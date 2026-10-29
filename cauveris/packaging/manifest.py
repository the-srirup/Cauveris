"""
Versioned manifest schema and builder for repair packages.

The manifest is the single source of truth inside the archive.  It is versioned
(``format``), source-bound (``source_bundle_id``), tamper-evident (every
artifact has a recorded checksum), and it collapses all verification signals
onto the canonical ladder.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from cauveris.packaging.models import (
    MANIFEST_FORMAT,
    VerificationLevel,
    compute_check_count,
    compute_verification_level,
)
from cauveris.schemas.patch import PatchCandidate, VerificationReport


@dataclass
class ManifestEntry:
    """One artifact entry inside the manifest's ``files`` table."""

    path: str
    sha256: str
    size_bytes: int
    file_type: str = "artifact"
    purpose: str = ""
    required: bool = True


@dataclass
class BuiltManifest:
    """
    A fully-constructed manifest with its checksum table.

    ``files`` carries the per-artifact entries (name + sha256 + size + metadata),
    and ``checksums`` carries the raw ``sha256  path`` lines that are written to
    ``checksums.txt`` / ``checksums.sha256``.
    """

    schema_version: str = "1.0"
    format: str = MANIFEST_FORMAT
    package_id: str = ""
    incident_id: str = ""
    repair_id: str = ""
    patch_candidate_id: str = ""
    verification_level: str = VerificationLevel.GENERATED.value
    verification_reason: str = ""
    checks_passed: int = 0
    checks_total: int = 9
    source_bundle_id: str = ""
    source_tree_hash: str = ""
    workspace_id: str = ""
    model_provider: str = ""
    model_name: str = ""
    summary: str = ""
    affected_files: List[str] = field(default_factory=list)
    target_files: List[str] = field(default_factory=list)
    file_checksums: Dict[str, Dict[str, str]] = field(default_factory=dict)
    patch_format: str = "unified_diff"
    hypothesis_id: str = ""
    hypothesis_rationale: str = ""
    limitations: List[str] = field(default_factory=list)
    model_execution_id: str = ""
    token_usage: Dict[str, Any] = field(default_factory=dict)
    rollback_instructions: str = "Run `python tools/rollback_patch.py --target <dir>` to revert changes."
    rollback_patch_path: str = "rollback.patch"
    lines_changed: int = 0
    checks: Dict[str, bool] = field(default_factory=dict)
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    files: List[ManifestEntry] = field(default_factory=list)
    # The raw lines written to checksums.txt/checksums.sha256 (excluding checksum files).
    checksum_lines: List[str] = field(default_factory=list)
    # Whether the package is marked as sample/demonstration (should always be False
    # for real packages built from a real incident).
    is_sample: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "format": self.format,
            "package_id": self.package_id,
            "incident_id": self.incident_id,
            "patch_candidate_id": self.patch_candidate_id,
            "repair_id": self.repair_id,
            "verification_level": self.verification_level,
            "verification_reason": self.verification_reason,
            "checks_passed": self.checks_passed,
            "checks_total": self.checks_total,
            "source_bundle_id": self.source_bundle_id,
            "generated_at": self.generated_at,
            "is_sample": self.is_sample,
            "incident": {
                "id": self.incident_id,
                "workspace_id": self.workspace_id,
                "source_bundle_id": self.source_bundle_id,
            },
            "repair": {
                "candidate_id": self.repair_id,
                "summary": self.summary,
                "affected_files": self.affected_files,
                "target_files": self.target_files,
                "lines_changed": self.lines_changed,
                "patch_format": self.patch_format,
                "file_checksums": self.file_checksums,
                "hypothesis_id": self.hypothesis_id,
                "hypothesis_rationale": self.hypothesis_rationale,
            },
            "source": {
                "tree_hash": self.source_tree_hash,
                "bundle_path": self.source_bundle_id,
            },
            "model": {
                "provider": self.model_provider,
                "model": self.model_name,
                "execution_id": self.model_execution_id,
                "token_usage": self.token_usage,
            },
            "verification": {
                "level": self.verification_level,
                "reason": self.verification_reason,
                "checks_passed": self.checks_passed,
                "checks_total": self.checks_total,
                "checks": self.checks,
                "limitations": self.limitations,
            },
            "rollback": {
                "instructions": self.rollback_instructions,
                "reverse_patch": self.rollback_patch_path,
            },
            "package": {
                "created_at": self.generated_at,
                "generator_version": "1.0",
                "policy_version": "1.0",
                "is_sample": self.is_sample,
            },
            "files": [
                {
                    "path": e.path,
                    "file_type": e.file_type,
                    "sha256": e.sha256,
                    "size_bytes": e.size_bytes,
                    "purpose": e.purpose,
                    "required": e.required,
                }
                for e in self.files
            ],
        }


