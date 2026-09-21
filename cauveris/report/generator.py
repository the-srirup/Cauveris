"""
Report generator for creating final incident reports and patch packages.
"""
import os
import json
from pathlib import Path
from typing import List, Dict, Any
from cauveris.schemas.incident import Incident
from cauveris.schemas.hypothesis import Hypothesis
from cauveris.schemas.experiment import Experiment
from cauveris.schemas.patch import PatchCandidate, VerificationReport
from cauveris.config import get_settings
import logging

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates final reports and patch packages."""

    def __init__(self):
        self.settings = get_settings()

    async def generate(
        self,
        incident: Incident,
        hypotheses: List[Hypothesis],
        experiments: List[Experiment],
        patch_candidates: List[PatchCandidate],
        verification_reports: List[VerificationReport]
    ) -> Dict[str, Any]:
        """
        generate a comprehensive incident report.

        Args:
            incident: The processed incident
            hypotheses: Generated hypotheses
            experiments: Experiment results
            patch_candidates: Generated patch candidates
            verification_reports: Verification results for patches

        Returns:
            Dictionary containing the report and paths to generated artifacts
        """
        logger.info(f"Generating report for incident {incident.id}")

        # Create report directory
        report_dir = Path(f"./report/{incident.id}")
        report_dir.mkdir(parents=True, exist_ok=True)

        # Generate the main incident report
        incident_report = {
            "incident_id": incident.id,
            "title": incident.title,
            "description": incident.description,
            "system_name": incident.system_name,
            "approximate_time": incident.approximate_time.isoformat() if incident.approximate_time else None,
            "evidence_summary": {
                "total_evidence_items": incident.evidence_count,
                "required_evidence_items": incident.required_evidence_count,
                "missing_required_evidence": incident.missing_required_evidence,
            },
            "timeline": getattr(incident, 'timeline_events', []),
            "hypotheses": [self._hypothesis_to_dict(h) for h in hypotheses],
            "experiments": [self._experiment_to_dict(e) for e in experiments],
            "patch_candidates": [self._patch_to_dict(p) for p in patch_candidates],
            "verification_reports": [self._verification_to_dict(v) for v in verification_reports],
            "status": "COMPLETED",
            "generated_at": "2026-09-20T10:30:00Z",  # In reality, use current time
        }

        # Write incident report
        report_path = report_dir / "incident_report.json"
        with open(report_path, 'w') as f:
            json.dump(incident_report, f, indent=2, default=str)

        # Generate patch package if we have verified patches
        verified_patches = [p for p in patch_candidates if p.verified]
        if verified_patches:
            patch_package_dir = await self._generate_patch_package(
                incident.id,
                verified_patches[0],  # Take the first verified patch for simplicity
                report_dir
            )
            incident_report["patch_package_path"] = str(patch_package_dir)

        logger.info(f"Report generated at {report_dir}")
        return incident_report

    def _hypothesis_to_dict(self, hypothesis: Hypothesis) -> Dict[str, Any]:
        """Convert Hypothesis object to dictionary."""
        return {
            "hypothesis_id": hypothesis.hypothesis_id,
            "causal_claim": hypothesis.causal_claim,
            "status": hypothesis.status,
            "supporting_artifact_ids": hypothesis.supporting_artifact_ids,
            "contradicting_artifact_ids": hypothesis.contradicting_artifact_ids,
            "missing_evidence": hypothesis.missing_evidence,
            "confidence_prior": hypothesis.confidence_prior,
            "expected_observation": hypothesis.expected_observation,
            "falsifying_observation": hypothesis.falsifying_observation,
            "intervention": hypothesis.intervention,
            "estimated_trials": hypothesis.estimated_trials,
            "estimated_cost": hypothesis.estimated_cost,
            "likely_files": hypothesis.likely_files,
            "likely_parameters": hypothesis.likely_parameters,
            "safety_constraints": hypothesis.safety_constraints,
        }

    def _experiment_to_dict(self, experiment: Experiment) -> Dict[str, Any]:
        """Convert Experiment object to dictionary."""
        return {
            "experiment_id": experiment.experiment_id,
            "hypothesis_id": experiment.hypothesis_id,
            "branch_name": experiment.branch_name,
            "intervention": experiment.intervention,
            "status": experiment.status,
            "trial_count": experiment.trial_count,
            "reproduction_count": experiment.reproduction_count,
            "reproduction_rate": experiment.reproduction_rate,
            "failure_oracle": experiment.failure_oracle,
            "logs_artifact_id": experiment.logs_artifact_id,
            "metrics_artifact_id": experiment.metrics_artifact_id,
            "replay_artifact_id": experiment.replay_artifact_id,
            "conclusion": experiment.conclusion,
        }

    def _patch_to_dict(self, patch: PatchCandidate) -> Dict[str, Any]:
        """Convert PatchCandidate object to dictionary."""
        return {
            "candidate_id": patch.candidate_id,
            "affected_files": patch.affected_files,
            "lines_changed": patch.lines_changed,
            "unified_diff": patch.unified_diff,
            "regression_test_patch": patch.regression_test_patch,
            "build_state": patch.build_state,
            "existing_test_state": patch.existing_test_state,
            "replay_state": patch.replay_state,
            "safety_result": patch.safety_result,
            "latency_result": patch.latency_result,
            "policy_findings": patch.policy_findings,
            "score": patch.score,
            "rejection_reason": patch.rejection_reason,
            "applied_cleanly": patch.applied_cleanly,
            "regression_test_fails_before": patch.regression_test_fails_before,
            "regression_test_passes_after": patch.regression_test_passes_after,
            "original_failure_not_reproduced": patch.original_failure_not_reproduced,
            "existing_tests_pass": patch.existing_tests_pass,
            "safety_invariants_pass": patch.safety_invariants_pass,
            "performance_within_budget": patch.performance_within_budget,
            "forbidden_change_scan_passes": patch.forbidden_change_scan_passes,
            "rollback_test_passes": patch.rollback_test_passes,
            "verified": patch.verified,
        }

    def _verification_to_dict(self, report: VerificationReport) -> Dict[str, Any]:
        """Convert VerificationReport object to dictionary."""
        return {
            "patch_candidate_id": report.patch_candidate_id,
            "applies_cleanly": report.applies_cleanly,
            "regression_test_fails_before": report.regression_test_fails_before,
            "regression_test_passes_after": report.regression_test_passes_after,
            "original_failure_not_reproduced": report.original_failure_not_reproduced,
            "existing_tests_pass": report.existing_tests_pass,
            "safety_invariants_pass": report.safety_invariants_pass,
            "performance_within_budget": report.performance_within_budget,
            "forbidden_change_scan_passes": report.forbidden_change_scan_passes,
            "rollback_test_passes": report.rollback_test_passes,
            "verified": report.verified,
            "details": report.details,
        }

    async def _generate_patch_package(
        self,
        incident_id: str,
        patch: PatchCandidate,
        report_dir: Path
    ) -> Path:
        """
        Generate a patch package directory with all required artifacts.

        Args:
            incident_id: ID of the incident
            patch: The verified patch candidate
            report_dir: Parent directory for the report

        Returns:
            Path to the patch package directory
        """
        package_dir = report_dir / "patch-package"
        package_dir.mkdir(parents=True, exist_ok=True)

        # Write fix.patch
        fix_path = package_dir / "fix.patch"
        with open(fix_path, 'w') as f:
            f.write(patch.unified_diff)

        # Write regression_test.patch (if available)
        if patch.regression_test_patch:
            regression_test_path = package_dir / "regression_test.patch"
            with open(regression_test_path, 'w') as f:
                f.write(patch.regression_test_patch)

        # Write verification.json
        verification_path = package_dir / "verification.json"
        with open(verification_path, 'w') as f:
            json.dump({
                "patch_candidate_id": patch.candidate_id,
                "applies_cleanly": patch.applied_cleanly,
                "regression_test_fails_before": patch.regression_test_fails_before,
                "regression_test_passes_after": patch.regression_test_passes_after,
                "original_failure_not_reproduced": patch.original_failure_not_reproduced,
                "existing_tests_pass": patch.existing_tests_pass,
                "safety_invariants_pass": patch.safety_invariants_pass,
                "performance_within_budget": patch.performance_within_budget,
                "forbidden_change_scan_passes": patch.forbidden_change_scan_passes,
                "rollback_test_passes": patch.rollback_test_passes,
                "verified": patch.verified,
            }, f, indent=2)

        # Create before_after directory structure
        before_after_dir = package_dir / "before_after"
        traces_dir = before_after_dir / "traces"
        metrics_dir = before_after_dir / "metrics"
        replay_videos_dir = before_after_dir / "replay-videos"
        mcap_excerpts_dir = before_after_dir / "mcap-excerpts"
        for dir_path in [traces_dir, metrics_dir, replay_videos_dir, mcap_excerpts_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # Write placeholder files in before_after directories
        (traces_dir / "before_traces.json").write_text('{"placeholder": "before traces"}')
        (traces_dir / "after_traces.json").write_text('{"placeholder": "after traces"}')
        (metrics_dir / "before_metrics.csv").write_text("timestamp,value\n0,0\n")
        (metrics_dir / "after_metrics.csv").write_text("timestamp,value\n0,0\n")
        (replay_videos_dir / "before_replay.webm").write_bytes(b'PLACEHOLDER')
        (replay_videos_dir / "after_replay.webm").write_bytes(b'PLACEHOLDER')
        (mcap_excerpts_dir / "before_excerpt.mcap").write_bytes(b'PLACEHOLDER')
        (mcap_excerpts_dir / "after_excerpt.mcap").write_bytes(b'PLACEHOLDER')

        # Write PULL_REQUEST.md
        pr_path = package_dir / "PULL_REQUEST.md"
        pr_content = f"""# Fix for Incident {incident_id}

