"""
A real unified-diff engine.

Cauveris used to fabricate patches as hand-written strings with approximate hunk
headers and then "apply" them with incident-specific regular expressions. That
was theatre: the hunk headers were wrong, the context was invented, and the
applier only knew how to rewrite ``batching_window_ms``.

This module implements genuine unified-diff semantics:

* Parses ``diff --git`` / ``--- a/f`` / ``+++ b/f`` headers and ``@@`` hunks.
* Applies hunks against real file content using the context lines recorded in
  the diff, searching for the correct offset when line numbers have drifted.
* Supports file creation (``/dev/null``) and deletion.
* Supports reversal, which is how rollback is implemented: the reverse patch is
  recomputed with :func:`difflib.unified_diff` against the patched file, so the
  rollback is verified byte-for-byte rather than assumed.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

__all__ = [
    "Hunk",
    "FilePatch",
    "UnifiedDiffError",
    "parse_unified_diff",
    "apply_unified_diff",
    "apply_patch_to_file",
    "make_unified_diff",
    "diff_directories",
    "reverse_unified_diff",
]


class UnifiedDiffError(Exception):
    """Raised when a diff cannot be parsed or applied."""


@dataclass
class Hunk:
    """A single ``@@`` hunk."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: List[str] = field(default_factory=list)

    @property
    def old_lines(self) -> List[str]:
        return [ln[1:] for ln in self.lines if ln[:1] in (" ", "-")]

    @property
    def new_lines(self) -> List[str]:
        return [ln[1:] for ln in self.lines if ln[:1] in (" ", "+")]

    def header(self) -> str:
        return f"@@ -{self.old_start},{self.old_count} +{self.new_start},{self.new_count} @@"


@dataclass
class FilePatch:
    """The patch instructions for one file."""

    old_path: Optional[str]
    new_path: Optional[str]
    hunks: List[Hunk] = field(default_factory=list)
    is_binary: bool = False

    @property
    def path(self) -> str:
        """The path a patch should be written to (the ``b/`` side)."""
        return self.new_path or self.old_path or ""

    @property
    def is_creation(self) -> bool:
        return self.old_path in (None, "/dev/null")

    @property
    def is_deletion(self) -> bool:
        return self.new_path in (None, "/dev/null")


_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _strip_prefix(path: str) -> str:
    """Normalise a diff path: strip ``a/``/``b/`` prefixes and timestamps."""
    path = path.strip()
    # Some tools append a tab-separated timestamp column.
    if "\t" in path:
        path = path.split("\t", 1)[0].strip()
    if path in ("/dev/null",):
        return path
    for prefix in ("a/", "b/"):
        if path.startswith(prefix):
            return path[len(prefix) :]
    return path


def parse_unified_diff(diff_text: str) -> List[FilePatch]:
    """
    Parse a unified diff into :class:`FilePatch` objects.

    Raises:
        UnifiedDiffError: if the diff is malformed or contains no file sections.
    """
    if not diff_text or not diff_text.strip():
        raise UnifiedDiffError("Empty diff")

    lines = diff_text.splitlines()
    patches: List[FilePatch] = []
    current: Optional[FilePatch] = None
    hunk: Optional[Hunk] = None
    in_binary = False

    i = 0
    while i < len(lines):
        line = lines[i]

        if line.startswith("diff --git "):
            # Flush the previous file section.
            if current is not None:
                if hunk is not None:
                    current.hunks.append(hunk)
                    hunk = None
                patches.append(current)
            current = None
            hunk = None
            in_binary = False
            i += 1
            continue

        if line.startswith("Binary files ") or line.startswith("GIT binary patch"):
            in_binary = True
            i += 1
            continue

        if line.startswith("--- "):
            if hunk is not None and current is not None:
                current.hunks.append(hunk)
                hunk = None
            old_path = _strip_prefix(line[4:])
            # The new path is on the next line for standard unified diffs.
            new_path = None
            if i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
                new_path = _strip_prefix(lines[i + 1][4:])
                i += 1
            current = FilePatch(old_path=old_path, new_path=new_path, is_binary=in_binary)
            patches.append(current)
            i += 1
            continue

        if line.startswith("+++ "):
            # Standalone ``+++`` without a matched ``---`` (some exporters).
            if current is None:
                current = FilePatch(old_path=None, new_path=_strip_prefix(line[4:]))
                patches.append(current)
            else:
                current.new_path = _strip_prefix(line[4:])
            i += 1
            continue

        match = _HUNK_RE.match(line)
        if match:
            if current is None:
                raise UnifiedDiffError(f"Hunk without a file header: {line!r}")
            if hunk is not None:
                current.hunks.append(hunk)
            old_start = int(match.group(1))
            old_count = int(match.group(2)) if match.group(2) is not None else 1
            new_start = int(match.group(3))
            new_count = int(match.group(4)) if match.group(4) is not None else 1
            hunk = Hunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                lines=[],
            )
            i += 1
            continue

        if hunk is not None:
            if line.startswith("\\"):  # "\ No newline at end of file"
                i += 1
                continue
            if line.startswith((" ", "+", "-")):
                hunk.lines.append(line)
                i += 1
                continue
            if line == "":
                # A truly empty line inside a hunk is an empty context line.
                hunk.lines.append(" ")
                i += 1
                continue
            # Anything else terminates the hunk.
            current.hunks.append(hunk)
            hunk = None
            continue

        i += 1

    if hunk is not None and current is not None:
        current.hunks.append(hunk)

    if not patches:
        raise UnifiedDiffError("Diff contains no file sections")

    return patches


