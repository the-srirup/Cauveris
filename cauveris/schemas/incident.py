"""
Incident-related schemas.
"""

from .base import BaseEntity, StatusLabel
from pydantic import Field, PrivateAttr
from typing import Optional, List, Dict, Any, ClassVar, Tuple
from datetime import datetime


class EvidenceItem(BaseEntity):
    """A piece of evidence in an incident bundle."""

    file_path: str = Field(..., description="Path within the incident bundle")
    file_type: str = Field(..., description="MIME type or file extension")
    size_bytes: int = Field(..., description="Size of the file in bytes")
    checksum_sha256: str = Field(..., description="SHA-256 checksum of the file")
    status: StatusLabel = Field(
        default=StatusLabel.OBSERVED, description="Current validation status"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    is_required: bool = Field(
        default=False, description="Whether this evidence is required for processing"
    )
    validation_errors: List[str] = Field(
        default_factory=list, description="Errors found during validation"
    )
    redacted: bool = Field(
        default=False, description="Whether secrets have been redacted from this item"
    )


class Incident(BaseEntity):
    """A structured incident bundle uploaded by the user or loaded from demo."""

    title: str = Field(..., description="Human-readable incident title")
    description: Optional[str] = Field(None, description="Detailed incident description")
    system_name: Optional[str] = Field(None, description="Name of the robotic system")
    approximate_time: Optional[datetime] = Field(None, description="Approximate time of incident")
    source_repositories: List[str] = Field(
        default_factory=list, description="Related source repositories"
    )
    commit_hash: Optional[str] = Field(None, description="Exact commit hash if known")
    evidence_items: List[EvidenceItem] = Field(
        default_factory=list, description="All evidence in the bundle"
    )
    manifest: Dict[str, Any] = Field(default_factory=dict, description="Parsed manifest.yaml")
    status: StatusLabel = Field(
        default=StatusLabel.OBSERVED, description="Overall incident processing status"
    )
    bundle_path: Optional[str] = Field(None, description="Path to the incident bundle directory")
    timeline_events: List[Dict[str, Any]] = Field(
        default_factory=list, description="Normalized timeline events"
    )
    temporal_analysis: Optional[Dict[str, Any]] = Field(
        default=None, description="Temporal causality analysis results"
    )
    is_demonstration: bool = Field(
        default=False, description="Whether this incident is demonstration benchmark data"
    )
    artifact_inventory: List[Dict[str, Any]] = Field(
        default_factory=list, description="Detailed inventory of all files in bundle"
    )
    capability_report: Optional[Dict[str, Any]] = Field(
        default=None, description="Pre-repair honest capability evaluation report"
    )
    discovered_repository: Optional[Dict[str, Any]] = Field(
        default=None, description="Discovered source repository analysis"
    )
    package_sha256: Optional[str] = Field(
        default=None, description="Cryptographic SHA-256 of the uploaded package archive"
    )
    job_id: Optional[str] = Field(
        default=None, description="Associated pipeline job execution ID"
    )

    # Operator-declared triage metadata.  These are collected by the workspace
    # creation wizard and must survive ingestion, persistence and a session
    # package round-trip — the wizard asks for them, so the backend keeps them.
    severity: Optional[str] = Field(
        default=None, description="Operator-declared triage severity (critical/high/medium/low)"
    )
    category: Optional[str] = Field(
        default=None, description="Implicated subsystem category (detection/navigation/planning/control/communication/other)"
    )
    environment: Optional[str] = Field(
        default=None, description="Deployment environment (warehouse/outdoor/lab/simulation/other)"
    )
    tags: List[str] = Field(
        default_factory=list, description="Free-form cross-cutting labels. Never used as the incident id."
    )
    intake_method: Optional[str] = Field(
        default=None, description="How the incident entered the system (archive/source/manual/url)"
    )

    # Multi-tenant and upload context private attributes
    _owner_user_id: Optional[str] = PrivateAttr(default=None)
    _owner_org_id: Optional[str] = PrivateAttr(default=None)
    _is_anonymous: bool = PrivateAttr(default=False)
    _uploaded_filename: Optional[str] = PrivateAttr(default=None)

    # Computed properties
    evidence_count: int = Field(0, description="Number of evidence items")
    required_evidence_count: int = Field(0, description="Number of required evidence items")
    missing_required_evidence: List[str] = Field(
        default_factory=list, description="List of missing required evidence paths"
    )

    def update_counts(self) -> None:
        """Update evidence counts based on current evidence items."""
        self.evidence_count = len(self.evidence_items)
        self.required_evidence_count = sum(1 for item in self.evidence_items if item.is_required)
        self.missing_required_evidence = [
            item.file_path
            for item in self.evidence_items
            if item.is_required and item.status != StatusLabel.OBSERVED
        ]

    #: The operator-declared triage fields that travel with the incident.
    METADATA_FIELDS: ClassVar[Tuple[str, ...]] = (
        "severity",
        "category",
        "environment",
        "tags",
        "intake_method",
        "approximate_time",
    )

    def metadata_snapshot(self) -> Dict[str, Any]:
        """Return the triage metadata as a plain, JSON-safe mapping.

        Empty values are omitted so a metadata sidecar never carries a pile of
        ``None`` keys that say nothing.
        """
        snapshot: Dict[str, Any] = {}
        for name in self.METADATA_FIELDS:
            value = getattr(self, name, None)
            if value is None:
                continue
            if name == "tags":
                if not value:
                    continue
                snapshot[name] = list(value)
                continue
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            snapshot[name] = value
        return snapshot

    def apply_metadata_snapshot(self, snapshot: Optional[Dict[str, Any]]) -> None:
        """Restore triage metadata previously captured by ``metadata_snapshot``."""
        if not snapshot:
            return
        for name in self.METADATA_FIELDS:
            if name not in snapshot or snapshot[name] is None:
                continue
            value = snapshot[name]
            if name == "tags":
                setattr(self, name, list(value or []))
                continue
            if name == "approximate_time" and isinstance(value, str):
                try:
                    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    continue
            setattr(self, name, value)

    def apply_metadata_to_manifest(self) -> Dict[str, Any]:
        """Merge the triage metadata into ``self.manifest``.

        The manifest is what survives a backend restart and what a session
        package serializes, so the wizard's answers must live there, not only
        on the transient incident object.
        """
        if not isinstance(self.manifest, dict):
            self.manifest = {}
        for key, value in self.metadata_snapshot().items():
            self.manifest.setdefault(key, value)
        return self.manifest
