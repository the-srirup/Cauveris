"""
Data model for Cauveris session packages.

A *session package* is a round-trippable snapshot of one whole investigation:
the evidence bundle, the pipeline stage history, the append-only event log,
the incident report and any repair packages already built for it.  It is the
unit of work an operator saves and later resumes.

The format deliberately mirrors the proven ``cauveris-repair-package/v1``
discipline: a versioned manifest, a per-file SHA-256 table, atomic archive
writes and owner-scoped access.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

#: Manifest format version, so old archives can declare what they are.
SESSION_MANIFEST_FORMAT = "cauveris-session/v1"

#: Schema version for the manifest body itself.
SESSION_SCHEMA_VERSION = 1

#: Canonical in-archive layout.  Every path is relative to the archive root.
SESSION_MANIFEST_PATH = "session/manifest.yaml"
SESSION_STAGES_PATH = "session/pipeline/stages.json"
SESSION_EVENTS_PATH = "session/pipeline/events.json"
SESSION_REPORT_PATH = "session/report/incident_report.json"
SESSION_PACKAGES_DIR = "session/packages"
SESSION_ARTIFACTS_DIR = "artifacts"
SESSION_CHECKSUMS_PATH = "checksums.sha256"


class SessionError(Exception):
    """Base class for session-package failures."""

    code = "session_error"

    def __init__(self, message: str, **context: Any):
        super().__init__(message)
        self.message = message
        self.context = context


class SessionFormatError(SessionError):
    """The archive is not a ``cauveris-session/v1`` package."""

    code = "session_invalid_format"


class SessionChecksumError(SessionError):
    """A file in the archive does not match its recorded checksum."""

    code = "session_checksum_mismatch"


class SessionNotFoundError(SessionError):
    """No session package exists for the requested incident."""

    code = "session_not_found"


@dataclass
class SessionManifestEntry:
    """One artifact entry inside the manifest's ``files`` table."""

    path: str
    sha256: str
    size_bytes: int
    file_type: str = "artifact"
    purpose: str = ""
    required: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "file_type": self.file_type,
            "purpose": self.purpose,
            "required": self.required,
        }


@dataclass
class SessionManifest:
    """
    The canonical description of what a session package contains.

    The manifest is the single source of truth inside the archive: it declares
    the format, the incident metadata, the pipeline state and a checksum for
    every file.  ``checksum_lines`` carries the raw ``sha256  path`` lines
    written to ``checksums.sha256``.
    """

    incident_id: str
    title: str = ""
    session_id: str = ""
    schema_version: int = SESSION_SCHEMA_VERSION
    format: str = SESSION_MANIFEST_FORMAT
    description: str = ""
    system_name: Optional[str] = None
    severity: Optional[str] = None
    category: Optional[str] = None
    environment: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    intake_method: Optional[str] = None
    approximate_time: Optional[str] = None
    is_demonstration: bool = False
    pipeline_state: str = "IDLE"
    active_stage_id: Optional[str] = None
    report_present: bool = False
    repair_package_count: int = 0
    evidence_file_count: int = 0
    stage_count: int = 0
    event_count: int = 0
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    generator_version: str = "1.0"
    files: List[SessionManifestEntry] = field(default_factory=list)
    checksum_lines: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "format": self.format,
            "schema_version": self.schema_version,
            "incident_id": self.incident_id,
            "title": self.title,
            "session_id": self.session_id,
            "description": self.description,
            "system_name": self.system_name,
            "severity": self.severity,
            "category": self.category,
            "environment": self.environment,
            "tags": list(self.tags),
            "intake_method": self.intake_method,
            "approximate_time": self.approximate_time,
            "is_demonstration": self.is_demonstration,
            "pipeline_state": self.pipeline_state,
            "active_stage_id": self.active_stage_id,
            "report_present": self.report_present,
            "repair_package_count": self.repair_package_count,
            "evidence_file_count": self.evidence_file_count,
            "stage_count": self.stage_count,
            "event_count": self.event_count,
            "generated_at": self.generated_at,
            "generator_version": self.generator_version,
            "files": [entry.to_dict() for entry in self.files],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionManifest":
        files = [
            SessionManifestEntry(
                path=entry.get("path", ""),
                sha256=entry.get("sha256", ""),
                size_bytes=int(entry.get("size_bytes") or 0),
                file_type=entry.get("file_type", "artifact"),
                purpose=entry.get("purpose", ""),
                required=bool(entry.get("required", True)),
            )
            for entry in (data.get("files") or [])
            if isinstance(entry, dict)
        ]
        return cls(
            incident_id=data.get("incident_id", ""),
            title=data.get("title", "") or "",
            session_id=data.get("session_id", "") or "",
            schema_version=int(data.get("schema_version") or SESSION_SCHEMA_VERSION),
            format=data.get("format", SESSION_MANIFEST_FORMAT),
            description=data.get("description", "") or "",
            system_name=data.get("system_name"),
            severity=data.get("severity"),
            category=data.get("category"),
            environment=data.get("environment"),
            tags=list(data.get("tags") or []),
            intake_method=data.get("intake_method"),
            approximate_time=data.get("approximate_time"),
            is_demonstration=bool(data.get("is_demonstration", False)),
            pipeline_state=data.get("pipeline_state", "IDLE") or "IDLE",
            active_stage_id=data.get("active_stage_id"),
            report_present=bool(data.get("report_present", False)),
            repair_package_count=int(data.get("repair_package_count") or 0),
            evidence_file_count=int(data.get("evidence_file_count") or 0),
            stage_count=int(data.get("stage_count") or 0),
            event_count=int(data.get("event_count") or 0),
            generated_at=data.get("generated_at", "") or "",
            generator_version=data.get("generator_version", "1.0") or "1.0",
            files=files,
        )


