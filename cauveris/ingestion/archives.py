"""
Archive detection and safe extraction for universal source intake.

Accepts anything a market-standard tool would hand us - ``.zip``,
``.tar``, ``.tar.gz``/``.tgz``, ``.tar.bz2``, ``.tar.xz``, or a single
compressed file (``.gz``/``.bz2``/``.xz`` of one document) - and decides
what it is from magic bytes, never from the file-name extension, because
the name is attacker-controlled and the bytes are not.

Extraction reuses the same hardening as the ZIP path in
:func:`cauveris.ingestion.controller.extract_zip_safely`: no absolute
paths, no ``..`` traversal, no symlinks/hardlinks/devices, member-count
cap, total uncompressed-size cap (zip-bomb defense), per-file size cap,
and a nesting-depth cap.  Nested archives found inside an extracted
bundle (a repo that ships ``assets/traces.zip``) are expanded in place
up to ``CAUVERIS_NESTED_ARCHIVE_DEPTH`` levels and
``CAUVERIS_MAX_NESTED_ARCHIVES`` archives total.
"""

from __future__ import annotations

import bz2
import gzip
import lzma
import logging
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from cauveris.config import Settings, get_settings
from cauveris.ingestion.controller import extract_zip_safely

logger = logging.getLogger(__name__)

__all__ = [
    "ARCHIVE_KINDS",
    "SUPPORTED_ARCHIVE_FORMATS",
    "SUPPORTED_ARCHIVE_EXTENSIONS",
    "detect_archive_kind",
    "extract_archive_safely",
    "expand_nested_archives",
    "flatten_single_root_dir",
    "materialize_payload",
    "sevenzip_available",
]

ARCHIVE_KINDS = {"zip", "tar", "gzip", "bzip2", "xz", "sevenzip"}

#: Human-facing list of the archive formats intake understands.  The API
#: (capabilities endpoint), the CLI and the web console all read this, so the
#: console can never advertise a format the backend cannot actually take.
SUPPORTED_ARCHIVE_FORMATS = [
    "zip",
    "tar",
    "tar.gz",
    "tgz",
    "tar.bz2",
    "tbz2",
    "tar.xz",
    "txz",
    "gz",
    "bz2",
    "xz",
    "7z (requires the optional 'archives' extra)",
]

#: Machine-readable extensions for the formats above, so the web console's
#: file pickers can build an ``accept`` list that never advertises a format
#: this deployment cannot actually read.  Detection is by magic bytes, so
#: these are picker hints only; ``.7z`` is dropped from the list the API
#: reports when the optional reader is missing (see :func:`sevenzip_available`).
SUPPORTED_ARCHIVE_EXTENSIONS = [
    ".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2",
    ".tar.xz", ".txz", ".gz", ".bz2", ".xz", ".7z",
]


def sevenzip_available() -> bool:
    """Whether the optional 7z reader (``py7zr``) is installed."""
    try:
        import py7zr  # noqa: F401
    except ImportError:
        return False
    return True

_MAGIC = [
    (b"PK\x03\x04", "zip"),
    (b"PK\x05\x06", "zip"),  # empty archive
    (b"PK\x07\x08", "zip"),  # spanned archive
    (b"\x1f\x8b", "gzip"),
    (b"BZh", "bzip2"),
    (b"\xfd7zXZ\x00", "xz"),
    (b"7z\xbc\xaf\x27\x1c", "sevenzip"),
]

#: 7-Zip needs a third-party reader (``py7zr``) that is not a hard
#: dependency; it is imported lazily and reported as unavailable otherwise.
_SEVENZIP_EXTRA_HINT = (
    "7z archives require the optional 'archives' extra: "
    'pip install "cauveris[archives]"'
)


def detect_archive_kind(head: bytes, filename: str = "") -> Optional[str]:
    """
    Classify a payload by magic bytes.

    Returns one of ``zip``, ``tar``, ``gzip``, ``bzip2``, ``xz``,
    ``sevenzip``, or ``None`` when the payload is not a recognized
    archive/compression format.  ``gzip``/``bzip2``/``xz`` may wrap a tar
    or a single file; the extractor decides which.

    ``filename`` is accepted for call-site symmetry but is deliberately not
    consulted: the name is attacker-controlled and the bytes are not.
    """
    if not head:
        return None
    for magic, kind in _MAGIC:
        if head.startswith(magic):
            return kind
    # tar (ustar magic at offset 257)
    if len(head) >= 262 and head[257:262] in (b"ustar",):
        return "tar"
    return None


