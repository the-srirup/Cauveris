"""
Universal source resolution for incident intake.

An engineer should be able to hand Cauveris *anything* a market-standard
tool hands them and have it flow through the pipeline:

* a local ZIP/TAR/... archive or a single evidence file,
* a local directory (a source checkout),
* a GitHub or GitLab URL - repo page, ``/archive/...``, ``/tree/<ref>``,
  release asset, or the ``github:owner/repo@ref`` / ``owner/repo``
  shorthand - resolved to a codeload archive of the source tree,
* a PyPI package (``pypi:requests@2.32`` or ``https://pypi.org/project/requests/``)
  - the sdist is preferred because it carries source, not just wheels,
* an npm package (``npm:lodash@4.17`` or a registry tarball URL),
* or any generic HTTPS URL pointing at an archive or evidence file.

Everything remote is downloaded through
:mod:`cauveris.ingestion.urlfetch` (SSRF-guarded) and materialized through
:mod:`cauveris.ingestion.archives` (magic-byte detection + hardened
extraction).  The result is a plain bundle directory that the existing
:class:`~cauveris.ingestion.controller.IngestionController` consumes
unchanged - with or without a ``manifest.yaml`` inside.

The full provenance of the source (kind, requested spec, final URL after
redirects, SHA-256, byte size) is returned in the descriptor so the
incident manifest can record exactly where its evidence came from.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import stat
import subprocess
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlsplit

import httpx

from cauveris.config import Settings, get_settings
from cauveris.ingestion.archives import materialize_payload
from cauveris.ingestion.urlfetch import (
    FetchedFile,
    SourceFetchError,
    fetch_to_file,
    validate_url,
)

logger = logging.getLogger(__name__)

__all__ = [
    "SourceSpecError",
    "ParsedSource",
    "ResolvedSource",
    "SPEC_FORMS",
    "parse_source",
    "resolve_source",
]


#: Accepted spec forms with a concrete example each.  The capabilities
#: endpoint serves exactly this list, so the console can never advertise a
#: form the backend cannot parse.
SPEC_FORMS = [
    {"form": "local path", "example": "/data/bundle.zip",
     "description": "Server-local archive/dir/file (CLI always; API only when CAUVERIS_ALLOW_LOCAL_PATH_INGEST=true)"},
    {"form": "https:// URL", "example": "https://example.com/incident-bundle.zip",
     "description": "Any allow-listed HTTPS URL pointing at an archive or a single evidence file"},
    {"form": "github:owner/repo[@ref]", "example": "github:psf/requests@v2.32.3",
     "description": "GitHub repo as a codeload zip; the bare owner/repo shorthand works too, as do github.com page URLs"},
    {"form": "gitlab:owner/repo[@ref]", "example": "gitlab:owner/repo@main",
     "description": "GitLab repo as an archive zip; gitlab.com page URLs work too"},
    {"form": "git+https://host/path/repo.git[@ref]", "example": "git+https://github.com/psf/requests.git@v2.32.3",
     "description": "Depth-1 git clone of any allow-listed HTTPS repo (a bare https://.../repo.git URL works too)"},
    {"form": "pypi:package[@version|range]", "example": "pypi:requests@>=2.0",
     "description": "PyPI package, sdist preferred; exact pin or PEP 440 range (highest match wins)"},
    {"form": "npm:package[@version|range]", "example": "npm:@angular/core@^17.0.0",
     "description": "npm package incl. scoped names; exact pin or semver range (^, ~, >=, *)"},
    {"form": "maven:group:artifact[:version]", "example": "maven:com.google.guava:guava:33.0.0",
     "description": "Maven Central artifact; prefers the -sources.jar, falls back to the plain jar"},
    {"form": "crates:name[@version|range]", "example": "crates:serde@1.0.200",
     "description": "crates.io crate (semver ranges ok)"},
    {"form": "go:module[@version|range]", "example": "go:github.com/gin-gonic/gin@v1.9.1",
     "description": "Go module via proxy.golang.org (semver ranges ok)"},
    {"form": "nuget:id[@version|range]", "example": "nuget:Newtonsoft.Json@13.0.3",
     "description": "NuGet package (semver ranges ok)"},
    {"form": "gem:name[@version|range]", "example": "gem:rails@7.1.0",
     "description": "RubyGems gem (PEP-440-style ranges ok)"},
]


class SourceSpecError(ValueError):
    """The source spec could not be understood or is not permitted."""


@dataclass
class ParsedSource:
    """A parsed, but not yet fetched, source specification."""

    kind: str  # local_file | local_dir | http_url | github | gitlab | pypi | npm
    # | maven | crates | go | nuget | gem | git
    raw: str
    url: Optional[str] = None  # direct download URL when already known
    owner: Optional[str] = None
    repo: Optional[str] = None
    ref: Optional[str] = None
    package: Optional[str] = None
    version: Optional[str] = None
    group: Optional[str] = None  # maven only
    fallback_url: Optional[str] = None  # maven: plain jar when -sources.jar 404s
    local_path: Optional[Path] = None


@dataclass
class ResolvedSource:
    """A source materialized as a bundle directory on disk."""

    bundle_dir: Path
    source_kind: str  # archive kind ("zip", "tar.gz", ...) or "file" / "local_dir"
    descriptor: Dict[str, Any]
    warnings: List[str] = field(default_factory=list)
    package_sha256: str = ""
    size_bytes: int = 0
    filename: str = ""


_GITHUB_SHORTHAND = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_REF_SPLIT = re.compile(r"[@/]")


def _split_repo_ref(spec: str) -> tuple[str, str, Optional[str]]:
    """Split ``owner/repo@ref`` / ``owner/repo/ref`` into (owner, repo, ref)."""
    ref: Optional[str] = None
    if "@" in spec:
        spec, ref = spec.rsplit("@", 1)
    parts = [p for p in spec.split("/") if p]
    if len(parts) < 2:
        raise SourceSpecError(f"Expected owner/repo, got {spec!r}")
    owner, repo = parts[0], parts[1]
    if ref is None and len(parts) > 2:
        ref = "/".join(parts[2:])
    return owner, repo, ref


def _split_pkg_version(rest: str) -> tuple[str, Optional[str]]:
    """
    Split ``package@version`` into (package, version), tolerating scoped names.

    The version separator is the *last* ``@`` that appears after the last
    ``/``, so ``@scope/name@1.2.3`` -> (``@scope/name``, ``1.2.3``) and
    ``@scope/name`` -> (``@scope/name``, None).  Splitting on the first ``@``
    (``str.partition("@")``) is what broke scoped npm packages: it produced an
    empty package name.
    """
    rest = rest.strip()
    slash = rest.rfind("/")
    at = rest.rfind("@")
    if at > slash and at > 0:
        return rest[:at].strip(), (rest[at + 1:].strip() or None)
    return rest, None


# ---------------------------------------------------------------------------
# Version-range resolution.
#
# Exact versions keep the fast path (a direct metadata lookup).  Anything
# else - ``latest``, ``*``, ``^1.2``, ``~1.2.3``, ``>=1.0`` for npm, or
# ``latest``/``>=2.0``/``!=2.32.0``/``1.*`` for PyPI - is resolved against the
# registry's full version list and picks the highest satisfying version.
# ---------------------------------------------------------------------------

_SEMVER_RE = re.compile(
    r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-([0-9A-Za-z.\-]+))?(?:\+[0-9A-Za-z.\-]+)?$"
)


def _semver_key(version: str) -> Optional[tuple]:
    """A comparable key for a semver string (npm versions), or None."""
    m = _SEMVER_RE.match(version.strip())
    if not m:
        return None
    major = int(m.group(1))
    minor = int(m.group(2) or 0)
    patch = int(m.group(3) or 0)
    pre = m.group(4) or ""
    pre_key = tuple((0, int(p)) if p.isdigit() else (1, p) for p in pre.split(".") if p)
    # A release outranks any of its pre-releases (1.0.0 > 1.0.0-rc.1).
    return (major, minor, patch, 0 if pre else 1, pre_key)


def _semver_part_matches(key: tuple, part: str) -> bool:
    """Whether one whitespace-separated range clause matches ``key``."""
    part = part.strip()
    if not part or part in ("*", "x", "X"):
        return True
    if part.startswith("^"):
        raw = part[1:]
        base = _semver_key(raw)
        if base is None:
            return False
        major, minor, patch = base[0], base[1], base[2]
        specified = len([c for c in raw.split("-", 1)[0].split("+", 1)[0].split(".") if c != ""])
        if major > 0:
            hi = (major + 1, 0, 0, 1, ())
        elif minor > 0:
            hi = (0, minor + 1, 0, 1, ())
        elif specified >= 3:
            hi = (0, 0, patch + 1, 1, ())
        elif specified == 2:
            hi = (0, 1, 0, 1, ())
        else:
            hi = (1, 0, 0, 1, ())
        return base <= key < hi
    if part.startswith("~"):
        raw = part[1:]
        base = _semver_key(raw)
        if base is None:
            return False
        major, minor = base[0], base[1]
        specified = len([c for c in raw.split("-", 1)[0].split("+", 1)[0].split(".") if c != ""])
        hi = (major, minor + 1, 0, 1, ()) if specified >= 2 else (major + 1, 0, 0, 1, ())
        return base <= key < hi
    # Wildcards: 1.* -> [1.0.0, 2.0.0), 1.2.* -> [1.2.0, 1.3.0)
    if part.endswith(".*") or part in ("x", "X"):
        head = part[:-2].rstrip(".")
        base = _semver_key(head or "0")
        if base is None:
            return False
        comps = [c for c in head.split(".") if c != ""] if head else []
        if len(comps) >= 2:
            hi = (base[0], base[1] + 1, 0, 1, ())
        else:
            hi = (base[0] + 1, 0, 0, 1, ())
        return base <= key < hi
    for op in (">=", "<=", "==", "!=", ">", "<", "="):
        if part.startswith(op):
            other = _semver_key(part[len(op):])
            if other is None:
                return False
            return {
                ">=": key >= other,
                "<=": key <= other,
                ">": key > other,
                "<": key < other,
                "==": key[:3] == other[:3] and key[3:] == other[3:],
                "!=": not (key[:3] == other[:3] and key[3:] == other[3:]),
                "=": key == other,
            }[op]
    # Bare version: exact match.
    other = _semver_key(part)
    return other is not None and key == other


def _npm_version_matches(spec: str, version: str) -> bool:
    """Semver range match (space-separated clauses are ANDed, as in npm)."""
    key = _semver_key(version)
    if key is None:
        return False
    return all(_semver_part_matches(key, part) for part in spec.split())


def _pypi_sort_key(version: str) -> tuple:
    """A total-order sort key for a PEP 440-ish version string."""
    try:
        from packaging.version import Version

        v = Version(version)
        return (1, v.epoch, v.release, v.pre or (), v.post or (), v.dev or (), str(v.local or ""))
    except Exception:
        return (0,) + _simple_version_key(version)


def _simple_version_key(version: str) -> tuple:
    """Dependency-free approximation of a PEP 440 sort key."""
    v = version.strip().lower().lstrip("v")
    if "!" in v:
        v = v.split("!", 1)[1]
    m = re.match(r"^(\d+(?:\.\d+)*)(.*)$", v)
    nums = tuple(int(x) for x in m.group(1).split(".")) if m else (0,)
    nums = nums + (0,) * max(0, 3 - len(nums))
    tail = m.group(2) if m else ""
    pre_key = tuple((0, int(p)) if p.isdigit() else (1, p) for p in re.split(r"[.\-_]", tail) if p)
    return (nums, 0 if not tail else 1, pre_key)


def _pypi_is_range(version: Optional[str]) -> bool:
    """Whether a PyPI version string is a range rather than an exact pin."""
    if not version:
        return True  # None means "latest"
    v = version.strip()
    # "^" is npm syntax, not PEP 440; treating it as a range makes the
    # registry resolver answer "no version matching '^1.0'" instead of
    # querying a nonexistent exact version endpoint.
    return v in ("latest", "*") or "*" in v or v[0] in "<>=!~^"


def _pypi_version_matches(spec: Optional[str], version: str) -> bool:
    """PEP 440 specifier match via packaging, with a simple fallback."""
    spec = (spec or "latest").strip()
    if spec in ("latest", "*", ""):
        return True
    try:
        from packaging.specifiers import SpecifierSet
        from packaging.version import Version

        try:
            return Version(version) in SpecifierSet(spec)
        except Exception:
            pass  # non-PEP-440 version or specifier (e.g. maven's 33.0.0-jre)
    except ImportError:
        pass
    # Fallback without packaging: handle the common operators on dotted keys.
    for op in ("==", "!=", ">=", "<=", "~=", ">", "<"):
        if spec.startswith(op):
            other = _simple_version_key(spec[len(op):].replace(".*", ""))
            key = _simple_version_key(version)
            if op == "==":
                return key[0] == other[0]
            if op == "!=":
                return key[0] != other[0]
            if op == ">=":
                return key >= other
            if op == "<=":
                return key <= other
            if op == ">":
                return key > other
            if op == "<":
                return key < other
            if op == "~=":
                comps = spec[len(op):].replace(".*", "").split(".")
                upper = list(other[0])
                if len(comps) >= 2:
                    upper[1] = upper[1] + 1
                    upper = upper[:2] + [0] * (len(upper) - 2)
                else:
                    upper[0] = upper[0] + 1
                    upper = upper[:1] + [0] * (len(upper) - 1)
                return key >= other and key[0] < tuple(upper)
    return _simple_version_key(spec) == _simple_version_key(version)


def _hash_file(path: Path) -> str:
    """SHA-256 of a file, read in chunks so huge files never sit in memory."""
    hasher = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _github_codeload_url(owner: str, repo: str, ref: Optional[str]) -> str:
    ref = ref or "HEAD"
    return f"https://codeload.github.com/{owner}/{repo}/zip/{quote(ref, safe='')}"


def _github_from_page_url(url: str) -> ParsedSource:
    """Map any github.com URL shape onto a codeload archive download."""
    parts = [p for p in urlsplit(url).path.split("/") if p]
    if len(parts) < 2:
        raise SourceSpecError(f"Not a GitHub repository URL: {url!r}")
    owner, repo = parts[0], parts[1]
    ref: Optional[str] = None
    sub = parts[2] if len(parts) > 2 else ""
    if sub == "tree" and len(parts) > 3:
        ref = "/".join(parts[3:])  # branch names may contain slashes
    elif sub == "archive" and len(parts) > 4:
        # /owner/repo/archive/refs/heads/main.zip -> direct asset
        return ParsedSource(kind="github", raw=url, url=url, owner=owner, repo=repo)
    elif sub == "releases" and "download" in parts:
        # a release asset URL - download it directly
        return ParsedSource(kind="github", raw=url, url=url, owner=owner, repo=repo)
    elif sub == "blob" and len(parts) > 3:
        ref = parts[3]  # single-file view: still take the tree at that ref
    return ParsedSource(
        kind="github", raw=url, url=_github_codeload_url(owner, repo, ref), owner=owner, repo=repo, ref=ref
    )


def _gitlab_archive_url(owner: str, repo: str, ref: Optional[str]) -> str:
    ref = ref or "HEAD"
    return f"https://gitlab.com/{owner}/{repo}/-/archive/{quote(ref, safe='')}/{repo}-{ref}.zip"


def _gitlab_from_page_url(url: str) -> ParsedSource:
    parts = [p for p in urlsplit(url).path.split("/") if p]
    if len(parts) < 2:
        raise SourceSpecError(f"Not a GitLab project URL: {url!r}")
    owner, repo = parts[0], parts[1]
    # GitLab marks special endpoints with a "-" segment: /-/archive/... and
    # /-/tree/<ref>/...  ("-/archive" is never a single list element after the
    # split, so match on the marker segment pair.)
    if "-" in parts:
        idx = parts.index("-")
        marker = parts[idx + 1] if idx + 1 < len(parts) else ""
        if marker == "archive":
            # Direct archive asset URL - download it as-is.
            return ParsedSource(kind="gitlab", raw=url, url=url, owner=owner, repo=repo)
        if marker == "tree" and idx + 2 < len(parts):
            ref = "/".join(parts[idx + 2:])  # branch names may contain slashes
            return ParsedSource(
                kind="gitlab", raw=url, url=_gitlab_archive_url(owner, repo, ref),
                owner=owner, repo=repo, ref=ref,
            )
    return ParsedSource(
        kind="gitlab", raw=url, url=_gitlab_archive_url(owner, repo, None), owner=owner, repo=repo, ref=None
    )


def parse_source(spec: str, settings: Optional[Settings] = None) -> ParsedSource:
    """
    Parse a source spec into a :class:`ParsedSource`.

    Accepted forms::

        /path/to/bundle.zip | /path/to/bundle.tar.gz | /path/to/evidence.json
        /path/to/source-dir
        https://example.com/incident.zip
        https://github.com/owner/repo[/tree/ref|...|/archive/...|/releases/download/...]
        github:owner/repo[@ref]        | owner/repo  (GitHub shorthand)
        https://gitlab.com/owner/repo[/-/archive/ref/...]
        gitlab:owner/repo[@ref]
        pypi:package[@version|range]   | https://pypi.org/project/package/
        npm:package[@version|range]    | https://registry.npmjs.org/...tgz
        maven:group:artifact[:version] | crates:name[@version|range]
        go:module[@version|range]      | nuget:id[@version|range]
        gem:name[@version|range]
        git+https://host/path/repo.git[@ref]  |  https://host/path/repo.git

    ``package`` may be scoped (``npm:@scope/name@1.2.3``); the version may
    be an exact pin or a range - npm/crates/Go/NuGet understand semver ranges
    (``latest``, ``*``, ``^``, ``~``, ``>=``), PyPI/Gems understand PEP 440
    specifiers (``>=2.0``, ``!=2.32.0``, ``2.*``).  The highest satisfying
    version is chosen.

    ``owner/repo`` is treated as a GitHub shorthand only when no local
    path with that name exists.  ``docker://`` and ``oci://`` are refused
    explicitly - container image intake needs a registry auth model.
    """
    settings = settings or get_settings()
    if not spec or not spec.strip():
        raise SourceSpecError("Empty source spec")
    spec = spec.strip()

    if spec.startswith("github:"):
        owner, repo, ref = _split_repo_ref(spec[len("github:"):])
        return ParsedSource(
            kind="github", raw=spec, url=_github_codeload_url(owner, repo, ref),
            owner=owner, repo=repo, ref=ref,
        )
    if spec.startswith("gitlab:"):
        owner, repo, ref = _split_repo_ref(spec[len("gitlab:"):])
        return ParsedSource(
            kind="gitlab", raw=spec, url=_gitlab_archive_url(owner, repo, ref),
            owner=owner, repo=repo, ref=ref,
        )
    if spec.startswith("git+"):
        return _parse_git_spec(spec)
    if spec.startswith("pypi:"):
        pkg, ver = _split_pkg_version(spec[len("pypi:"):])
        return ParsedSource(kind="pypi", raw=spec, package=pkg, version=ver)
    if spec.startswith("npm:"):
        pkg, ver = _split_pkg_version(spec[len("npm:"):])
        return ParsedSource(kind="npm", raw=spec, package=pkg, version=ver)
    if spec.startswith("maven:"):
        rest = spec[len("maven:"):].strip()
        version = None
        if "@" in rest:
            rest, version = rest.split("@", 1)
        parts = rest.split(":")
        if len(parts) < 2 or not parts[0] or not parts[1]:
            raise SourceSpecError(
                "maven: source needs group:artifact[:version] or group:artifact[@version], e.g. maven:com.google.guava:guava:33.0.0"
            )
        group = parts[0]
        artifact = parts[1]
        if not version and len(parts) > 2 and parts[2]:
            version = parts[2]
        return ParsedSource(
            kind="maven", raw=spec, group=group, package=artifact,
            version=version or None,
        )
    if spec.startswith("crates:"):
        pkg, ver = _split_pkg_version(spec[len("crates:"):])
        return ParsedSource(kind="crates", raw=spec, package=pkg, version=ver)
    if spec.startswith("go:"):
        pkg, ver = _split_pkg_version(spec[len("go:"):])
        return ParsedSource(kind="go", raw=spec, package=pkg, version=ver)
    if spec.startswith("nuget:"):
        pkg, ver = _split_pkg_version(spec[len("nuget:"):])
        return ParsedSource(kind="nuget", raw=spec, package=pkg, version=ver)
    if spec.startswith("gem:"):
        pkg, ver = _split_pkg_version(spec[len("gem:"):])
        return ParsedSource(kind="gem", raw=spec, package=pkg, version=ver)

    if "://" in spec:
        scheme = spec.split("://", 1)[0].lower()
        if scheme in ("docker", "oci"):
            raise SourceSpecError(
                f"{scheme}:// intake is not supported by this deployment "
                "(container image intake needs a registry auth model)"
            )
        if scheme not in ("http", "https"):
            raise SourceSpecError(f"Unsupported URL scheme {scheme!r} in {spec!r}")
        if urlsplit(spec).path.endswith(".git"):
            # A bare https://host/.../repo.git URL means "clone this repo".
            return _parse_git_url(spec, spec)
        host = (urlsplit(spec).hostname or "").lower()
        if host == "github.com" or host == "www.github.com":
            return _github_from_page_url(spec)
        if host == "api.github.com" and "/repos/" in urlsplit(spec).path:
            return ParsedSource(kind="github", raw=spec, url=spec)
        if host == "gitlab.com":
            return _gitlab_from_page_url(spec)
        if host == "pypi.org":
            path = urlsplit(spec).path
            m = re.search(r"/project/([^/]+)", path)
            if m:
                return ParsedSource(kind="pypi", raw=spec, package=m.group(1))
            m = re.search(r"/pypi/([^/]+)", path)
            if m:
                return ParsedSource(kind="pypi", raw=spec, package=m.group(1))
            raise SourceSpecError(f"Unrecognized PyPI URL: {spec!r}")
        if host == "registry.npmjs.org":
            path = urlsplit(spec).path
            if path.endswith(".tgz"):
                return ParsedSource(kind="npm", raw=spec, url=spec,
                                    package=path.strip("/").split("/-/")[0])
            m = re.match(r"^/(@?[^/]+(?:/[^/]+)?)/?$", path)
            if m:
                return ParsedSource(kind="npm", raw=spec, package=m.group(1).lstrip("/"))
            raise SourceSpecError(f"Unrecognized npm registry URL: {spec!r}")
        return ParsedSource(kind="http_url", raw=spec, url=spec)

    # No scheme: a local path, or an owner/repo GitHub shorthand.
    local = Path(spec)
    if local.exists():
        return ParsedSource(
            kind="local_dir" if local.is_dir() else "local_file",
            raw=spec, local_path=local,
        )
    if _GITHUB_SHORTHAND.match(spec):
        owner, repo, ref = _split_repo_ref(spec)
        return ParsedSource(
            kind="github", raw=spec, url=_github_codeload_url(owner, repo, ref),
            owner=owner, repo=repo, ref=ref,
        )
    raise SourceSpecError(
        f"Cannot interpret source {spec!r}: not an existing local path, not an HTTPS URL, "
        "and not a recognized shorthand (see /api/v1/ingest/capabilities for the list: "
        "github:owner/repo@ref, pypi:pkg@ver, npm:pkg@ver, maven:g:a:v, crates:name@v, "
        "go:module@v, nuget:id@v, gem:name@v, git+https://.../repo.git@ref, owner/repo)"
    )


def _hash_bundle_dir(bundle_dir: Path) -> str:
    """A deterministic content hash for a local directory source."""
    hasher = hashlib.sha256()
    for path in sorted(p for p in bundle_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(bundle_dir).as_posix()
        hasher.update(f"{rel}:{_hash_file(path)}\n".encode())
    return hasher.hexdigest()


def _copy_local_dir(src: Path, dest: Path, settings: Settings) -> List[str]:
    """Copy a local source tree into the bundle dir with the same caps as archives."""
    warnings: List[str] = []
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    total = 0
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        if ".git" in rel.parts:
            continue
        if len(rel.parts) > 15:
            warnings.append(f"Skipping too-deep path: {rel}")
            continue
        target = dest / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if not path.is_file():
            continue  # skip symlinks/sockets/etc. from local trees
        size = path.stat().st_size
        count += 1
        total += size
        if count > settings.max_archive_members:
            raise SourceSpecError("Local directory exceeds the member threshold")
        if total > settings.max_archive_uncompressed_size:
            raise SourceSpecError("Local directory exceeds the uncompressed-size threshold")
        if size > settings.max_archive_file_size:
            warnings.append(f"Skipping oversized file: {rel}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    return warnings


def _pypi_choose_file(files: List[Dict[str, Any]], context: str) -> Dict[str, Any]:
    """Prefer the sdist (it carries source), fall back to the wheel."""
    sdist = next((u for u in files if u.get("packagetype") == "sdist"), None)
    wheel = next((u for u in files if u.get("packagetype") == "bdist_wheel"), None)
    chosen = sdist or wheel
    if not chosen:
        raise SourceSpecError(f"PyPI package {context} has no downloadable sdist or wheel")
    return chosen


async def _resolve_pypi(parsed: ParsedSource, staging: Path, settings: Settings,
                        client: Optional[httpx.AsyncClient]) -> tuple[ParsedSource, str]:
    """
    Resolve a PyPI package to a concrete sdist/wheel URL via the JSON API.

    An exact version pins the ``/pypi/<pkg>/<version>/json`` endpoint (fast
    path, unchanged behaviour).  ``latest``/``*``/PEP 440 ranges fetch the
    full ``/pypi/<pkg>/json`` metadata and pick the highest version in
    ``releases`` that satisfies the specifier and ships at least one file.
    """
    pkg = parsed.package or ""
    if not pkg:
        raise SourceSpecError("PyPI source needs a package name")
    requested = (parsed.version or "").strip()
    exact = bool(requested) and not _pypi_is_range(requested)
    if exact:
        meta_url = f"https://pypi.org/pypi/{quote(pkg)}/{quote(requested)}/json"
    else:
        meta_url = f"https://pypi.org/pypi/{quote(pkg)}/json"
    fetched = await fetch_to_file(
        meta_url, staging, settings, filename=f"pypi-{pkg}.json", client=client,
        extra_headers={"Accept": "application/json"},
    )
    try:
        meta = json.loads(fetched.path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SourceSpecError(f"PyPI metadata for {pkg!r} is not valid JSON: {exc}")

    if exact:
        chosen = _pypi_choose_file(meta.get("urls") or [], f"{pkg!r}@{requested}")
        resolved_version = (meta.get("info") or {}).get("version") or requested
    else:
        releases = meta.get("releases") or {}
        info_version = (meta.get("info") or {}).get("version")
        if not requested or requested == "latest":
            candidates = [info_version] if info_version and releases.get(info_version) else []
            if not candidates:
                candidates = [v for v, files in releases.items() if files]
        else:
            candidates = [
                v for v, files in releases.items()
                if files and _pypi_version_matches(requested, v)
            ]
        if not candidates:
            available = sorted(releases)[-5:] if releases else []
            raise SourceSpecError(
                f"PyPI package {pkg!r} has no version matching {requested or 'latest'!r} "
                f"(available: {available if available else 'none'})"
            )
        resolved_version = max(candidates, key=_pypi_sort_key)
        chosen = _pypi_choose_file(releases[resolved_version], f"{pkg!r}@{resolved_version}")
    resolved = ParsedSource(
        kind="pypi", raw=parsed.raw, url=chosen["url"],
        package=pkg, version=resolved_version,
    )
    return resolved, Path(chosen["url"]).name


async def _resolve_npm(parsed: ParsedSource, staging: Path, settings: Settings,
                       client: Optional[httpx.AsyncClient]) -> tuple[ParsedSource, str]:
    """
    Resolve an npm package to a concrete tarball URL via registry metadata.

    ``parsed.version`` may be an exact pin, ``latest``/``*``, or a semver
    range (``^1.2``, ``~1.2.3``, ``>=1.0 <2.0``); the highest satisfying
    version in ``meta.versions`` wins, with pre-releases ranked by semver.
    """
    pkg = parsed.package or ""
    if not pkg:
        raise SourceSpecError("npm source needs a package name")
    meta_url = f"https://registry.npmjs.org/{quote(pkg, safe='@/')}"
    fetched = await fetch_to_file(
        meta_url, staging, settings, filename="npm-meta.json", client=client,
        extra_headers={"Accept": "application/json"},
    )
    try:
        meta = json.loads(fetched.path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SourceSpecError(f"npm metadata for {pkg!r} is not valid JSON: {exc}")
    versions = meta.get("versions") or {}
    if not versions:
        raise SourceSpecError(f"npm package {pkg!r} has no published versions")
    requested = (parsed.version or "").strip()
    dist_tags = meta.get("dist-tags") or {}
    if not requested or requested in ("latest", "*"):
        version = dist_tags.get("latest")
        if version not in versions:
            version = max(versions, key=lambda v: _semver_key(v) or (0, 0, 0, 0, ()))
    elif requested in versions:
        version = requested  # exact pin - today's behaviour
    else:
        candidates = [v for v in versions if _npm_version_matches(requested, v)]
        if not candidates:
            raise SourceSpecError(
                f"npm package {pkg!r} has no version matching {requested!r} "
                f"(available: {sorted(versions)[-5:]})"
            )
        version = max(candidates, key=lambda v: _semver_key(v) or (0, 0, 0, 0, ()))
    tarball = versions[version].get("dist", {}).get("tarball")
    if not tarball:
        raise SourceSpecError(f"npm package {pkg!r}@{version} has no tarball URL")
    resolved = ParsedSource(kind="npm", raw=parsed.raw, url=tarball, package=pkg, version=version)
    return resolved, Path(urlsplit(tarball).path).name


# ---------------------------------------------------------------------------
# Additional registries (Maven Central, crates.io, Go modules, NuGet,
# RubyGems) and git clone.  Each registry resolver turns a spec into a
# concrete download URL after asking that registry's metadata API; the
# download itself still goes through fetch_to_file (SSRF-guarded).
# ---------------------------------------------------------------------------

_MAVEN_BASE = "https://repo1.maven.org/maven2"

#: A token safe to embed in a URL path segment (no traversal, no slashes).
_VERSION_TOKEN_RE = re.compile(r"^[0-9A-Za-z._+~-]+$")


def _check_version_token(version: str, context: str) -> str:
    """Reject version strings that could escape a URL path segment."""
    if not version or not _VERSION_TOKEN_RE.fullmatch(version) or ".." in version:
        raise SourceSpecError(f"Unsafe version {version!r} in {context}")
    return version


async def _fetch_json(url: str, staging: Path, settings: Settings,
                      client: Optional[httpx.AsyncClient], filename: str) -> Any:
    """Fetch a metadata document and parse it as JSON."""
    fetched = await fetch_to_file(
        url, staging, settings, filename=filename, client=client,
        extra_headers={"Accept": "application/json"},
    )
    try:
        return json.loads(fetched.path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SourceSpecError(f"Metadata from {url} is not valid JSON: {exc}")


def _pick_semver_version(requested: Optional[str], versions: List[str],
                         latest: Optional[str], ctx: str) -> str:
    """Pick the highest version satisfying an exact/semver-range request."""
    requested = (requested or "").strip()
    if not versions:
        raise SourceSpecError(f"{ctx} has no published versions")
    if not requested or requested in ("latest", "*"):
        if latest in versions:
            return latest  # type: ignore[return-value]
        return max(versions, key=lambda v: _semver_key(v) or (0, 0, 0, 0, ()))
    if requested in versions:
        return requested
    candidates = [v for v in versions if _npm_version_matches(requested, v)]
    if not candidates:
        raise SourceSpecError(
            f"{ctx} has no version matching {requested!r} (available: {sorted(versions)[-5:]})"
        )
    return max(candidates, key=lambda v: _semver_key(v) or (0, 0, 0, 0, ()))


def _pick_pypi_version(requested: Optional[str], versions: List[str],
                       latest: Optional[str], ctx: str) -> str:
    """Pick the highest version satisfying an exact/PEP 440-range request."""
    requested = (requested or "").strip()
    if not versions:
        raise SourceSpecError(f"{ctx} has no published versions")
    if not requested or requested == "latest":
        if latest in versions:
            return latest  # type: ignore[return-value]
        return max(versions, key=_pypi_sort_key)
    candidates = [v for v in versions if _pypi_version_matches(requested, v)]
    if not candidates:
        raise SourceSpecError(
            f"{ctx} has no version matching {requested!r} (available: {sorted(versions)[-5:]})"
        )
    return max(candidates, key=_pypi_sort_key)


async def _resolve_maven(parsed: ParsedSource, staging: Path, settings: Settings,
                         client: Optional[httpx.AsyncClient]) -> tuple[ParsedSource, str]:
    """Resolve ``maven:group:artifact[:version]`` via Maven Central metadata."""
    group = parsed.group or ""
    artifact = parsed.package or ""
    if not group or not artifact:
        raise SourceSpecError(
            "maven: source needs group:artifact[:version], e.g. maven:com.google.guava:guava:33.0.0"
        )
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", group) or not re.fullmatch(r"[A-Za-z0-9_.-]+", artifact):
        raise SourceSpecError(f"Unsafe maven coordinates {group}:{artifact}")
    gpath = quote(group.replace(".", "/"), safe="/")
    meta_url = f"{_MAVEN_BASE}/{gpath}/{quote(artifact, safe='')}/maven-metadata.xml"
    fetched = await fetch_to_file(
        meta_url, staging, settings, filename=f"maven-{artifact}.xml", client=client,
        extra_headers={"Accept": "application/xml"},
    )
    try:
        root = ET.fromstring(fetched.path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SourceSpecError(f"Maven metadata for {group}:{artifact} is not valid XML: {exc}")
    versions = [
        (v.text or "").strip()
        for v in root.findall(".//versions/version")
        if (v.text or "").strip()
    ]
    requested = (parsed.version or "").strip()
    ctx = f"maven:{group}:{artifact}"
    if not versions:
        single = (root.findtext(".//versioning/version") or "").strip()
        versions = [single] if single else []
        if not versions and not requested:
            raise SourceSpecError(f"{ctx} has no version metadata")
    if requested and requested in versions:
        version = requested
    else:
        latest = (root.findtext(".//versioning/release") or root.findtext(".//versioning/latest") or "").strip() or None
        version = _pick_pypi_version(requested or None, versions, latest, ctx)
    _check_version_token(version, ctx)
    base = f"{_MAVEN_BASE}/{gpath}/{quote(artifact, safe='')}/{quote(version, safe='')}"
    qver = quote(version, safe="")
    sources_url = f"{base}/{quote(artifact, safe='')}-{qver}-sources.jar"
    plain_url = f"{base}/{quote(artifact, safe='')}-{qver}.jar"
    resolved = ParsedSource(
        kind="maven", raw=parsed.raw, url=sources_url, package=artifact,
        version=version, group=group, fallback_url=plain_url,
    )
    # The -sources.jar may not exist for every artifact; resolve_source
    # retries with fallback_url (the plain jar) when this 404s.
    return resolved, f"{artifact}-{version}-sources.jar"


async def _resolve_crates(parsed: ParsedSource, staging: Path, settings: Settings,
                          client: Optional[httpx.AsyncClient]) -> tuple[ParsedSource, str]:
    """Resolve ``crates:name@version`` via the crates.io API."""
    name = parsed.package or ""
    if not name or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise SourceSpecError("crates: source needs a crate name ([A-Za-z0-9_-]+)")
    ctx = f"crates:{name}"
    meta = await _fetch_json(
        f"https://crates.io/api/v1/crates/{name}/versions", staging, settings, client,
        filename=f"crates-{name}.json",
    )
    versions = [v.get("num") for v in (meta.get("versions") or []) if v.get("num")]
    version = _pick_semver_version(parsed.version, versions, latest=None, ctx=ctx)
    _check_version_token(version, ctx)
    url = f"https://crates.io/api/v1/crates/{name}/{quote(version, safe='')}/download"
    resolved = ParsedSource(kind="crates", raw=parsed.raw, url=url, package=name, version=version)
    return resolved, f"{name}-{version}.crate"


def _go_escape(module: str) -> str:
    """Go module proxy path escaping: each uppercase letter -> ``!lower``."""
    return "".join("!" + c.lower() if c.isupper() else c for c in module)


async def _resolve_go(parsed: ParsedSource, staging: Path, settings: Settings,
                      client: Optional[httpx.AsyncClient]) -> tuple[ParsedSource, str]:
    """Resolve ``go:module@version`` via proxy.golang.org."""
    module = parsed.package or ""
    if not module or module.startswith("/") or ".." in module.split("/"):
        raise SourceSpecError("go: source needs a module path, e.g. go:github.com/gin-gonic/gin@v1.9.1")
    ctx = f"go:{module}"
    esc = _go_escape(module)
    requested = (parsed.version or "").strip()
    if not requested or requested == "latest":
        meta = await _fetch_json(
            f"https://proxy.golang.org/{esc}/@latest", staging, settings, client,
            filename="go-latest.json",
        )
        version = meta.get("Version") or ""
        if not version:
            raise SourceSpecError(f"{ctx} has no @latest version")
    else:
        fetched = await fetch_to_file(
            f"https://proxy.golang.org/{esc}/@v/list", staging, settings,
            filename="go-version-list.txt", client=client,
            extra_headers={"Accept": "text/plain"},
        )
        versions = [ln.strip() for ln in fetched.path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        try:
            version = _pick_semver_version(requested, versions, latest=None, ctx=ctx)
        except SourceSpecError:
            # An exact pin the list does not know still gets a direct zip URL.
            _check_version_token(requested, ctx)
            version = requested
    _check_version_token(version, ctx)
    url = f"https://proxy.golang.org/{esc}/@v/{quote(version, safe='')}.zip"
    resolved = ParsedSource(kind="go", raw=parsed.raw, url=url, package=module, version=version)
    return resolved, f"{module.rsplit('/', 1)[-1]}-{version}.zip"


async def _resolve_nuget(parsed: ParsedSource, staging: Path, settings: Settings,
                         client: Optional[httpx.AsyncClient]) -> tuple[ParsedSource, str]:
    """Resolve ``nuget:id@version`` via the NuGet flat-container API."""
    pid = (parsed.package or "").strip()
    if not pid or not re.fullmatch(r"[A-Za-z0-9._-]+", pid):
        raise SourceSpecError("nuget: source needs a package id ([A-Za-z0-9._-]+)")
    low = pid.lower()
    ctx = f"nuget:{pid}"
    meta = await _fetch_json(
        f"https://api.nuget.org/v3-flatcontainer/{low}/index.json", staging, settings, client,
        filename=f"nuget-{low}.json",
    )
    versions = [v.lower() for v in (meta.get("versions") or [])]
    requested = (parsed.version or "").strip().lower()
    version = _pick_semver_version(requested or None, versions, latest=versions[-1] if versions else None, ctx=ctx)
    _check_version_token(version, ctx)
    url = f"https://api.nuget.org/v3-flatcontainer/{low}/{version}/{low}.{version}.nupkg"
    resolved = ParsedSource(kind="nuget", raw=parsed.raw, url=url, package=pid, version=version)
    return resolved, f"{pid}.{version}.nupkg"


async def _resolve_gem(parsed: ParsedSource, staging: Path, settings: Settings,
                       client: Optional[httpx.AsyncClient]) -> tuple[ParsedSource, str]:
    """Resolve ``gem:name@version`` via the RubyGems API."""
    name = (parsed.package or "").strip()
    if not name or not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        raise SourceSpecError("gem: source needs a gem name ([A-Za-z0-9._-]+)")
    ctx = f"gem:{name}"
    meta = await _fetch_json(
        f"https://rubygems.org/api/v1/versions/{quote(name, safe='')}.json", staging, settings, client,
        filename=f"gem-{name}.json",
    )
    versions = [v.get("number") or v.get("version") for v in (meta if isinstance(meta, list) else []) if (v.get("number") or v.get("version"))]
    requested = (parsed.version or "").strip()
    version = _pick_pypi_version(requested or None, versions, latest=None, ctx=ctx)
    _check_version_token(version, ctx)
    url = f"https://rubygems.org/downloads/{quote(name, safe='')}-{quote(version, safe='')}.gem"
    resolved = ParsedSource(kind="gem", raw=parsed.raw, url=url, package=name, version=version)
    return resolved, f"{name}-{version}.gem"


#: Registry resolvers keyed by ParsedSource.kind.
_REGISTRY_RESOLVERS = {
    "pypi": _resolve_pypi,
    "npm": _resolve_npm,
    "maven": _resolve_maven,
    "crates": _resolve_crates,
    "go": _resolve_go,
    "nuget": _resolve_nuget,
    "gem": _resolve_gem,
}


def _parse_git_url(url: str, raw: str, ref: Optional[str] = None) -> ParsedSource:
    """A bare ``https://host/.../repo.git`` URL (or ``git+``-prefixed) -> git kind."""
    name = url.rstrip("/").rsplit("/", 1)[-1]
    if name.endswith(".git"):
        name = name[:-4]
    name = re.sub(r"[^A-Za-z0-9._-]", "-", name) or "repo"
    return ParsedSource(kind="git", raw=raw, url=url, repo=name, ref=ref)