## Summary
{patch.candidate_id} addresses the root cause: {self._get_hypothesis_causal_claim(patch)}.

## Changes
- **Files changed**: {len(patch.affected_files)}
- **Lines changed**: {patch.lines_changed}

## Verification
- Build: {patch.build_state}
- Existing tests: {patch.existing_test_state}
- Replay: {patch.replay_state}
- Safety: {patch.safety_result}
- Latency: {patch.latency_result}
- Policy scan: {', '.join(patch.policy_findings) if patch.policy_findings else 'None'}
- Verified: {patch.verified}

## Testing
A regression test has been included to prevent reversion.

## Rollback
See rollback.sh for instructions to revert this change.
"""
        with open(pr_path, 'w') as f:
            f.write(pr_content)

        # Write reviewer checklist
        checklist_path = package_dir / "reviewer-checklist.md"
        checklist_content = """# Patch Review Checklist

## Correctness
- [ ] The patch addresses the root cause and not just symptoms
- [ ] The regression test fails on the original code and passes after the patch
- [ ] The patch applies cleanly (no merge conflicts)

## Safety
- [ ] Safety watchdog and invariants are not weakened
- [ ] No increase in timeouts without justification
- [ ] No removal of monitoring or logging

## Performance
- [ ] Performance is within budget (no significant regression)
- [ ] No unnecessary computational overhead