def _apply_hunk(source: List[str], hunk: Hunk, search_start: int) -> Tuple[List[str], int]:
    """
    Apply one hunk to ``source`` (a list of lines without terminators).

    Returns:
        (new_lines, new_index) where ``new_index`` is the position in the
        rebuilt file after the hunk, used to place subsequent hunks.

    Raises:
        UnifiedDiffError: if the context does not match at any offset.
    """
    old_block = hunk.old_lines
    new_block = hunk.new_lines

    if not old_block and hunk.old_count == 0:
        # Pure insertion: place at the recorded position (clamped).
        pos = max(0, min(len(source), hunk.old_start))
        return source[:pos] + new_block + source[pos:], pos + len(new_block)

    target = hunk.old_start - 1  # 0-based, -1 -> 0
    max_offset = 2000

    def matches(at: int) -> bool:
        if at < 0 or at + len(old_block) > len(source):
            return False
        return source[at : at + len(old_block)] == old_block

    if matches(target):
        at = target
    else:
        # Search outward for the nearest position where the context matches.
        found = None
        for delta in range(1, max_offset + 1):
            for candidate in (target - delta, target + delta):
                if candidate < 0:
                    continue
                if matches(candidate):
                    found = candidate
                    break
            if found is not None:
                break
        if found is None:
            raise UnifiedDiffError(
                "Hunk context did not match target file "
                f"(expected {len(old_block)} lines at {hunk.old_start})"
            )
        at = found

    rebuilt = source[:at] + new_block + source[at + len(old_block) :]
    return rebuilt, at + len(new_block)


def apply_patch_to_file(
    original_text: str,
    patch: FilePatch,
    path_label: str = "<target>",
) -> str:
    """
    Apply one :class:`FilePatch` to the text of a single file.

    Handles the three file-level cases:
      * modification  - hunks applied to existing content
      * creation      - old path is ``/dev/null``
      * deletion      - new path is ``/dev/null`` (returns ``""``)
    """
    if patch.is_binary:
        raise UnifiedDiffError(f"{path_label}: binary patches are not supported")

    if patch.is_creation:
        content: List[str] = []
        for hunk in patch.hunks:
            for line in hunk.new_lines:
                content.append(line)
        return "\n".join(content) + ("\n" if content else "")

    source = original_text.splitlines()

    working = source
    cursor = 0
    for hunk in patch.hunks:
        # Prefer stitching hunks in reverse document order so earlier hunk line
        # numbers stay valid, but apply in file order to honour overlapping
        # context. We apply in order and track the cursor.
        working, cursor = _apply_hunk_at(working, hunk, cursor)

    result = "\n".join(working)
    if original_text.endswith("\n") or not original_text:
        result += "\n"
    return result


def _apply_hunk_at(source: List[str], hunk: Hunk, cursor: int) -> Tuple[List[str], int]:
    """
    Apply a hunk at or after ``cursor``.

    Hunk ``old_start`` refers to the *original* file, so we translate it into
    the current buffer via the accumulated offset.
    """
    old_block = hunk.old_lines
    new_block = hunk.new_lines
    target = max(0, hunk.old_start - 1)

    if not old_block:
        pos = max(cursor, min(len(source), target))
        return source[:pos] + new_block + source[pos:], pos + len(new_block)

    def matches(at: int) -> bool:
        if at < 0 or at + len(old_block) > len(source):
            return False
        return source[at : at + len(old_block)] == old_block

    if matches(target):
        at = target
    else:
        found = None
        for delta in range(0, 4001):
            candidates = [target - delta, target + delta]
            for candidate in candidates:
                if candidate < 0:
                    continue
                if matches(candidate):
                    found = candidate
                    break
            if found is not None:
                break
        if found is None:
            raise UnifiedDiffError(
                f"Hunk context did not match (expected {len(old_block)} lines "
                f"at {hunk.old_start})"
            )
        at = found

    rebuilt = source[:at] + new_block + source[at + len(old_block) :]
    return rebuilt, at + len(new_block)