def _infer_file_metadata(path: str) -> Tuple[str, str, bool]:
    """Return (file_type, purpose, required) based on artifact path."""
    p = path.lower()
    if p.endswith((".patch", ".diff")):
        if "rollback" in p:
            return "patch", "Reverse unified diff for safe rollback", True
        elif "regression" in p:
            return "patch", "Regression test patch to verify fix", False
        return "patch", "Unified diff fix addressing root cause", True
    if p == "manifest.json":
        return "manifest", "Package manifest and provenance record", True
    if p.endswith((".sha256", ".txt")) and "checksum" in p:
        return "checksums", "Per-file SHA-256 member checksums", True
    if p.endswith(".py"):
        if "apply" in p:
            return "script", "Standalone zero-dependency patch installer", True
        if "rollback" in p:
            return "script", "Standalone zero-dependency rollback script", True
        return "script", "Executable tool", False
    if p.endswith(".sh"):
        return "script", "Shell script for patch operations", False
    if p.endswith(".html"):
        return "report", "Full HTML incident investigation report", True
    if p.endswith(".json"):
        if "capability" in p:
            return "json", "Repair capability boundaries and decision", True
        if "limitation" in p:
            return "json", "Structured repair and operational limitations", True
        if "diagnosis" in p:
            return "json", "Root-cause diagnosis and causal claim", True
        if "provenance" in p:
            return "json", "Evidence bundle provenance metadata", True
        if "invariant" in p:
            return "json", "Evaluated safety and performance invariant set", True
        if "baseline" in p:
            return "json", "Baseline failure reproduction run results", True
        if "intervention" in p or "post" in p:
            return "json", "Post-intervention clearance run results", True
        if "comparison" in p:
            return "json", "Baseline vs intervention run comparison", True
        if "verification" in p or "checks" in p:
            return "json", "Verification run verdict and check results", True
        return "json", "Structured evidence record", False
    if p.endswith(".md"):
        return "documentation", "Human-readable documentation and instructions", True
    if p.endswith(".csv"):
        return "telemetry", "Time-series trial telemetry", False
    if p.endswith(".mcap"):
        return "recording", "Binary telemetry log excerpt", False
    return "artifact", "Supporting artifact", False


