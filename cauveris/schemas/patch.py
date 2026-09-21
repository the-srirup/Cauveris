"""
Patch and verification schemas.
"""
from .base import BaseEntity
from pydantic import Field
from typing import Optional, List, Dict, Any


class PatchCandidate(BaseEntity):
    """A candidate patch for fixing the incident."""
    candidate_id: str = Field(..., description="Unique identifier for the patch candidate")
    affected_files: List[str] = Field(default_factory=list, description="List of files changed by the patch")
    lines_changed: int = Field(0, description="Number of lines changed")
    unified_diff: str = Field(..., description="Unified diff of the patch")
    regression_test_patch: Optional[str] = Field(None, description="Patch adding regression test")
    build_state: str = Field("unknown", description="Build status: success, failure, or unknown")
    existing_test_state: str = Field("unknown", description="Existing test suite status")
    replay_state: str = Field("unknown", description="Replay status after patch")
    safety_result: str = Field("unknown", description="Safety check result")
    latency_result: str = Field("unknown", description="Performance/latency result")
    policy_findings: List[str] = Field(default_factory=list, description="Forbidden change scan findings")
    score: float = Field(0.0, description="Overall score of the candidate")
    rejection_reason: Optional[str] = Field(None, description="Reason if candidate was rejected")
    applied_cleanly: bool = Field(False, description="Whether patch applied without conflicts")
    regression_test_fails_before: bool = Field(False, description="Regression test fails on original")
    regression_test_passes_after: bool = Field(False, description="Regression test passes after patch")
    original_failure_not_reproduced: bool = Field(False, description="Original failure not reproduced with patch")
    existing_tests_pass: bool = Field(False, description="Existing tests pass with patch")
    safety_invariants_pass: bool = Field(False, description="Safety invariants pass with patch")
    performance_within_budget: bool = Field(False, description="Performance within budget")
    forbidden_change_scan_passes: bool = Field(False, description="Forbidden change scan passes")
    rollback_test_passes: bool = Field(False, description="Rollback test passes")
    verified: bool = Field(False, description="Whether patch meets all verification criteria")


class VerificationReport(BaseEntity):
    """Report of verification checks for a patch candidate."""
    patch_candidate_id: str = Field(..., description="ID of patch candidate being verified")
    applies_cleanly: bool = Field(False, description="Patch applies cleanly")
    regression_test_fails_before: bool = Field(False, description="Regression test fails on original commit")
    regression_test_passes_after: bool = Field(False, description="Regression test passes after patch")
    original_failure_not_reproduced: bool = Field(False, description="Original failure not reproduced")
    existing_tests_pass: bool = Field(False, description="Existing unit/integration tests pass")
    safety_invariants_pass: bool = Field(False, description="Safety invariants pass")
    performance_within_budget: bool = Field(False, description="Performance within budget")
    forbidden_change_scan_passes: bool = Field(False, description="Forbidden change scan passes")
    rollback_test_passes: bool = Field(False, description="Rollback test passes")
    verified: bool = Field(False, description="Overall verification result")
    details: Dict[str, Any] = Field(default_factory=dict, description="Detailed verification results")