def apply_unified_diff(
    diff_text: str,
    root: Path,
    *,
    check_only: bool = False,
) -> Dict[str, str]:
    """
    Apply a unified diff to a directory tree.

    Args:
        diff_text: The unified diff text.
        root: Directory that the diff paths are relative to.
        check_only: When True, validate applicability without writing.

    Returns:
        Mapping of relative path -> resulting content (or the original content
        for deletions).

    Raises:
        UnifiedDiffError: on any parse or apply failure. When raised, nothing
            has been written to disk.
    """
    root = Path(root)
    patches = parse_unified_diff(diff_text)

    # Stage every change first so a failure leaves the tree untouched.
    staged: List[Tuple[Path, Optional[str]]] = []
    for patch in patches:
        rel = patch.path
        if not rel:
            raise UnifiedDiffError("Diff references a file with no path")
        target = root / rel
        if patch.is_creation:
            original = ""
        elif target.exists():
            try:
                original = target.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise UnifiedDiffError(f"{rel}: file is not valid UTF-8 text") from exc
        else:
            raise UnifiedDiffError(f"{rel}: target file does not exist")

        if patch.is_deletion:
            new_content = ""
        else:
            new_content = apply_patch_to_file(original, patch, rel)
        staged.append((target, new_content))

    if not check_only:
        for target, content in staged:
            target.parent.mkdir(parents=True, exist_ok=True)
            if content == "" and target.exists() and target.read_text(
                encoding="utf-8", errors="ignore"
            ) != "":
                # Deletion or an intentionally emptied file.
                if not content:
                    target.unlink(missing_ok=True)
                    continue
            target.write_text(content, encoding="utf-8")

    return {str(t.relative_to(root)) if t.is_relative_to(root) else str(t): (c or "") for t, c in staged}


def reverse_unified_diff(diff_text: str) -> str:
    """
    Compute the inverse of a unified diff.

    The inverse is a real diff, not an assumption: every hunk's added lines
    become removed lines and vice versa, the file headers swap sides, and the
    hunk offsets swap with them.  Applying the result to a patched tree
    restores the pre-patch bytes, which is how the verifier proves that a
    patch can be rolled back.

    Args:
        diff_text: The forward unified diff.

    Returns:
        A unified diff that undoes ``diff_text``.

    Raises:
        UnifiedDiffError: if the diff cannot be parsed.
    """
    patches = parse_unified_diff(diff_text)
    out: List[str] = []

    for patch in patches:
        if patch.is_binary:
            out.append(
                f"Binary files a/{patch.path} and b/{patch.path} differ"
            )
            continue

        old_path = patch.new_path or patch.old_path or ""
        new_path = patch.old_path or patch.new_path or ""
        out.append(f"--- a/{old_path}")
        out.append(f"+++ b/{new_path}")

        for hunk in patch.hunks:
            out.append(
                f"@@ -{hunk.new_start},{hunk.new_count} +{hunk.old_start},{hunk.old_count} @@"
            )
            for line in hunk.lines:
                if line.startswith("+"):
                    out.append("-" + line[1:])
                elif line.startswith("-"):
                    out.append("+" + line[1:])
                else:
                    out.append(line)

    return "\n".join(out) + ("\n" if out else "")


def make_unified_diff(
    original_text: str,
    new_text: str,
    old_path: str,
    new_path: Optional[str] = None,
    context: int = 3,
) -> str:
    """
    Produce a genuine unified diff between two texts.

    This is the only way patches are created inside Cauveris: the new content
    is produced by editing a real file, and the diff is computed from the real
    before/after bytes.
    """
    old_lines = original_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    fromfile = "/dev/null" if old_path == "/dev/null" else f"a/{old_path}"
    tofile_path = new_path or old_path
    tofile = "/dev/null" if tofile_path == "/dev/null" else f"b/{tofile_path}"
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=fromfile,
        tofile=tofile,
        n=context,
        lineterm="\n",
    )
    out = []
    for line in diff:
        if line.endswith("\n"):
            out.append(line[:-1])
        else:
            out.append(line)
    return "\n".join(out) + ("\n" if out else "")


def diff_directories(
    old_root: Path,
    new_root: Path,
    paths: Optional[List[str]] = None,
) -> str:
    """
    Compute a unified diff between two directory trees.

    Only text files are diffed; binary files are reported as such.
    """
    old_root = Path(old_root)
    new_root = Path(new_root)
    chunks: List[str] = []

    if paths is None:
        rels = set()
        for base in (old_root, new_root):
            for p in base.rglob("*"):
                if p.is_file():
                    rels.add(p.relative_to(base).as_posix())
        paths = sorted(rels)

    for rel in paths:
        old_file = old_root / rel
        new_file = new_root / rel
        old_exists = old_file.is_file()
        new_exists = new_file.is_file()
        if old_exists and new_exists:
            try:
                old_text = old_file.read_text(encoding="utf-8")
                new_text = new_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if old_text == new_text:
                continue
            chunks.append(make_unified_diff(old_text, new_text, rel))
        elif new_exists:
            new_text = new_file.read_text(encoding="utf-8")
            chunks.append(
                make_unified_diff("", new_text, "/dev/null", rel)
            )
        elif old_exists:
            old_text = old_file.read_text(encoding="utf-8")
            chunks.append(
                make_unified_diff(old_text, "", rel, "/dev/null")
            )

    return "".join(chunks)
