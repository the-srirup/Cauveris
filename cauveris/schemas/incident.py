"""
Incident-related schemas.
"""
from .base import BaseEntity, StatusLabel
from pydantic import Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class EvidenceItem(BaseEntity):
    """A piece of evidence in an incident bundle."""
    file_path: str = Field(..., description="Path within the incident bundle")
    file_type: str = Field(..., description="MIME type or file extension")
    size_bytes: int = Field(..., description="Size of the file in bytes")
    checksum_sha256: str = Field(..., description="SHA-256 checksum of the file")
    status: StatusLabel = Field(default=StatusLabel.OBSERVED, description="Current validation status")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    is_required: bool = Field(default=False, description="Whether this evidence is required for processing")
    validation_errors: List[str] = Field(default_factory=list, description="Errors found during validation")
    redacted: bool = Field(default=False, description="Whether secrets have been redacted from this item")


class Incident(BaseEntity):
    """A structured incident bundle uploaded by the user or loaded from demo."""
    title: str = Field(..., description="Human-readable incident title")
    description: Optional[str] = Field(None, description="Detailed incident description")
    system_name: Optional[str] = Field(None, description="Name of the robotic system")
    approximate_time: Optional[datetime] = Field(None, description="Approximate time of incident")
    source_repositories: List[str] = Field(default_factory=list, description="Related source repositories")
    commit_hash: Optional[str] = Field(None, description="Exact commit hash if known")
    evidence_items: List[EvidenceItem] = Field(default_factory=list, description="All evidence in the bundle")
    manifest: Dict[str, Any] = Field(default_factory=dict, description="Parsed manifest.yaml")
    status: StatusLabel = Field(default=StatusLabel.OBSERVED, description="Overall incident processing status")
    timeline_events: List[Dict[str, Any]] = Field(default_factory=list, description="Normalized timeline events")
    temporal_analysis: Optional[Dict[str, Any]] = Field(default=None, description="Temporal causality analysis results")

    # Computed properties
    evidence_count: int = Field(0, description="Number of evidence items")
    required_evidence_count: int = Field(0, description="Number of required evidence items")
    missing_required_evidence: List[str] = Field(default_factory=list, description="List of missing required evidence paths")

    def update_counts(self) -> None:
        """Update evidence counts based on current evidence items."""
        self.evidence_count = len(self.evidence_items)
        self.required_evidence_count = sum(1 for item in self.evidence_items if item.is_required)
        self.missing_required_evidence = [
            item.file_path for item in self.evidence_items
            if item.is_required and item.status != StatusLabel.OBSERVED
        ]