def _validate_member_name(member: str, dest: Path) -> Path:
    """Normalize and validate one archive member path; returns the safe target."""
    norm = member.replace("\\", "/")
    if norm.startswith("/") or ".." in norm.split("/"):
        raise ValueError(f"Path traversal attempt detected: {member}")
    member_path = Path(norm)
    if member_path.is_absolute() or ".." in member_path.parts:
        raise ValueError(f"Invalid path in archive: {member}")
    if len(member_path.parts) > 15:
        raise ValueError(f"Directory nesting exceeds maximum permitted depth: {member}")
    safe_path = dest / member_path
    try:
        safe_path.resolve().relative_to(dest.resolve())
    except ValueError:
        raise ValueError(f"Path traversal attempt detected: {member}")
    return safe_path


def _check_caps(member_count: int, total_uncompressed: int, settings: Settings) -> None:
    if member_count == 0:
        raise ValueError("Archive is empty")
    if member_count > settings.max_archive_members:
        raise ValueError("Archive exceeds the member threshold")
    if total_uncompressed > settings.max_archive_uncompressed_size:
        raise ValueError("Archive exceeds the uncompressed-size threshold")


def _probe_is_tar(path: Path, block_aligned_only: bool = False) -> bool:
    """
    Whether a payload is a tar, including the pre-POSIX V7 layout.

    V7 tars carry no ``ustar`` magic, so magic-byte detection alone cannot
    see them; the tar reader can.  Used only as a fallback when no magic
    matched, so a misclassification costs one open() call.

    ``block_aligned_only`` applies the cheap "a tar is a whole number of
    512-byte blocks" rule first.  The nested-archive scan uses it so that
    probing thousands of files stays cheap.
    """
    if block_aligned_only:
        try:
            if path.stat().st_size % 512 != 0:
                return False
        except OSError:
            return False
    try:
        with tarfile.open(path, "r:*") as tf:
            tf.getmembers()
        return True
    except (tarfile.TarError, OSError, EOFError):
        return False


def classify_payload(
    path: Path, head: Optional[bytes] = None, block_aligned_only: bool = False
) -> Optional[str]:
    """
    Classify a payload on disk, falling back to a tar probe.

    Magic bytes decide first (the name is never consulted); only when no
    magic matched do we try to read the payload as a tar, which catches the
    old V7 format that has no magic at all.
    """
    path = Path(path)
    if head is None:
        try:
            with open(path, "rb") as fh:
                head = fh.read(1024)
        except OSError:
            return None
    kind = detect_archive_kind(head, path.name)
    if kind is None and _probe_is_tar(path, block_aligned_only=block_aligned_only):
        return "tar"
    return kind


def _extract_7z_safely(archive_path: Path, dest: Path, settings: Settings) -> List[Path]:
    """
    Extract a 7-Zip archive with the same traversal and size policy as tar/zip.

    7z support needs the optional ``py7zr`` reader; when it is not installed
    the caller gets an actionable error rather than an import traceback.
    """
    try:
        import py7zr
    except ImportError as exc:  # pragma: no cover - depends on the install extra
        raise ValueError(_SEVENZIP_EXTRA_HINT) from exc

    dest.mkdir(parents=True, exist_ok=True)
    try:
        with py7zr.SevenZipFile(archive_path, mode="r") as archive:
            entries = archive.list()
            if not entries:
                raise ValueError("Archive is empty")
            if len(entries) > settings.max_archive_members:
                raise ValueError("Archive exceeds the member threshold")
            declared = sum(max(0, int(getattr(e, "uncompressed", 0) or 0)) for e in entries)
            if declared > settings.max_archive_uncompressed_size:
                raise ValueError("Archive exceeds the uncompressed-size threshold")
            # Validate every member name *before* anything is written, so a
            # traversal attempt never reaches the filesystem.
            for entry in entries:
                name = getattr(entry, "filename", "") or ""
                if not name or getattr(entry, "is_directory", False):
                    continue
                _validate_member_name(name, dest)
            archive.extractall(path=dest)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Archive is corrupt or not a 7z archive: {exc}") from exc

    # Enforce the caps against what actually landed on disk - the declared
    # sizes inside the archive are not trustworthy.
    extracted: List[Path] = []
    total = 0
    for path in sorted(dest.rglob("*")):
        if not path.is_file():
            continue
        size = path.stat().st_size
        if size > settings.max_archive_file_size:
            try:
                path.unlink()
            except OSError:
                pass
            raise ValueError(f"File {path.name} exceeds maximum permitted size")
        total += size
        if total > settings.max_archive_uncompressed_size:
            try:
                path.unlink()
            except OSError:
                pass
            raise ValueError("Archive exceeds the uncompressed-size threshold")
        extracted.append(path)
    if len(extracted) > settings.max_archive_members:
        raise ValueError("Archive exceeds the member threshold")
    return extracted


