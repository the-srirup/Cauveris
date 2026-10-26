"""
Locating a pipeline parameter inside a real configuration file.

Cauveris has to answer three questions about a configuration file that ships
with an incident bundle:

1. *Which key controls the batching window?*  The answer is found from the
   **shape of the key**, not from a table of known file names, so a bundle
   that calls it ``dynamic_batching.max_delay_ms`` is understood exactly as
   well as one that calls it ``batching_window_ms``.
2. *What value does the key have right now?*
3. *What does the file look like after the key is changed?*

The third question is the one that decides whether a patch is real.  A patch
is a **diff between two real byte sequences**: the file as the bundle shipped
it, and the file with the key changed.  This module produces the second
sequence by editing the first in place - one scalar, in place, with the
surrounding indentation, the trailing comment and every other key left
exactly as they were.

Nothing here knows an incident id or a file name.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

from .parameter_registry import PARAMETER_REGISTRY, needles_for

__all__ = [
    "PARAMETER_NEEDLES",
    "match_parameter",
    "flatten_config",
    "config_parameter_entries",
    "yaml_scalar_lines",
    "split_trailing_comment",
    "reconcile_trailing_comment",
    "replace_yaml_scalar",
    "replace_json_scalar",
    "sectioned_config_entries",
    "replace_sectioned_scalar",
    "parse_config_file",
    "parse_config_text",
    "is_packaging_file",
    "source_parameter_entries",
    "replace_source_scalar",
    "find_parameter_in_tree",
    "find_parameter_in_file",
    "CONFIG_SUFFIXES",
    "SECTIONED_CONFIG_SUFFIXES",
]

#: A configuration key maps onto a pipeline parameter when its name contains
#: one of these needles.  The order matters: the first match wins, so the
#: specific names are checked before the general ones.
#:
#: The list is derived from :mod:`cauveris.analysis.parameter_registry`, which
#: is the single source of truth for every parameter the pipeline can
#: simulate.  Adding a parameter to the registry makes it locatable here, in
#: the twin and in the verifier at the same time.
PARAMETER_NEEDLES: Tuple[Tuple[str, Tuple[str, ...]], ...] = needles_for(
    tuple(PARAMETER_REGISTRY.keys())
)


def match_parameter(key: str) -> Optional[str]:
    """
    The pipeline parameter a configuration key controls, if any.

    The key is matched on its last dotted component and on the full dotted
    path, so ``dynamic_batching.batching_window_ms`` and ``batching_window_ms``
    both resolve to ``batching_window_ms``.

    A parameter may exclude keys explicitly.  Several deadlines live in the
    same configuration and they are not interchangeable: a control loop's
    deadline is the watchdog budget and a transform lookup's deadline belongs
    to another subsystem, and neither is the deadline a caller puts on the
    request.  Reading one as the other would let a patch shorten a safety
    budget, so the excluded forms are skipped rather than matched.
    """
    if not key:
        return None
    lowered = str(key).lower()
    components = [part for part in lowered.split(".") if part]
    candidates = [components[-1]] if components else []
    candidates.append(lowered)
    for parameter, needles in PARAMETER_NEEDLES:
        spec = PARAMETER_REGISTRY.get(parameter)
        if spec is not None and spec.excluded_needles:
            if any(
                excluded in candidate
                for candidate in candidates
                for excluded in spec.excluded_needles
            ):
                continue
        for candidate in candidates:
            for needle in needles:
                if needle in candidate:
                    return parameter
    return None


def coerce_number(value: Any) -> Optional[float]:
    """Return ``value`` as a float when it plausibly is a number."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def flatten_config(data: Any, prefix: str = "") -> Dict[str, Any]:
    """Flatten a nested mapping into dotted keys."""
    flat: Dict[str, Any] = {}
    if not isinstance(data, dict):
        return flat
    for key, value in data.items():
        full = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(flatten_config(value, f"{full}."))
        else:
            flat[full] = value
    return flat


def config_parameter_entries(data: Any) -> Dict[str, List[Tuple[str, Any]]]:
    """
    Every pipeline parameter a parsed configuration declares.

    Returns:
        Mapping of parameter name -> list of ``(dotted key, value)`` pairs.
        A parameter can be declared more than once; every declaration is
        reported, because a patch has to change all of them or none.
    """
    entries: Dict[str, List[Tuple[str, Any]]] = {}
    for key, value in flatten_config(data).items():
        parameter = match_parameter(key)
        if parameter is None:
            continue
        entries.setdefault(parameter, []).append((key, value))
    return entries


