"""
Canonical component attribution for evidence events.

Evidence reaches Cauveris through many channels - service logs, ROS node
logs, metric exporters, distributed traces, deployment manifests and operator
notes - and each channel names the thing it describes differently, or not at
all.

The holographic inverse problem estimates a state vector *per component*, so
every consumer that needs to answer "which component does this observation
describe?" has to give the same answer.  HEU construction and topology
construction used to resolve components independently and disagreed with each
other; a real incident bundle therefore collapsed onto a single placeholder
component, and the inversion then reported confident, meaningless numbers
(health 1.0, cpu 0.0) for an incident that was actually a saturating GPU
queue.

This module is the single resolver used by both, plus the bundle-declared
alias mechanism that lets a bundle state "these two names mean the same
thing" instead of forcing the resolver to guess.  Nothing here invents a
relationship: when the evidence does not say which component an observation
belongs to, the attribution stays unresolved and the observation is reported
as unattributed rather than being folded into a plausible-looking neighbour.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import yaml

logger = logging.getLogger(__name__)

# How a component name was obtained, in decreasing order of trustworthiness.
EXPLICIT = "explicit"  # stamped by the parser that read the evidence
DECLARED_ATTRIBUTE = "declared_attribute"  # the evidence names its own owner
FILE_CHANNEL = "file_channel"  # derived from the evidence file's channel
SPAN_NAME = "span_name"  # derived from a trace span's operation name
SYSTEM_RECORDING = "system_recording"  # a recording of the system under study
UNRESOLVED = "unresolved"

# How much an observation is allowed to constrain a component's state, per
# attribution method.  These are weights, not probabilities.
_METHOD_CONFIDENCE = {
    EXPLICIT: 1.0,
    DECLARED_ATTRIBUTE: 0.9,
    FILE_CHANNEL: 0.7,
    SYSTEM_RECORDING: 0.7,
    SPAN_NAME: 0.45,
    UNRESOLVED: 0.0,
}

# Attribute keys that identify the emitting component, most specific first.
_COMPONENT_ATTRIBUTES = (
    "component",
    "service",
    "service.name",
    "service_name",
    "component_name",
    "node",
)

# Evidence file extensions stripped when deriving a channel name.
_EVIDENCE_EXTENSIONS = (
    ".jsonl",
    ".json",
    ".csv",
    ".log",
    ".yaml",
    ".yml",
    ".txt",
    ".md",
    ".mcap",
    ".parquet",
)

# Files that describe a *channel* rather than a component.
_GENERIC_CHANNELS = {"otel", "events", "manifest", "index"}


@dataclass(frozen=True)
class Attribution:
    """Which component an observation belongs to, and how sure we are."""

    component: Optional[str]
    method: str = UNRESOLVED
    confidence: float = 0.0

    @property
    def resolved(self) -> bool:
        return bool(self.component)


def channel_component(source: Optional[str]) -> Optional[str]:
    """Component name implied by an evidence file path.

    ``logs/cloud-service.jsonl`` -> ``cloud-service``,
    ``metrics/gpu.csv`` -> ``gpu``.  Files whose stem only names a transport
    (``traces/otel.json``, ``deployments/events.json``) carry no component
    identity and resolve to ``None``.
    """
    if not source:
        return None
    name = str(source).replace("\\", "/").rsplit("/", 1)[-1].strip()
    lower = name.lower()
    for ext in _EVIDENCE_EXTENSIONS:
        if lower.endswith(ext):
            name = name[: -len(ext)]
            break
    name = name.strip().strip("._-")
    if not name or name.lower() in _GENERIC_CHANNELS:
        return None
    return name


def span_component(span_name: Optional[str]) -> Optional[str]:
    """Component name implied by a trace span's operation name.

    A span name describes the *operation* (``inference_request``), not the
    emitting service, so this is the weakest signal available and carries
    the lowest confidence.
    """
    if not span_name:
        return None
    head = re.split(r"[._:/-]", str(span_name).strip(), maxsplit=1)[0].strip().lower()
    return head or None


def load_component_aliases(bundle_path: Optional[Path]) -> Dict[str, str]:
    """Load the component aliases a bundle declares about itself.

    Two sources are read, both declarations made by the bundle itself:

    * ``manifest.yaml`` -> ``component_aliases``
    * ``config/component_aliases.yaml`` (or ``.json``)

    The mapping is ``alias -> canonical component``.  A bundle that declares
    nothing gets no aliases, and equivalent names then stay distinct - the
    resolver never guesses that two differently named entities are the same.
    """
    aliases: Dict[str, str] = {}
    if not bundle_path:
        return aliases
    root = Path(bundle_path)

    manifest_path = root / "manifest.yaml"
    if manifest_path.exists():
        try:
            data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            declared = data.get("component_aliases") if isinstance(data, dict) else None
            if isinstance(declared, dict):
                aliases.update({str(k): str(v) for k, v in declared.items()})
        except Exception as exc:  # pragma: no cover - malformed manifest
            logger.warning(f"Could not read component aliases from {manifest_path}: {exc}")

    for candidate in (
        root / "config" / "component_aliases.yaml",
        root / "config" / "component_aliases.yml",
        root / "config" / "component_aliases.json",
    ):
        if not candidate.exists():
            continue
        try:
            if candidate.suffix == ".json":
                import json

                data = json.loads(candidate.read_text(encoding="utf-8"))
            else:
                data = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
            declared = data.get("component_aliases", data) if isinstance(data, dict) else None
            if isinstance(declared, dict):
                aliases.update({str(k): str(v) for k, v in declared.items()})
        except Exception as exc:  # pragma: no cover - malformed alias file
            logger.warning(f"Could not read component aliases from {candidate}: {exc}")

    return aliases


def canonical_component(
    name: Optional[str], aliases: Optional[Mapping[str, str]] = None
) -> Optional[str]:
    """Map a raw name onto its canonical component name via declared aliases."""
    if not name:
        return None
    current = str(name).strip()
    if not current:
        return None
    if not aliases:
        return current

    seen = set()
    for _ in range(8):  # bounded: alias chains must not loop forever
        if current in seen:
            break
        seen.add(current)
        target = aliases.get(current)
        if target is None:
            lowered = current.lower()
            for alias, alias_target in aliases.items():
                if str(alias).lower() == lowered:
                    target = alias_target
                    break
        if not target or str(target).strip() == current:
            break
        current = str(target).strip()
    return current or None


def resolve_attribution(
    event: Any, aliases: Optional[Mapping[str, str]] = None
) -> Attribution:
    """Resolve which component an evidence event describes.

    Resolution order:

    1. ``event["component"]`` - a parser that read the evidence already
       stamped its owner.
    2. A declared owner attribute (``service``, ``node``, ...).
    3. The evidence file's channel (``metrics/gpu.csv`` -> ``gpu``).
    4. A trace span's operation name (``inference_request`` -> ``inference``).
    5. Unresolved.
    """
    if not isinstance(event, Mapping):
        return Attribution(None, UNRESOLVED, 0.0)

    stamped = event.get("component")
    if isinstance(stamped, str) and stamped.strip():
        method = str(event.get("component_source") or EXPLICIT)
        confidence = event.get("component_confidence")
        if not isinstance(confidence, (int, float)):
            confidence = _METHOD_CONFIDENCE.get(method, _METHOD_CONFIDENCE[EXPLICIT])
        return Attribution(canonical_component(stamped, aliases), method, float(confidence))

    attributes = event.get("attributes")
    attributes = attributes if isinstance(attributes, Mapping) else {}

    for key in _COMPONENT_ATTRIBUTES:
        value = attributes.get(key)
        if isinstance(value, str) and value.strip():
            return Attribution(
                canonical_component(value, aliases),
                DECLARED_ATTRIBUTE,
                _METHOD_CONFIDENCE[DECLARED_ATTRIBUTE],
            )

    channel = channel_component(event.get("source"))
    if channel:
        return Attribution(
            canonical_component(channel, aliases),
            FILE_CHANNEL,
            _METHOD_CONFIDENCE[FILE_CHANNEL],
        )

    span = span_component(attributes.get("span_name"))
    if span:
        return Attribution(
            canonical_component(span, aliases), SPAN_NAME, _METHOD_CONFIDENCE[SPAN_NAME]
        )

    return Attribution(None, UNRESOLVED, 0.0)


def resolve_event_component(
    event: Any, aliases: Optional[Mapping[str, str]] = None
) -> Optional[str]:
    """Canonical component name for an event, or ``None`` when unresolved."""
    return resolve_attribution(event, aliases).component