def _extract_tar_safely(tar_path: Path, dest: Path, settings: Settings) -> List[Path]:
    """Extract a tar (optionally gz/bz2/xz compressed) with full hardening."""
    extracted: List[Path] = []
    dest.mkdir(parents=True, exist_ok=True)
    try:
        tf = tarfile.open(tar_path, "r:*")
    except tarfile.TarError as exc:
        raise ValueError(f"Archive is corrupt or not a tar: {exc}")
    with tf:
        members = tf.getmembers()
        total = sum(max(0, int(m.size)) for m in members)
        _check_caps(len(members), total, settings)
        for member in members:
            safe_path = _validate_member_name(member.name, dest)
            if member.isdir():
                safe_path.mkdir(parents=True, exist_ok=True)
                continue
            if member.issym() or member.islnk():
                raise ValueError(f"Symlinks/hardlinks are forbidden in archive: {member.name}")
            if member.isdev() or member.isfifo():
                raise ValueError(f"Device/FIFO entries are forbidden in archive: {member.name}")
            if not member.isreg():
                logger.warning("Skipping unsupported tar member type: %s", member.name)
                continue
            if member.size > settings.max_archive_file_size:
                raise ValueError(f"File {member.name} exceeds maximum permitted size")
            safe_path.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(member)
            if src is None:
                continue
            written = 0
            with src, open(safe_path, "wb") as out:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > settings.max_archive_file_size:
                        raise ValueError(f"File {member.name} exceeds maximum permitted size")
                    out.write(chunk)
            extracted.append(safe_path)
    return extracted


def _decompress_single_file(compressed: Path, dest: Path, settings: Settings, kind: str) -> List[Path]:
    """Decompress a single-file .gz/.bz2/.xz payload (not a tar)."""
    openers: Dict[str, Callable[..., Any]] = {"gzip": gzip.open, "bzip2": bz2.open, "xz": lzma.open}
    opener = openers[kind]
    name = compressed.name
    for suffix in (".gz", ".bz2", ".xz"):
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
            break
    if not name:
        name = f"decompressed-{kind}"
    target = dest / name
    dest.mkdir(parents=True, exist_ok=True)
    cap = settings.max_archive_uncompressed_size
    written = 0
    try:
        with opener(compressed, "rb") as src, open(target, "wb") as out:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > cap:
                    raise ValueError("Decompressed file exceeds the uncompressed-size threshold")
                out.write(chunk)
    except (OSError, EOFError, lzma.LZMAError) as exc:
        if target.exists():
            target.unlink()
        raise ValueError(f"Compressed file is corrupt: {exc}")
    return [target]


def extract_archive_safely(
    archive_path: Path, dest: Path, settings: Optional[Settings] = None
) -> List[Path]:
    """
    Extract any supported archive into ``dest`` with traversal/bomb guards.

    Dispatch is by magic bytes of the file, not by extension.  Returns the
    list of extracted file paths.  Raises ``ValueError`` on any policy
    violation or corrupt archive.
    """
    settings = settings or get_settings()
    archive_path = Path(archive_path)
    dest = Path(dest)
    try:
        with open(archive_path, "rb") as fh:
            head = fh.read(1024)
    except OSError as exc:
        raise ValueError(f"Cannot read archive {archive_path}: {exc}")
    kind = classify_payload(archive_path, head)

    if kind == "zip":
        try:
            return extract_zip_safely(archive_path, dest, settings)
        except zipfile.BadZipFile as exc:
            raise ValueError(f"Archive is corrupt: {exc}")
    if kind == "tar":
        return _extract_tar_safely(archive_path, dest, settings)
    if kind == "sevenzip":
        return _extract_7z_safely(archive_path, dest, settings)
    if kind in ("gzip", "bzip2", "xz"):
        # Either a compressed tar or a single compressed file.
        try:
            return _extract_tar_safely(archive_path, dest, settings)
        except ValueError as exc:
            if "corrupt or not a tar" not in str(exc):
                raise
            return _decompress_single_file(archive_path, dest, settings, kind)
    raise ValueError(
        f"Unsupported archive format for {archive_path.name!r}; "
        "expected ZIP, TAR, TAR.GZ/TGZ, TAR.BZ2, TAR.XZ, GZ, BZ2, XZ or 7Z"
    )


def _find_nested_archives(base: Path) -> List[Path]:
    """Archives under ``base``, excluding anything already inside ``__extracted__``."""
    found: List[Path] = []
    if not base.is_dir():
        return found
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        if "__extracted__" in path.relative_to(base).parts:
            continue
        try:
            with open(path, "rb") as fh:
                head = fh.read(1024)
        except OSError:
            continue
        if detect_archive_kind(head, path.name):
            found.append(path)
        elif classify_payload(path, head, block_aligned_only=True) == "tar":
            # A V7 tar has no magic; the block-alignment rule keeps this
            # probe cheap across a whole bundle.
            found.append(path)
    return found