# ---------------------------------------------------------------------------
# YAML text editing
# ---------------------------------------------------------------------------

#: ``key: value`` at a given indentation, with an optional trailing comment.
_YAML_ASSIGNMENT_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<key>[A-Za-z0-9_.\-]+)\s*:\s*(?P<rest>.*)$"
)
#: A quoted or bare scalar at the end of a YAML line.
_YAML_SCALAR_RE = re.compile(
    r"^(?P<value>\"[^\"]*\"|'[^']*'|[^#]*?)\s*(?P<comment>#.*)?$"
)


def yaml_scalar_lines(text: str) -> List[Tuple[int, str, str, int, int]]:
    """
    Every scalar assignment in a YAML document.

    Returns:
        A list of ``(line index, dotted key, raw value text, value start,
        value end)``.  The dotted key is the full path of the scalar, so
        ``batching_window_ms`` inside ``dynamic_batching`` is reported as
        ``dynamic_batching.batching_window_ms``.  The offsets locate the
        value inside the line, so a patch replaces the value and nothing else.

    Mappings and sequences are skipped: a patch changes a scalar, not a
    structure, and rewriting a structure would change far more of the file
    than the fix requires.
    """
    results: List[Tuple[int, str, str, int, int]] = []
    # Stack of (indent, key) for the open mappings.
    stack: List[Tuple[int, str]] = []

    for index, line in enumerate(text.splitlines()):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            # A sequence item: its scalars belong to the enclosing mapping,
            # not to a path of their own.
            continue

        match = _YAML_ASSIGNMENT_RE.match(line)
        if not match:
            continue

        indent = len(match.group("indent").expandtabs(2))
        key = match.group("key")
        raw_rest = match.group("rest")
        rest = raw_rest.strip()

        while stack and stack[-1][0] >= indent:
            stack.pop()
        path = ".".join([entry[1] for entry in stack] + [key])

        if not rest:
            stack.append((indent, key))
            continue

        scalar = _YAML_SCALAR_RE.match(rest)
        value_text = (scalar.group("value") if scalar else rest).strip()
        if not value_text:
            continue
        # Locate the value inside the line: the raw text after the separator,
        # plus the offset of the scalar within it.
        offset = raw_rest.find(value_text)
        if offset < 0:
            offset = 0
        start = match.start("rest") + offset
        results.append((index, path, value_text, start, start + len(value_text)))

    return results