def _parse_git_spec(spec: str) -> ParsedSource:
    """Parse ``git+https://host/path/repo.git[@ref]``."""
    rest = spec[len("git+"):]
    url, ref = _split_pkg_version(rest)  # last @ after the last /
    scheme = url.split("://", 1)[0].lower() if "://" in url else ""
    if scheme not in ("https", "http"):
        raise SourceSpecError(
            f"git clone supports https URLs only, got {scheme or 'none'!r} in {spec!r} "
            "(ssh URLs are not supported)"
        )
    return _parse_git_url(url, spec, ref)


async def _resolve_git(parsed: ParsedSource, dest_dir: Path, settings: Settings) -> ResolvedSource:
    """
    Clone a git repo into the bundle dir (depth 1, single branch when a ref
    is given).  The URL goes through the same SSRF policy as URL intake
    before any subprocess runs; a failed clone leaves nothing behind.
    """
    if not getattr(settings, "allow_git_clone", True):
        raise SourceSpecError("Git clone intake is disabled (CAUVERIS_ALLOW_GIT_CLONE=false)")
    url = parsed.url or ""
    validate_url(url, settings)  # https only, no userinfo, host allowlist, DNS check
    if shutil.which("git") is None:
        raise SourceSpecError(
            "git is not installed in this deployment; install git in the runtime image "
            "or set CAUVERIS_ALLOW_GIT_CLONE=false"
        )
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    clone_dir = dest_dir / (parsed.repo or "repo")
    cmd = ["git", "clone", "--depth", "1"]
    if parsed.ref:
        cmd += ["--single-branch", "--branch", parsed.ref]
    cmd += [url, str(clone_dir)]
    timeout = float(getattr(settings, "git_clone_timeout_seconds", 120))
    try:
        # Runs in a worker thread so a slow clone never blocks the event loop.
        proc = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        shutil.rmtree(clone_dir, ignore_errors=True)
        raise SourceSpecError(f"git clone of {url!r} timed out after {timeout:.0f}s")
    except OSError as exc:
        raise SourceSpecError(f"git clone failed to start: {exc}")
    if proc.returncode != 0:
        shutil.rmtree(clone_dir, ignore_errors=True)
        lines = (proc.stderr or proc.stdout or "").strip().splitlines()
        detail = lines[-1][:300] if lines else "unknown error"
        raise SourceSpecError(f"git clone of {url!r} failed: {detail}")
    # Record the commit before dropping .git from the bundle.
    commit = ""
    try:
        rev = await asyncio.to_thread(
            subprocess.run,
            ["git", "-C", str(clone_dir), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30,
        )
        if rev.returncode == 0:
            commit = rev.stdout.strip()
    except Exception:
        pass

    def _onerror(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass

    shutil.rmtree(clone_dir / ".git", onerror=_onerror)

    digest = _hash_bundle_dir(clone_dir)
    size = sum(p.stat().st_size for p in clone_dir.rglob("*") if p.is_file())
    descriptor: Dict[str, Any] = {
        "kind": "git",
        "spec": parsed.raw,
        "requested_url": url,
        "ref": parsed.ref or "HEAD",
        "commit": commit,
        "repo": parsed.repo,
        "filename": parsed.repo or "repo",
        "size_bytes": size,
        "sha256": digest,
        "payload_kind": "git",
    }
    return ResolvedSource(
        bundle_dir=clone_dir,
        source_kind="git",
        descriptor=descriptor,
        warnings=[],
        package_sha256=digest,
        size_bytes=size,
        filename=parsed.repo or "repo",
    )


async def resolve_source(
    spec: str,
    dest_dir: Path,
    settings: Optional[Settings] = None,
    *,
    client: Optional[httpx.AsyncClient] = None,
    allow_local: bool = True,
) -> ResolvedSource:
    """
    Resolve any supported source spec into a bundle directory under ``dest_dir``.

    ``allow_local`` must be False for API-driven intake unless
    ``CAUVERIS_ALLOW_LOCAL_PATH_INGEST=true`` - letting an HTTP caller read
    server-local paths would be a file-disclosure hole.  The CLI always
    passes True.
    """
    settings = settings or get_settings()
    parsed = parse_source(spec, settings)

    if parsed.kind in ("local_file", "local_dir"):
        if not allow_local and not settings.allow_local_path_ingest:
            raise SourceSpecError(
                "Local path intake is disabled for API callers "
                "(set CAUVERIS_ALLOW_LOCAL_PATH_INGEST=true to enable)"
            )
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        if parsed.kind == "local_dir":
            warnings = _copy_local_dir(parsed.local_path, dest_dir, settings)
            return ResolvedSource(
                bundle_dir=dest_dir,
                source_kind="local_dir",
                descriptor={
                    "kind": "local_dir",
                    "spec": parsed.raw,
                    "path": str(parsed.local_path),
                    "sha256": _hash_bundle_dir(dest_dir),
                },
                warnings=warnings,
                package_sha256=_hash_bundle_dir(dest_dir),
                size_bytes=sum(p.stat().st_size for p in dest_dir.rglob("*") if p.is_file()),
                filename=Path(parsed.local_path).name,
            )
        # local single file
        bundle_root, kind, warnings = materialize_payload(parsed.local_path, dest_dir, settings)
        digest = _hash_file(parsed.local_path)
        return ResolvedSource(
            bundle_dir=bundle_root,
            source_kind=kind,
            descriptor={
                "kind": "local_file",
                "spec": parsed.raw,
                "path": str(parsed.local_path),
                "sha256": digest,
            },
            warnings=warnings,
            package_sha256=digest,
            size_bytes=parsed.local_path.stat().st_size,
            filename=parsed.local_path.name,
        )

    # Remote sources.
    if not settings.url_ingestion_enabled:
        raise SourceSpecError("URL ingestion is disabled (CAUVERIS_URL_INGESTION_ENABLED=false)")

    if parsed.kind == "git":
        return await _resolve_git(parsed, Path(dest_dir), settings)

    # Each resolution stages into its own unique directory, so two concurrent
    # ingests of the same package never clobber each other's metadata or
    # download mid-read.  The staging dir is always removed in the finally.
    staging_base = Path(settings.evidence_store_path).parent / "temp_ingestion" / "downloads"
    staging = staging_base / uuid.uuid4().hex
    staging.mkdir(parents=True, exist_ok=True)
    try:
        download_url = parsed.url
        filename: Optional[str] = None
        if parsed.kind in _REGISTRY_RESOLVERS and parsed.url is None:
            parsed, filename = await _REGISTRY_RESOLVERS[parsed.kind](parsed, staging, settings, client)
            download_url = parsed.url
        elif parsed.kind == "github" and parsed.url and "codeload" not in parsed.url:
            filename = Path(urlsplit(parsed.url).path).name or None
        elif parsed.kind == "github":
            filename = f"{parsed.repo}-{parsed.ref or 'HEAD'}.zip"

        assert download_url is not None
        try:
            fetched: FetchedFile = await fetch_to_file(
                download_url, staging, settings, filename=filename, client=client
            )
        except SourceFetchError:
            # Maven's -sources.jar does not exist for every artifact; fall
            # back to the plain jar before giving up.
            if parsed.kind == "maven" and parsed.fallback_url:
                download_url = parsed.fallback_url
                filename = Path(urlsplit(download_url).path).name or None
                fetched = await fetch_to_file(
                    download_url, staging, settings, filename=filename, client=client
                )
            else:
                raise

        dest_dir = Path(dest_dir)
        bundle_root, kind, warnings = materialize_payload(fetched.path, dest_dir, settings)

        descriptor: Dict[str, Any] = {
            "kind": parsed.kind,
            "spec": parsed.raw,
            "requested_url": download_url,
            "final_url": fetched.final_url,
            "redirected": fetched.final_url != download_url,
            "filename": fetched.path.name,
            "size_bytes": fetched.size_bytes,
            "sha256": fetched.sha256,
            "content_type": fetched.content_type,
            "payload_kind": kind,
        }
        if parsed.owner and parsed.repo:
            descriptor.update({"owner": parsed.owner, "repo": parsed.repo, "ref": parsed.ref or "HEAD"})
        if parsed.package:
            descriptor.update({"package": parsed.package, "version": parsed.version})

        return ResolvedSource(
            bundle_dir=bundle_root,
            source_kind=kind,
            descriptor=descriptor,
            warnings=warnings,
            package_sha256=fetched.sha256,
            size_bytes=fetched.size_bytes,
            filename=fetched.path.name,
        )
    finally:
        # The bundle dir now holds the content; the staged download is dropped.
        shutil.rmtree(staging, ignore_errors=True)