def expand_nested_archives(root: Path, settings: Optional[Settings] = None) -> List[str]:
    """
    Expand archives found inside an extracted bundle, level by level.

    Level 1 expands archives sitting in the bundle itself; level 2 expands
    archives found inside those expansions, and so on, up to
    ``settings.nested_archive_depth`` levels and at most
    ``settings.max_nested_archives`` archives total, so a bundle of bundles
    cannot become a zip bomb.  Each archive is extracted next to its original
    under ``__extracted__/<archive-name>.d<level>/`` (the original is kept as
    evidence; the ``.d<level>`` suffix and a numeric disambiguator keep
    same-named archives in different directories from colliding).
    Returns human-readable warnings for every cap hit or archive that could
    not be expanded.
    """
    settings = settings or get_settings()
    warnings: List[str] = []
    root = Path(root)
    max_depth = max(0, int(settings.nested_archive_depth))
    expanded = 0
    current_bases: List[Path] = [root]
    for depth in range(1, max_depth + 1):
        candidates: List[Path] = []
        for base in current_bases:
            candidates.extend(_find_nested_archives(base))
        if not candidates:
            break
        next_bases: List[Path] = []
        for path in candidates:
            if expanded >= settings.max_nested_archives:
                warnings.append(
                    f"Nested archive cap reached ({settings.max_nested_archives}); "
                    f"not expanding {path.name}"
                )
                return warnings
            target = path.parent / "__extracted__" / f"{path.name}.d{depth}"
            n = 1
            while target.exists():
                target = path.parent / "__extracted__" / f"{path.name}.d{depth}.{n}"
                n += 1
            try:
                extract_archive_safely(path, target, settings)
                expanded += 1
                next_bases.append(target)
                logger.info("Expanded nested archive %s -> %s", path, target)
            except ValueError as exc:
                warnings.append(f"Could not expand nested archive {path.name}: {exc}")
        current_bases = next_bases
    # Warn only when archives genuinely remain unexpanded because of the depth cap.
    if max_depth > 0 and current_bases:
        remaining = sum(len(_find_nested_archives(base)) for base in current_bases)
        if remaining:
            warnings.append(
                f"Nested archive depth cap reached ({max_depth}); "
                f"{remaining} nested archive(s) left unexpanded"
            )
    return warnings


def flatten_single_root_dir(dest: Path) -> bool:
    """
    GitHub/GitLab codeload archives wrap everything in one top-level
    directory (``repo-ref/``).  When an extraction produced exactly one
    directory and no loose files, hoist its contents up so the bundle
    root *is* the project root.  Returns True when a flatten happened.
    """
    dest = Path(dest)
    try:
        entries = list(dest.iterdir())
    except OSError:
        return False
    if len(entries) == 1 and entries[0].is_dir():
        inner = entries[0]
        for child in inner.iterdir():
            shutil.move(str(child), str(dest / child.name))
        inner.rmdir()
        logger.info("Flattened single top-level directory %s", inner.name)
        return True
    return False


def materialize_payload(
    payload_path: Path, dest_dir: Path, settings: Optional[Settings] = None
) -> Tuple[Path, str, List[str]]:
    """
    Turn a downloaded/uploaded payload into a bundle directory.

    Archives are extracted, nested archives expanded, and a single
    top-level directory flattened (GitHub-codeload layout).  A
    non-archive file is copied in as the bundle's only evidence file.

    Returns ``(bundle_root, payload_kind, warnings)`` where payload_kind
    is the detected archive kind or ``"file"``.
    """
    settings = settings or get_settings()
    payload_path = Path(payload_path)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        with open(payload_path, "rb") as fh:
            head = fh.read(1024)
    except OSError as exc:
        raise ValueError(f"Cannot read payload {payload_path}: {exc}")
    kind = classify_payload(payload_path, head)

    if kind is None:
        # Single evidence file (JSON/JSONL/CSV/YAML/log/...): place it as-is.
        if payload_path.stat().st_size > settings.max_archive_file_size:
            raise ValueError("Single-file payload exceeds maximum permitted size")
        target = dest_dir / payload_path.name.replace("\\", "/").split("/")[-1]
        shutil.copyfile(payload_path, target)
        return dest_dir, "file", []

    extract_archive_safely(payload_path, dest_dir, settings)
    warnings = expand_nested_archives(dest_dir, settings)
    flatten_single_root_dir(dest_dir)
    return dest_dir, kind, warnings