def _format_scalar(value: Any) -> str:
    """Render a value the way it is written in the file."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def split_trailing_comment(line: str) -> Tuple[str, str]:
    """
    Split a line into its content and its trailing comment.

    A ``#`` only starts a comment when it is outside quotes and preceded by
    whitespace, so a colour, a URL fragment or a number sign inside a string
    is left alone.

    Returns:
        ``(content, comment)``; the comment includes its ``#`` and is empty
        when the line carries none.
    """
    in_single = False
    in_double = False
    index = 0
    while index < len(line):
        char = line[index]
        if char == "\\" and in_double:
            index += 2
            continue
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            if index == 0 or line[index - 1] in " \t":
                return line[:index], line[index:]
        index += 1
    return line, ""


def reconcile_trailing_comment(
    tail: str, previous: Any, new_value: Any
) -> str:
    """
    Keep a trailing comment true after the value it decorates changes.

    A comment that mentions a number documents how the value got there, so
    changing the value can make it false - a config reading
    ``batching_window_ms: 100  # Increased from 100 in v42`` says something
    untrue about itself.  Dropping the operator's note loses the history it
    carries, so instead the change Cauveris made is stated as well and the
    original wording is kept.

    Arguments:
        tail: The text after the value on the line - spacing and comment.
        previous: The value the line had.
        new_value: The value the line now has.

    Returns:
        The tail, with the change appended when it can be stated truthfully.
    """
    stripped = tail.strip()
    if not stripped.startswith("#"):
        return tail
    body = stripped[1:].strip()
    if not re.search(r"\d", body):
        # Nothing numeric in it, so nothing in it can have become untrue.
        return tail
    if "by cauveris" in body.lower():
        return tail
    try:
        old_number = float(previous)
        new_number = float(new_value)
    except (TypeError, ValueError):
        return tail
    if old_number == new_number:
        return tail
    direction = "reduced" if new_number < old_number else "raised"
    return (
        tail.rstrip()
        + f"; {direction} from {_format_scalar(old_number)} by Cauveris"
    )


def replace_yaml_scalar(
    text: str, dotted_key: str, new_value: Any
) -> Optional[Tuple[str, Any]]:
    """
    Change one scalar in a YAML document, leaving everything else alone.

    The indentation, the trailing comment and every other key are preserved:
    the resulting file is the original file with one number changed, which is
    what makes the diff between them a one-line diff.

    A trailing comment that documents the old value is kept truthful - see
    :func:`reconcile_trailing_comment`.

    Returns:
        ``(new text, previous value)``, or ``None`` when the key is not a
        scalar of this document.
    """
    lines = text.splitlines()
    for index, path, value_text, start, end in yaml_scalar_lines(text):
        if path != dotted_key:
            continue
        previous = _parse_yaml_scalar(value_text)
        if previous is None:
            continue
        line = lines[index]
        # Keep the original quoting style if the value was quoted.
        rendered = _format_scalar(new_value)
        if len(value_text) >= 2 and value_text[0] == value_text[-1] == '"':
            rendered = f'"{rendered}"'
        elif len(value_text) >= 2 and value_text[0] == value_text[-1] == "'":
            rendered = f"'{rendered}'"
        tail = reconcile_trailing_comment(line[end:], previous, new_value)
        lines[index] = line[:start] + rendered + tail
        return "\n".join(lines) + ("\n" if text.endswith("\n") else ""), previous
    return None


def _parse_yaml_scalar(text: str) -> Any:
    """The value a raw YAML scalar denotes."""
    try:
        return yaml.safe_load(text)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# JSON text editing
# ---------------------------------------------------------------------------


def replace_json_scalar(
    text: str, dotted_key: str, new_value: Any
) -> Optional[Tuple[str, Any]]:
    """
    Change one scalar in a JSON document.

    The document is re-serialised, so the formatting follows the file's own
    indentation where it can be recovered and is otherwise canonical JSON.
    The diff is computed from the real bytes either way.

    Returns:
        ``(new text, previous value)``, or ``None`` when the key is absent.
    """
    try:
        data = json.loads(text)
    except Exception:
        return None
    flat = flatten_config(data)
    if dotted_key not in flat:
        return None
    previous = flat[dotted_key]
    node = data
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        node = node.get(part) if isinstance(node, dict) else None
        if node is None:
            return None
    if not isinstance(node, dict) or parts[-1] not in node:
        return None
    node[parts[-1]] = new_value
    indent = 2
    for line in text.splitlines()[:1]:
        stripped = line.lstrip()
        if stripped and not stripped.startswith("{"):
            indent = len(line) - len(stripped)
            break
    return json.dumps(data, indent=max(1, indent)) + "\n", previous


# ---------------------------------------------------------------------------
# Sectioned configuration text - TOML and INI
#
# A robot whose parameters ship as ``robot.toml`` or ``robot.ini`` declares
# them the same way: a ``[section]`` header followed by ``key = value`` lines.
# The keys are reported in the same dotted shape a nested YAML document
# produces, so the rest of the pipeline does not need to know which format the
# customer's robot happens to use.
# ---------------------------------------------------------------------------

#: A section header: ``[dynamic_batching]``.
_SECTION_HEADER_RE = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*$")

#: A ``key = value`` assignment, with the indentation and the spacing kept so
#: that the value can be replaced without disturbing the rest of the line.
_SECTION_LINE_RE = re.compile(
    r"^(?P<indent>\s*)(?P<key>[A-Za-z0-9_.\-]+)(?P<gap>\s*=\s*)(?P<value>.*)$"
)


def _split_sectioned_value(rest: str) -> Tuple[str, str]:
    """
    Split the right-hand side of a sectioned assignment.

    Returns:
        ``(value text, tail)``.  The tail is everything that follows the
        value - the gap and the trailing comment - so that a patched line is
        byte-identical to the original except for the number.
    """
    text = rest
    if text[:1] in ("'", '"'):
        quote = text[0]
        end = text.find(quote, 1)
        if end != -1:
            return text[: end + 1], text[end + 1 :]
    for marker in ("#", ";"):
        index = text.find(marker)
        if index != -1:
            head = text[:index]
            value = head.rstrip()
            return value, head[len(value) :] + text[index:]
    value = text.rstrip()
    return value, text[len(value) :]


def _parse_sectioned_scalar(text: str) -> Any:
    """The value a sectioned assignment's raw text denotes."""
    value = text.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    lowered = value.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def sectioned_config_entries(text: str) -> List[Tuple[str, Any]]:
    """
    Every key a sectioned configuration file declares.

    Returns:
        A list of ``(dotted key, value)`` pairs.  A key declared inside a
        section is reported as ``section.key``; a key declared at the top
        level is reported as it stands.
    """
    entries: List[Tuple[str, Any]] = []
    section = ""
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        header = _SECTION_HEADER_RE.match(raw_line)
        if header:
            section = header.group("name").strip()
            continue
        match = _SECTION_LINE_RE.match(raw_line)
        if not match:
            continue
        key = match.group("key")
        dotted = f"{section}.{key}" if section else key
        value_text, _tail = _split_sectioned_value(match.group("value"))
        entries.append((dotted, _parse_sectioned_scalar(value_text)))
    return entries


