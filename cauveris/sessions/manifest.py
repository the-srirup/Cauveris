"""
Versioned manifest schema and builder for session packages.

The manifest is the single source of truth inside a ``cauveris-session/v1``
archive.  It declares the format, the incident metadata, the pipeline state
the session was captured in, and a SHA-256 checksum for every file the
archive carries.  A companion ``checksums.sha256`` holds the same digests in
the conventional ``sha256  path`` form so the archive can be verified with
standard tools.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

from cauveris.sessions.models import (
    SESSION_CHECKSUMS_PATH,
    SESSION_MANIFEST_FORMAT,
    SESSION_MANIFEST_PATH,
    SessionManifest,
    SessionManifestEntry,
)


def _infer_file_metadata(path: str) -> Tuple[str, str, bool]:
    """Return ``(file_type, purpose, required)`` for an in-archive path."""
    p = path.lower()
    if p == SESSION_MANIFEST_PATH.lower():
        return "manifest", "Session manifest and provenance record", True
    if p == SESSION_CHECKSUMS_PATH.lower():
        return "checksums", "Per-file SHA-256 member checksums", True
    if p.endswith("stages.json"):
        return "pipeline", "Pipeline stage history for the session", True
    if p.endswith("events.json"):
        return "pipeline", "Append-only pipeline event log for the session", True
    if "incident_report" in p:
        return "report", "Investigation report captured with the session", True
    if p.startswith("session/packages/"):
        return "package", "Repair package already built for this incident", False
    if p.startswith("artifacts/"):
        return "evidence", "Evidence artifact from the incident bundle", False
    if p.endswith((".mcap", ".bag", ".db3")):
        return "recording", "Binary telemetry recording", False
    if p.endswith((".csv", ".jsonl")):
        return "telemetry", "Time-series telemetry", False
    if p.endswith((".yaml", ".yml")):
        return "manifest", "Bundle manifest", False
    if p.endswith(".json"):
        return "json", "Structured record", False
    if p.endswith((".py", ".sh")):
        return "script", "Source or helper script from the evidence bundle", False
    if p.endswith((".md", ".txt")):
        return "documentation", "Human-readable documentation", False
    return "artifact", "Supporting artifact from the evidence bundle", False


def build_session_manifest(
    incident_id: str,
    artifacts: Iterable[Tuple[str, bytes]],
    *,
    title: str = "",
    description: str = "",
    system_name: Optional[str] = None,
    severity: Optional[str] = None,
    category: Optional[str] = None,
    environment: Optional[str] = None,
    tags: Optional[List[str]] = None,
    intake_method: Optional[str] = None,
    approximate_time: Optional[str] = None,
    is_demonstration: bool = False,
    pipeline_state: str = "IDLE",
    active_stage_id: Optional[str] = None,
    report_present: bool = False,
    repair_package_count: int = 0,
    evidence_file_count: int = 0,
    stage_count: int = 0,
    event_count: int = 0,
    session_id: str = "",
    generated_at: Optional[str] = None,
) -> SessionManifest:
    """
    Build a manifest from the artifacts that will go into the archive.

    Args:
        incident_id: The incident being captured.
        artifacts: ``(relative_path, raw_bytes)`` pairs for every file in the
            archive.  The manifest path itself must *not* be included — the
            manifest is written afterwards, and a self-referential checksum
            could never verify.
        title: Incident title.
        description: Incident description.
        system_name: The implicated robotic system.
        severity: Operator-declared triage severity.
        category: Operator-declared subsystem category.
        environment: Operator-declared deployment environment.
        tags: Operator-declared labels.
        intake_method: How the incident entered the system.
        approximate_time: Approximate time of the incident.
        is_demonstration: Whether the incident is sample benchmark data.
        pipeline_state: The pipeline state the session was captured in.
        active_stage_id: The stage that was active when the session was captured.
        report_present: Whether a report was captured.
        repair_package_count: How many repair packages were captured.
        evidence_file_count: How many evidence artifacts were captured.
        stage_count: How many stage records were captured.
        event_count: How many events were captured.
        session_id: The session identifier.
        generated_at: ISO timestamp; defaults to now.

    Returns:
        A :class:`SessionManifest` with its per-file entries and checksum lines.
    """
    entries: List[SessionManifestEntry] = []
    checksum_lines: List[str] = []

    for rel, data in artifacts:
        digest = hashlib.sha256(data).hexdigest()
        ftype, purpose, required = _infer_file_metadata(rel)
        entries.append(
            SessionManifestEntry(
                path=rel,
                sha256=digest,
                size_bytes=len(data),
                file_type=ftype,
                purpose=purpose,
                required=required,
            )
        )
        if not rel.startswith("checksums."):
            checksum_lines.append(f"{digest}  {rel}")

    manifest = SessionManifest(
        incident_id=incident_id,
        title=title or "",
        session_id=session_id or "",
        description=description or "",
        system_name=system_name,
        severity=severity,
        category=category,
        environment=environment,
        tags=list(tags or []),
        intake_method=intake_method,
        approximate_time=approximate_time,
        is_demonstration=is_demonstration,
        pipeline_state=pipeline_state or "IDLE",
        active_stage_id=active_stage_id,
        report_present=report_present,
        repair_package_count=repair_package_count,
        evidence_file_count=evidence_file_count,
        stage_count=stage_count,
        event_count=event_count,
        files=entries,
        checksum_lines=checksum_lines,
    )
    if generated_at:
        manifest.generated_at = generated_at
    return manifest


def manifest_to_yaml(manifest: SessionManifest) -> bytes:
    """Serialize a manifest to the YAML bytes stored at ``session/manifest.yaml``."""
    text = yaml.safe_dump(
        manifest.to_dict(), sort_keys=False, default_flow_style=False, allow_unicode=True
    )
    return text.encode("utf-8")


def parse_manifest(
    data: bytes, expected: str = SESSION_MANIFEST_FORMAT
) -> SessionManifest:
    """
    Parse the bytes of a ``session/manifest.yaml`` into a manifest.

    The declared format is validated here: an archive whose manifest says it
    is something else is not a session package, and the caller must never
    have to wonder whether it parsed "successfully" into the wrong thing.
    """
    from cauveris.sessions.models import SessionFormatError

    try:
        parsed = yaml.safe_load(data.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise SessionFormatError(f"Session manifest is not valid YAML: {exc}") from exc
    if not isinstance(parsed, dict):
        raise SessionFormatError("Session manifest is not a mapping")

    declared = str(parsed.get("format") or "")
    if declared != expected:
        raise SessionFormatError(
            f"Archive declares format {declared!r}; expected {expected!r}"
        )
    return SessionManifest.from_dict(parsed)


def checksum_blob(lines: List[str]) -> bytes:
    """Render the ``checksums.sha256`` file body."""
    if not lines:
        return b""
    return ("\n".join(lines) + "\n").encode("utf-8")


def parse_checksums(data: bytes) -> Dict[str, str]:
    """
    Parse a ``checksums.sha256`` body into ``{path: sha256}``.

    Malformed lines are skipped rather than raising: the manifest's own
    ``files`` table is the authoritative checksum list, and this file exists so
    the archive can be verified with ordinary shell tooling.
    """
    result: Dict[str, str] = {}
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return result
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        digest, path = parts[0].strip(), parts[1].strip()
        # Strip the binary-mode marker some tools add.
        if path.startswith("*"):
            path = path[1:]
        if len(digest) != 64:
            continue
        result[path.lstrip("./")] = digest.lower()
    return result


def manifest_declares_format(data: Dict[str, Any], expected: str = SESSION_MANIFEST_FORMAT) -> bool:
    """Whether the manifest body declares the expected archive format."""
    return str(data.get("format") or "") == expected