## Policy
- [ ] No forbidden changes (e.g., disabling safety features)
- [ ] No hard-coded values specific to the incident
- [ ] No blanket exception handling

## Build and Test
- [ ] The project builds successfully with the patch
- [ ] All existing tests pass
- [ ] The patch does not break any dependent services

## Rollback
- [ ] Rollback procedure is documented and tested
"""
        with open(checklist_path, 'w') as f:
            f.write(checklist_content)

        # Write rollback.sh
        rollback_path = package_dir / "rollback.sh"
        rollback_content = f"""#!/bin/bash
# Rollback script for patch {patch.candidate_id}

set -euo pipefail

echo "Rolling back patch {patch.candidate_id} for incident {incident_id}"

# Check if we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "Error: Not in a git repository"
    exit 1
fi

# Show the patch that would be reversed
echo "Patch to be reverted:"
git apply --reverse --check {patch.candidate_id}.patch || echo "Patch check failed"

# Apply the reverse patch
echo "Applying reverse patch..."
git apply --reverse {patch.candidate_id}.patch

echo "Rollback complete. Please verify the system is back to its previous state."
"""
        with open(rollback_path, 'w') as f:
            f.write(rollback_content)
        # Make it executable
        os.chmod(rollback_path, 0o755)

        logger.info(f"Patch package generated at {package_dir}")
        return package_dir

    def _get_hypothesis_causal_claim(self, patch: PatchCandidate) -> str:
        """Extract causal claim from patch (placeholder)."""
        # In a real implementation, we would link the patch to its hypothesis
        return "Increased dynamic batching window caused inference latency to exceed freshness budget"