@dataclass
class SessionRecord:
    """The persisted record of one built session package."""

    incident_id: str
    session_id: str = ""
    build_number: int = 1
    status: str = "READY"
    storage_locator: Optional[str] = None
    session_sha256: str = ""
    size: int = 0
    safe_filename: str = ""
    manifest: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    built_by_user_id: str = ""
    built_by_org_id: str = ""
    failure_code: Optional[str] = None
    failure_message: Optional[str] = None
    source_incident_id: str = ""
    version: int = 1

    @property
    def zip_path(self) -> Optional[str]:
        return self.storage_locator

    @property
    def checksum_sha256(self) -> str:
        return self.session_sha256

    @property
    def size_bytes(self) -> int:
        return self.size

    @property
    def is_downloadable(self) -> bool:
        return self.status == "READY" and bool(self.storage_locator)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "session_id": self.session_id,
            "build_number": self.build_number,
            "status": self.status,
            "storage_locator": self.storage_locator,
            "session_sha256": self.session_sha256,
            "size": self.size,
            "safe_filename": self.safe_filename,
            "manifest": self.manifest,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "built_by_user_id": self.built_by_user_id,
            "built_by_org_id": self.built_by_org_id,
            "failure_code": self.failure_code,
            "failure_message": self.failure_message,
            "source_incident_id": self.source_incident_id,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionRecord":
        return cls(
            incident_id=data.get("incident_id", ""),
            session_id=data.get("session_id", ""),
            build_number=int(data.get("build_number") or 1),
            status=data.get("status", "READY") or "READY",
            storage_locator=data.get("storage_locator"),
            session_sha256=data.get("session_sha256", "") or "",
            size=int(data.get("size") or 0),
            safe_filename=data.get("safe_filename", "") or "",
            manifest=data.get("manifest") or {},
            created_at=data.get("created_at", "") or "",
            updated_at=data.get("updated_at", "") or "",
            built_by_user_id=data.get("built_by_user_id", "") or "",
            built_by_org_id=data.get("built_by_org_id", "") or "",
            failure_code=data.get("failure_code"),
            failure_message=data.get("failure_message"),
            source_incident_id=data.get("source_incident_id", "") or "",
            version=int(data.get("version") or 1),
        )


@dataclass
class SessionBuildOutcome:
    """The result of building one session package."""

    record: SessionRecord
    manifest: SessionManifest
    zip_bytes: bytes = b""
    warnings: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)


@dataclass
class SessionImportSummary:
    """
    The honest account of what an import actually restored.

    ``missing`` names the parts of the session that were *not* in the
    archive.  A restored incident with no report must never be presented as
    "0 findings, all clear" — the summary is what the console renders.
    """

    incident_id: str
    title: str = ""
    restored: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    pipeline_state: str = "IDLE"
    active_stage_id: Optional[str] = None
    report_present: bool = False
    stage_count: int = 0
    event_count: int = 0
    repair_package_count: int = 0
    evidence_file_count: int = 0
    source_incident_id: str = ""
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "title": self.title,
            "restored": list(self.restored),
            "missing": list(self.missing),
            "pipeline_state": self.pipeline_state,
            "active_stage_id": self.active_stage_id,
            "report_present": self.report_present,
            "stage_count": self.stage_count,
            "event_count": self.event_count,
            "repair_package_count": self.repair_package_count,
            "evidence_file_count": self.evidence_file_count,
            "source_incident_id": self.source_incident_id,
            "warnings": list(self.warnings),
        }


def sha256_bytes(data: bytes) -> str:
    """SHA-256 of a byte string, hex-encoded."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    """SHA-256 of a file on disk, hex-encoded."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def random_session_id() -> str:
    """A short, unambiguous session identifier."""
    return f"ses-{os.urandom(8).hex()}"


def verify_checksum(expected: str, actual: str) -> bool:
    """Constant-time comparison of two checksums."""
    return hmac.compare_digest(str(expected), str(actual))