def build_manifest(
    incident_id: str,
    patch: PatchCandidate,
    report: Optional[VerificationReport],
    staged: bool,
    source_bundle_id: str,
    artifacts: List[Tuple[str, bytes]],
    *,
    package_id: str = "",
    workspace_id: str = "",
    source_tree_hash: str = "",
    model_provider: str = "",
    model_name: str = "",
) -> BuiltManifest:
    """
    Build a manifest from the artifacts that will go into the archive.

    Args:
        incident_id: The incident the package is for.
        patch: The patch candidate the package contains.
        report: The verification report, if any.
        staged: Whether the archive has passed the final staging gate.
        source_bundle_id: The bundle the patch was generated and verified against.
        artifacts: ``(relative_path, raw_bytes)`` pairs for every file in the
            archive. This is what gets checksummed.
        package_id: Unique package identifier.
        workspace_id: Workspace identifier.
        source_tree_hash: Git tree / bundle directory hash.
        model_provider: Provider of model used for investigation.
        model_name: Name of model used.

    Returns:
        A :class:`BuiltManifest` plus the manifest bytes.
    """
    level = compute_verification_level(patch, report, staged=staged)
    checks_passed = compute_check_count(patch)
    if report is not None:
        checks_passed = compute_check_count(report)

    # Collect atomic check states
    src = report if report is not None else patch
    checks_dict = {
        name: bool(getattr(src, name, False))
        for name in (
            "applies_cleanly",
            "regression_test_fails_before",
            "regression_test_passes_after",
            "original_failure_not_reproduced",
            "existing_tests_pass",
            "safety_invariants_pass",
            "performance_within_budget",
            "forbidden_change_scan_passes",
            "rollback_test_passes",
        )
    }

    entries: List[ManifestEntry] = []
    checksum_lines: List[str] = []
    for rel, data in artifacts:
        digest = hashlib.sha256(data).hexdigest()
        ftype, purpose, req = _infer_file_metadata(rel)
        entries.append(
            ManifestEntry(
                path=rel,
                sha256=digest,
                size_bytes=len(data),
                file_type=ftype,
                purpose=purpose,
                required=req,
            )
        )
        # checksums file records lines for other files
        if not rel.startswith("checksums."):
            checksum_lines.append(f"{digest}  {rel}")

    target_files = [patch.target_file] if getattr(patch, "target_file", None) else list(getattr(patch, "affected_files", []))
    file_checksums = dict(getattr(patch, "file_checksums", {}) or {})
    if not file_checksums and getattr(patch, "target_file", None) and (getattr(patch, "before_hash", None) or getattr(patch, "after_hash", None)):
        file_checksums = {patch.target_file: {"before": patch.before_hash or "", "after": patch.after_hash or ""}}

    lims: List[str] = []
    if report is not None:
        report_lims = getattr(report, "limitations", None)
        if report_lims and isinstance(report_lims, list):
            lims.extend(report_lims)
        v_sum = getattr(report, "verification_summary", None)
        if isinstance(v_sum, dict) and v_sum.get("limitations"):
            lims.extend(v_sum["limitations"])

    exec_id = getattr(patch, "provider_execution_id", "") or ""
    t_usage: Dict[str, Any] = {}
    if exec_id:
        try:
            from cauveris.model_gateway.records import get_execution_store
            rec = get_execution_store().get(exec_id)
            if rec:
                model_provider = model_provider or rec.provider
                model_name = model_name or rec.model_id
                t_usage = rec.usage or {}
        except Exception:
            pass

    return BuiltManifest(
        schema_version="1.0",
        format=MANIFEST_FORMAT,
        package_id=package_id or f"pkg_{incident_id}_{patch.candidate_id}",
        incident_id=incident_id,
        repair_id=patch.candidate_id,
        patch_candidate_id=patch.candidate_id,
        verification_level=level.value,
        verification_reason=(
            "All 9 invariant checks passed and archive passed staging gate"
            if staged and level == VerificationLevel.STAGING_VERIFIED
            else f"{checks_passed}/9 invariant checks passed"
        ),
        checks_passed=checks_passed,
        checks_total=9,
        source_bundle_id=source_bundle_id,
        source_tree_hash=source_tree_hash,
        workspace_id=workspace_id,
        model_provider=model_provider,
        model_name=model_name,
        summary=getattr(patch, "description", "") or "Repair candidate patch",
        affected_files=list(getattr(patch, "affected_files", [])),
        target_files=target_files,
        file_checksums=file_checksums,
        patch_format="unified_diff",
        hypothesis_id=getattr(patch, "hypothesis_id", "") or "",
        hypothesis_rationale=getattr(patch, "rationale", "") or "",
        limitations=lims,
        model_execution_id=exec_id,
        token_usage=t_usage,
        rollback_instructions="Run `python tools/rollback_patch.py --target <dir>` to revert changes.",
        rollback_patch_path="rollback.patch",
        lines_changed=getattr(patch, "lines_changed", 0),
        checks=checks_dict,
        files=entries,
        checksum_lines=checksum_lines,
        is_sample=False,
    )