def _same_dotted_key(found: str, wanted: str) -> bool:
    """
    Whether two dotted keys name the same assignment.

    A key given without its section matches the first declaration of that
    name; a key given *with* a section matches only that declaration, because
    a file may declare the same name under two sections and only one of them
    is the knob the patch means.
    """
    if found == wanted:
        return True
    return "." not in wanted and found.rsplit(".", 1)[-1] == wanted


def _coerce_config_value(value: Any) -> Any:
    """A configuration value with the type it denotes."""
    if not isinstance(value, str):
        return value
    lowered = value.strip().lower()
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _parse_ini(text: str) -> Optional[Dict[str, Any]]:
    """An INI file as a nested mapping."""
    import configparser

    parser = configparser.ConfigParser()
    try:
        parser.read_string(text)
    except Exception:
        # Keys declared before any section header are still configuration.
        entries = sectioned_config_entries(text)
        return dict(entries) if entries else None
    data: Dict[str, Any] = {}
    for section in parser.sections():
        node: Dict[str, Any] = data
        parts = section.split(".")
        for part in parts[:-1]:
            child = node.setdefault(part, {})
            if not isinstance(child, dict):
                return None
            node = child
        node[parts[-1]] = {
            key: _coerce_config_value(value) for key, value in parser.items(section)
        }
    for name, value in parser.defaults().items():
        data.setdefault(name, _coerce_config_value(value))
    return data


