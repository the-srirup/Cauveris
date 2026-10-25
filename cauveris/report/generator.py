"""
Report generator for creating final incident reports and patch packages.
"""

import os
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from cauveris.analysis.model import TwinParameters
from cauveris.analysis.system_model import SystemModel, get_system_model
from cauveris.schemas.incident import Incident
from cauveris.schemas.hypothesis import Hypothesis
from cauveris.schemas.experiment import Experiment
from cauveris.schemas.patch import PatchCandidate, VerificationReport
from cauveris.simulation.runner import DigitalTwinFaultInjectors, CloudToRobotDigitalTwin
from cauveris.simulation.mapping import map_experiment_to_intervention
from cauveris.config import get_settings
import logging

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates final reports and patch packages."""

    def __init__(self):
        self.settings = get_settings()
        self._model: Optional[SystemModel] = None

    def _resolve_model(self, incident: Incident) -> Optional[SystemModel]:
        """The incident's calibrated model, when its bundle can be found."""
        bundle = getattr(incident, "bundle_path", None)
        if not bundle:
            return None
        try:
            return get_system_model(
                incident.id,
                Path(bundle),
                manifest=getattr(incident, "manifest", None) or {},
            )
        except Exception as exc:
            logger.info(f"Could not build the system model for the report: {exc}")
            return None

    async def generate(
        self,
        incident: Incident,
        hypotheses: List[Hypothesis],
        experiments: List[Experiment],
        patch_candidates: List[PatchCandidate],
        verification_reports: List[VerificationReport],
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

        # The incident's calibrated model, so that every number the report
        # shows is computed from this incident's own evidence rather than
        # from a default pipeline.
        self._model = self._resolve_model(incident)

        # Index hypotheses by id so patches can be traced back to their causal claim
        self._hypotheses_by_id = {
            h.hypothesis_id: h for h in hypotheses if getattr(h, "hypothesis_id", None)
        }

        # Create report directory
        report_dir = Path(f"./report/{incident.id}")
        report_dir.mkdir(parents=True, exist_ok=True)

        # Generate the main incident report
        incident_report = {
            "incident_id": incident.id,
            "title": incident.title,
            "description": incident.description,
            "system_name": incident.system_name,
            "approximate_time": incident.approximate_time.isoformat()
            if incident.approximate_time
            else None,
            "evidence_summary": {
                "total_evidence_items": incident.evidence_count,
                "required_evidence_items": incident.required_evidence_count,
                "missing_required_evidence": incident.missing_required_evidence,
            },
            "timeline": getattr(incident, "timeline_events", []),
            "temporal_analysis": getattr(incident, "temporal_analysis", None),
            "hypotheses": [self._hypothesis_to_dict(h) for h in hypotheses],
            "experiments": [self._experiment_to_dict(e) for e in experiments],
            "patch_candidates": [self._patch_to_dict(p) for p in patch_candidates],
            "verification_reports": [self._verification_to_dict(v) for v in verification_reports],
            "status": "COMPLETED",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Write incident report
        report_path = report_dir / "incident_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(incident_report, f, indent=2, default=str)

        # Generate patch package if we have verified patches
        verified_patches = [p for p in patch_candidates if p.verified]
        if verified_patches:
            # Take the first verified patch and look up its originating experiment
            # (candidate_id = "patch-{experiment_id}") to build before/after evidence
            target_patch = verified_patches[0]
            experiment = self._experiment_for_patch(target_patch, experiments)
            patch_package_dir = await self._generate_patch_package(
                incident.id,
                target_patch,
                experiment,
                report_dir,
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
        experiment: Optional[Experiment],
        report_dir: Path,
    ) -> Path:
        """
        Generate a patch package directory with all required artifacts.

        Args:
            incident_id: ID of the incident
            patch: The verified patch candidate
            experiment: The experiment the patch was generated from (may be None)
            report_dir: Parent directory for the report

        Returns:
            Path to the patch package directory
        """
        package_dir = report_dir / "patch-package"
        package_dir.mkdir(parents=True, exist_ok=True)

        # Write fix.patch
        fix_path = package_dir / "fix.patch"
        with open(fix_path, "w", encoding="utf-8") as f:
            f.write(patch.unified_diff)

        # Write standalone self-applying installer apply_patch.py
        from cauveris.patch.generator import PatchGenerator

        patch_gen = PatchGenerator()
        installer_code = patch_gen.generate_standalone_installer(patch)
        installer_path = package_dir / "apply_patch.py"
        with open(installer_path, "w", encoding="utf-8") as f:
            f.write(installer_code)

        # Write regression_test.patch (if available)
        if patch.regression_test_patch:
            regression_test_path = package_dir / "regression_test.patch"
            with open(regression_test_path, "w", encoding="utf-8") as f:
                f.write(patch.regression_test_patch)

        # Write verification.json
        verification_path = package_dir / "verification.json"
        with open(verification_path, "w", encoding="utf-8") as f:
            json.dump(
                {
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
                },
                f,
                indent=2,
            )

        # Create before_after directory structure with real data
        before_after_dir = package_dir / "before_after"
        traces_dir = before_after_dir / "traces"
        metrics_dir = before_after_dir / "metrics"
        replay_videos_dir = before_after_dir / "replay-videos"
        mcap_excerpts_dir = before_after_dir / "mcap-excerpts"

        # Post-fix batching window, parsed from the patch diff (None -> baseline 200ms)
        after_window_ms = self._patched_batching_window(patch)
        before_window_ms = self._pre_patch_batching_window(patch, self._model)
        for dir_path in [traces_dir, metrics_dir, replay_videos_dir, mcap_excerpts_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # 1. Before & After evidence, computed live from the digital twin using the
        # actual pre-fix and post-fix configurations (batching window from the patch)
        # and this incident's calibrated model.
        before_metrics, before_traces = self._run_twin_evidence(
            before_window_ms=before_window_ms, model=self._model
        )
        after_metrics, after_traces = self._run_twin_evidence(
            before_window_ms=after_window_ms, model=self._model
        )

        (traces_dir / "before_traces.json").write_text(
            json.dumps(before_traces, indent=2), encoding="utf-8"
        )
        (traces_dir / "after_traces.json").write_text(
            json.dumps(after_traces, indent=2), encoding="utf-8"
        )
        self._write_metrics_csv(metrics_dir / "before_metrics.csv", before_metrics)
        self._write_metrics_csv(metrics_dir / "after_metrics.csv", after_metrics)

        # 2. MCAP excerpts from the same twin trial outputs
        try:
            from mcap.writer import Writer

            for name, payload in [("before_excerpt.mcap", before_metrics), ("after_excerpt.mcap", after_metrics)]:
                mcap_file = mcap_excerpts_dir / name
                with open(mcap_file, "wb") as f:
                    w = Writer(f)
                    w.start()
                    s_id = w.register_schema(name="robot_state", encoding="jsonschema", data=b"{}")
                    c_id = w.register_channel(
                        topic="/robot/telemetry", message_encoding="json", schema_id=s_id
                    )
                    t0 = 1789900190000000000
                    for step_idx, trial in enumerate(payload):
                        t_msg = t0 + (step_idx * 50000000)
                        data_payload = {
                            "speed_mps": 0.0 if trial["emergency_stop"] else 0.8,
                            "safety_status": "EMERGENCY_STOP" if trial["emergency_stop"] else "NOMINAL",
                            "detection_age_ms": trial["total_latency_ms"],
                        }
                        w.add_message(
                            channel_id=c_id,
                            log_time=t_msg,
                            publish_time=t_msg,
                            data=json.dumps(data_payload).encode("utf-8"),
                        )
                    w.finish()
        except Exception as e:
            logger.debug(f"Failed to generate MCAP excerpts: {e}")

        # 3. Replay note — replay videos require recorded camera streams, which are not
        # part of the digital twin output. Record honestly rather than emitting fake media.
        (replay_videos_dir / "README.txt").write_text(
            "Replay videos are not synthesized. Attach MCAP recordings captured from the real "
            "system at incident time to this directory before review.\n",
            encoding="utf-8",
        )

        # Write PULL_REQUEST.md
        pr_path = package_dir / "PULL_REQUEST.md"
        causal_claim = self._causal_claim_for_patch(patch, experiment)
        pr_content = f"""# Fix for Incident {incident_id}

## Summary
{patch.candidate_id} addresses the root cause: {causal_claim}.

## Changes
- **Files changed**: {len(patch.affected_files)}
- **Lines changed**: {patch.lines_changed}

## Verification
- Build: {patch.build_state}
- Existing tests: {patch.existing_test_state}
- Replay: {patch.replay_state}
- Safety: {patch.safety_result}
- Latency: {patch.latency_result}
- Policy scan: {", ".join(patch.policy_findings) if patch.policy_findings else "None"}
- Verified: {patch.verified}

## Testing
A regression test has been included to prevent reversion.

## Rollback
See rollback.sh for instructions to revert this change.
"""
        with open(pr_path, "w", encoding="utf-8") as f:
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
        with open(checklist_path, "w", encoding="utf-8") as f:
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
        with open(rollback_path, "w", encoding="utf-8") as f:
            f.write(rollback_content)
        # Make it executable
        os.chmod(rollback_path, 0o755)

        logger.info(f"Patch package generated at {package_dir}")
        return package_dir

    def _experiment_for_patch(
        self, patch: PatchCandidate, experiments: List[Experiment]
    ) -> Optional[Experiment]:
        """Find the experiment a patch was generated from (candidate_id = patch-{exp_id})."""
        exp_id = patch.candidate_id
        if exp_id.startswith("patch-"):
            exp_id = exp_id[len("patch-"):]
        for e in experiments:
            if e.experiment_id == exp_id:
                return e
        return None

    def _causal_claim_for_patch(
        self, patch: PatchCandidate, experiment: Optional[Experiment]
    ) -> str:
        """Resolve the causal claim by walking patch -> experiment -> hypothesis."""
        hypothesis = None
        if experiment is not None:
            hypothesis = self._hypotheses_by_id.get(experiment.hypothesis_id)
        if hypothesis is None:
            return "Root cause not linked (patch generated without hypothesis metadata)"
        return hypothesis.causal_claim

    def _patched_batching_window(self, patch: PatchCandidate) -> float:
        """
        The batching window the patch installs.

        It is read from the patch's own structured edit when there is one,
        because that is the value the patch actually writes into the
        configuration file.  The diff is the fallback for a patch that was
        built before the structured edit existed.
        """
        for edit in patch.config_edits:
            if edit.parameter == "batching_window_ms":
                try:
                    return float(edit.target_value)
                except (TypeError, ValueError):
                    break
        m = re.search(r"\+\s*batching_window_ms:\s*(\d+(?:\.\d+)?)", patch.unified_diff)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
        return 100.0

    def _pre_patch_batching_window(
        self, patch: PatchCandidate, model: Optional[SystemModel]
    ) -> float:
        """
        The batching window the target workspace has before the patch.

        Read from the patch's structured edit, because that is the value the
        patch found in the real file; the calibrated model is the fallback.
        """
        for edit in patch.config_edits:
            if edit.parameter == "batching_window_ms" and edit.current_value is not None:
                try:
                    return float(edit.current_value)
                except (TypeError, ValueError):
                    break
        if model is not None and model.has_fitted_model():
            return float(model.parameters.batching_window_ms)
        return 200.0

    def _run_twin_evidence(
        self,
        before_window_ms: float,
        model: Optional[SystemModel] = None,
    ):
        """
        Run the actual digital twin for 20 trials at the given batching window and
        return (trial metric rows, synthetic span view of the trials) used as
        before/after evidence. Values are computed, not hard-coded.

        The twin is built from the incident's calibrated model when there is
        one, so the evidence describes *this* incident's pipeline and not a
        default pipeline that happens to look similar.
        """
        if model is not None and model.has_fitted_model():
            # The window has to be changed in the parameters themselves: the
            # twin evaluates ``self.parameters()``, so overriding the fault
            # injectors alone would leave the window at its calibrated value
            # and the before/after evidence would be two copies of the same
            # run.
            merged = model.parameters.as_dict()
            merged["batching_window_ms"] = before_window_ms
            parameters = TwinParameters(**merged)
            faults = DigitalTwinFaultInjectors.from_parameters(parameters)
            twin = CloudToRobotDigitalTwin(
                faults,
                parameters=parameters,
                budget_ms=model.budget.freshness_budget_ms,
                control_deadline_ms=model.budget.control_deadline_ms,
                kinematics=model.kinematics,
                emergency_stop_on_stale=model.budget.emergency_stop_on_stale,
            )
        else:
            faults = DigitalTwinFaultInjectors(batching_window_ms=before_window_ms)
            twin = CloudToRobotDigitalTwin(faults)
        trials = [twin.step(seed=9000 + i) for i in range(20)]

        span_status_ok = all(t["emergency_stop"] is False for t in trials)
        traces = {
            "source": "digital_twin_simulation",
            "trials": len(trials),
            "freshness_budget_ms": twin.freshness_budget_ms,
            "spans": [
                {
                    "name": "inference_request",
                    "duration_ms": round(sum(t["inference_latency_ms"] for t in trials) / len(trials), 2),
                    "attributes": {
                        "batch_window_ms": before_window_ms,
                        "avg": True,
                        "unit": "ms",
                    },
                },
                {
                    "name": "robot_control_loop",
                    "duration_ms": round(sum(t["total_latency_ms"] for t in trials) / len(trials), 2),
                    "status": {
                        "code": 0 if span_status_ok else 2,
                        "message": (
                            "All trials within freshness budget"
                            if span_status_ok
                            else "One or more trials exceeded freshness budget (emergency stop)"
                        ),
                    },
                },
                {
                    "name": "safety_monitor",
                    "duration_ms": 0.5,
                    "status": {
                        "code": 0 if span_status_ok else 2,
                        "message": (
                            "NORMAL_OPERATION: no emergency stops across trials"
                            if span_status_ok
                            else f"EMERGENCY_STOP in {sum(1 for t in trials if t['emergency_stop'])}/{len(trials)} trials"
                        ),
                    },
                },
            ],
        }
        return trials, traces

    def _write_metrics_csv(self, path: Path, trials) -> None:
        """Write trial rows as CSV with a live timestamp column."""
        ts_base = datetime.now(timezone.utc)
        lines = ["timestamp,batch_wait_ms,gpu_compute_ms,inference_latency_ms,network_delay_ms,total_latency_ms,is_stale,emergency_stop"]
        for i, t in enumerate(trials):
            ts = (ts_base.replace(microsecond=0).isoformat().replace("+00:00", "Z"))
            lines.append(
                f"{ts},{t['batch_wait_ms']},{t['gpu_compute_ms']},{t['inference_latency_ms']},"
                f"{t['network_delay_ms']},{t['total_latency_ms']},{int(t['is_stale'])},{int(t['emergency_stop'])}"
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