def parse_config_text(text: str, suffix: str) -> Optional[Dict[str, Any]]:
    """
    Read configuration text into a nested mapping.

    The format is decided by the suffix, not by the file's name.

    Returns:
        The parsed mapping, or ``None`` when the text cannot be read as
        configuration of that format.
    """
    suffix = suffix.lower()
    try:
        if suffix == ".json":
            data: Any = json.loads(text)
        elif suffix in (".yaml", ".yml"):
            data = yaml.safe_load(text)
        elif suffix == ".toml":
            import tomllib

            data = tomllib.loads(text)
        elif suffix in (".ini", ".cfg", ".conf"):
            data = _parse_ini(text)
        else:
            return None
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def parse_config_file(path: Path) -> Optional[Dict[str, Any]]:
    """
    Read a configuration file into a nested mapping.

    The format is decided by the file's suffix, not by its name: a robot's
    parameters may ship as YAML, JSON, TOML or INI, and all four are read
    into the same shape, so the rest of the pipeline does not have to care
    which one a customer's robot happens to use.

    Returns:
        The parsed mapping, or ``None`` when the file cannot be read as
        configuration.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return parse_config_text(text, path.suffix.lower())


def replace_sectioned_scalar(
    text: str, dotted_key: str, new_value: Any
) -> Optional[Tuple[str, Any]]:
    """
    Change one numeric assignment in a sectioned configuration file.

    The section matters: a file may declare ``timeout_ms`` under two
    different sections, and only the one the patch names may change, so the
    assignment is located by section *and* key rather than by key alone.

    The quoting style, the indentation, the spacing around the ``=`` and the
    trailing comment are all preserved, which is what makes the diff between
    the original and the patched file a one-line diff.

    Returns:
        ``(new text, previous value)``, or ``None`` when the key is absent
        from this file.
    """
    lines = text.splitlines()
    section = ""
    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        header = _SECTION_HEADER_RE.match(raw_line)
        if header:
            section = header.group("name").strip()
            continue
        match = _SECTION_LINE_RE.match(raw_line)
        if not match:
            continue
        key = match.group("key")
        dotted = f"{section}.{key}" if section else key
        if not _same_dotted_key(dotted, dotted_key):
            continue
        value_text, tail = _split_sectioned_value(match.group("value"))
        previous = _parse_sectioned_scalar(value_text)
        if not isinstance(previous, (int, float)) or isinstance(previous, bool):
            continue
        rendered = _format_scalar(new_value)
        if len(value_text) >= 2 and value_text[0] == value_text[-1] in ("'", '"'):
            rendered = f"{value_text[0]}{rendered}{value_text[0]}"
        lines[index] = (
            match.group("indent") + key + match.group("gap") + rendered + tail
        )
        return "\n".join(lines) + ("\n" if text.endswith("\n") else ""), previous
    return None


# ---------------------------------------------------------------------------
# Source text editing
# ---------------------------------------------------------------------------

#: ``self.qos_depth = 10`` or ``qos_depth: 10``.
_SOURCE_ASSIGNMENT_RE = re.compile(
    r"(?m)^(?P<head>\s*(?:self\.)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*)"
    r"(?P<value>-?\d+(?:\.\d+)?)\s*(?P<tail>.*)$"
)


def source_parameter_entries(text: str) -> Dict[str, List[Tuple[str, Any]]]:
    """
    Every pipeline parameter a source file assigns.

    A configuration file is not the only place a pipeline knob lives: a ROS
    node may set its queue depth in ``__init__``.  Reading those assignments
    is what lets a patch change source code when that is where the knob is.
    """
    entries: Dict[str, List[Tuple[str, Any]]] = {}
    for match in _SOURCE_ASSIGNMENT_RE.finditer(text):
        parameter = match_parameter(match.group("name"))
        if parameter is None:
            continue
        entries.setdefault(parameter, []).append(
            (match.group("name"), float(match.group("value")))
        )
    return entries


def replace_source_scalar(
    text: str, name: str, new_value: Any
) -> Optional[Tuple[str, Any]]:
    """
    Change one numeric assignment in a source file.

    Returns:
        ``(new text, previous value)``, or ``None`` when the assignment is
        not there.
    """
    pattern = re.compile(
        r"(?m)^(?P<head>\s*(?:self\.)?(?P<name>"
        + re.escape(name)
        + r")\s*[:=]\s*)(?P<value>-?\d+(?:\.\d+)?)"
    )
    match = pattern.search(text)
    if not match:
        return None
    previous = float(match.group("value"))
    rendered = _format_scalar(new_value)
    new_text = (
        text[: match.start()]
        + match.group("head")
        + rendered
        + text[match.end() :]
    )
    return new_text, previous


# ---------------------------------------------------------------------------
# Searching a bundle
# ---------------------------------------------------------------------------

#: The file types a configuration or source knob can live in.
CONFIG_SUFFIXES = (".yaml", ".yml", ".json")

#: Configuration files that declare their keys in sections rather than in a
#: nested mapping.  A robot that ships ``robot.toml`` is not without a
#: configuration, so its knobs have to be found and patched exactly as a
#: YAML document's are.
SECTIONED_CONFIG_SUFFIXES = (".toml", ".ini", ".cfg", ".conf")

#: Files that are configuration *of the toolchain*, not of the robot.  A
#: bundle that ships its own ``pyproject.toml`` is a Python project, not a
#: robot whose parameters are named ``batching_window_ms``.
_PACKAGING_NAMES = frozenset(
    {
        "pyproject.toml",
        "setup.cfg",
        "tox.ini",
        "pytest.ini",
        ".coveragerc",
        "mypy.ini",
    }
)

SOURCE_SUFFIXES = (".py", ".cpp", ".cc", ".cxx", ".h", ".hpp")


def is_packaging_file(path: Path) -> bool:
    """Whether a file configures the build rather than the robot."""
    name = Path(path).name.lower()
    if name in _PACKAGING_NAMES:
        return True
    return name.startswith(".")


def _iter_files(root: Path, suffixes: Iterable[str]) -> List[Path]:
    found: List[Path] = []
    for suffix in suffixes:
        found.extend(root.rglob(f"*{suffix}"))
    return sorted(p for p in found if p.is_file())


def find_parameter_in_tree(
    root: Path,
    parameter: str,
    *,
    preferred: Optional[str] = None,
    directories: Optional[Iterable[str]] = None,
) -> Optional[Tuple[str, str, Any]]:
    """
    Find where a parameter is declared in a directory tree.

    Args:
        root: The tree to search.
        parameter: The pipeline parameter to look for.
        preferred: The relative path the intervention named.  When it exists
            and declares the parameter, it wins - the operator's own mapping
            of parameter to file is trusted over the search.
        directories: Restrict the search to these sub-directories.  When
            omitted, the whole tree is searched.

    Returns:
        ``(relative path, key, current value)``, or ``None``.
    """
    root = Path(root)
    search_roots = [root / d for d in directories] if directories else [root]

    # 1. The file the intervention named.
    if preferred:
        candidate = root / preferred
        if candidate.is_file():
            found = find_parameter_in_file(candidate, parameter, relative_to=root)
            if found is not None:
                return found

    for search_root in search_roots:
        if not search_root.is_dir():
            continue
        for path in _iter_files(search_root, CONFIG_SUFFIXES):
            found = find_parameter_in_file(path, parameter, relative_to=root)
            if found is not None:
                return found
        for path in _iter_files(search_root, SECTIONED_CONFIG_SUFFIXES):
            if is_packaging_file(path):
                continue
            found = find_parameter_in_file(path, parameter, relative_to=root)
            if found is not None:
                return found
        for path in _iter_files(search_root, SOURCE_SUFFIXES):
            found = find_parameter_in_file(path, parameter, relative_to=root)
            if found is not None:
                return found

    # A bundle may keep its configuration beside the manifest rather than in
    # a ``config/`` directory - a ``robot.toml`` at the top level is a common
    # way to ship one - so the root's own configuration files are searched
    # too.  Only the files directly in the root are considered: a source file
    # that mentions the name is not where the robot keeps its settings.
    top_level = sorted(p for p in root.iterdir() if p.is_file()) if root.is_dir() else []
    for path in top_level:
        suffix = path.suffix.lower()
        if suffix not in CONFIG_SUFFIXES + SECTIONED_CONFIG_SUFFIXES:
            continue
        if is_packaging_file(path):
            continue
        found = find_parameter_in_file(path, parameter, relative_to=root)
        if found is not None:
            return found

    return None


def find_parameter_in_file(
    path: Path, parameter: str, *, relative_to: Optional[Path] = None
) -> Optional[Tuple[str, str, Any]]:
    """
    Find where a parameter is declared in one file.

    Returns:
        ``(relative path, key, current value)``, or ``None`` when the file
        does not declare the parameter.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    suffix = path.suffix.lower()
    relative = (
        path.relative_to(relative_to).as_posix() if relative_to is not None else path.as_posix()
    )

    if suffix in CONFIG_SUFFIXES:
        if suffix == ".json":
            try:
                data = json.loads(text)
            except Exception:
                data = None
        else:
            try:
                data = yaml.safe_load(text)
            except Exception:
                data = None
        if isinstance(data, dict):
            for key, value in config_parameter_entries(data).get(parameter, []):
                return relative, key, value
        # A YAML file that does not parse cleanly may still declare the key as
        # a plain scalar; fall back to the line scanner.
        for _index, key, value_text, *_ in yaml_scalar_lines(text):
            if match_parameter(key) != parameter:
                continue
            value = _parse_yaml_scalar(value_text)
            if value is not None:
                return relative, key, value
        return None

    if suffix in SECTIONED_CONFIG_SUFFIXES:
        for key, value in sectioned_config_entries(text):
            if match_parameter(key) != parameter:
                continue
            return relative, key, value
        return None

    for name, value in source_parameter_entries(text).get(parameter, []):
        return relative, name, value
    return None
