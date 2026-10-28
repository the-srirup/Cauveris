"""
Repair Package Builder for Cauveris.
Assembles the complete cryptographic, reversible repair package for an incident
and packages it into a verified zip archive.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from cauveris.analysis.model import TwinParameters
from cauveris.analysis.system_model import SystemModel
from cauveris.config import get_settings
from cauveris.patch.generator import PatchGenerator
from cauveris.patch.unified_diff import reverse_unified_diff
from cauveris.schemas.experiment import Experiment
from cauveris.schemas.hypothesis import Hypothesis
from cauveris.schemas.incident import Incident
from cauveris.schemas.patch import PatchCandidate, VerificationReport
from cauveris.simulation.runner import CloudToRobotDigitalTwin, DigitalTwinFaultInjectors

logger = logging.getLogger(__name__)


@dataclass
class PatchPackageResult:
    """The result of building a verified repair package."""

    incident_id: str
    repair_id: str
    package_dir: Path
    zip_path: Path
    checksum_sha256: str
    size_bytes: int
    manifest: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class PatchPackageBuilder:
    """Builds the authentic, evidence-backed repair package for an incident."""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()

    async def build_package(
        self,
        incident: Incident,
        patch: PatchCandidate,
        experiment: Optional[Experiment] = None,
        hypotheses: Optional[List[Hypothesis]] = None,
        verification_reports: Optional[List[VerificationReport]] = None,
        system_model: Optional[SystemModel] = None,
        output_dir: Optional[Union[Path, str]] = None,
    ) -> PatchPackageResult:
        """
        Assemble and write all package artifacts and build the sealed zip archive.
        """
        incident_id = str(incident.id)
        repair_id = str(patch.candidate_id)

        if output_dir:
            base_dir = Path(output_dir)
        else:
            base_dir = Path(self.settings.report_store_path) / incident_id

        package_dir = base_dir / "patch-package"
        package_dir.mkdir(parents=True, exist_ok=True)

        hypotheses_by_id = {
            h.hypothesis_id: h for h in (hypotheses or []) if getattr(h, "hypothesis_id", None)
        }

        # 1. Unified Diffs
        diff_text = patch.unified_diff or ""
        (package_dir / "fix.patch").write_text(diff_text, encoding="utf-8")
        (package_dir / "patch.patch").write_text(diff_text, encoding="utf-8")
        (package_dir / "rollback.patch").write_text(
            reverse_unified_diff(diff_text), encoding="utf-8"
        )

        # 2. Standalone Zero-Dependency Installer
        patch_gen = PatchGenerator()
        installer_code = patch_gen.generate_standalone_installer(patch)
        (package_dir / "apply_patch.py").write_text(installer_code, encoding="utf-8")

        # 3. Regression Test
        if patch.regression_test_patch:
            (package_dir / "regression_test.patch").write_text(
                patch.regression_test_patch, encoding="utf-8"
            )

        # 4. Verification Check Data
        verification_payload = {
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
        }
        (package_dir / "verification.json").write_text(
            json.dumps(verification_payload, indent=2), encoding="utf-8"
        )

        matching_report = next(
            (
                r
                for r in (verification_reports or [])
                if getattr(r, "patch_candidate_id", None) == patch.candidate_id
            ),
            None,
        )
        report_dict = (
            matching_report.model_dump()
            if hasattr(matching_report, "model_dump")
            else (dict(matching_report) if matching_report else verification_payload)
        )
        (package_dir / "verification-report.json").write_text(
            json.dumps(report_dict, indent=2, default=str), encoding="utf-8"
        )

        # 5. Before & After Digital Twin Evidence
        before_after_dir = package_dir / "before_after"
        traces_dir = before_after_dir / "traces"
        metrics_dir = before_after_dir / "metrics"
        replay_videos_dir = before_after_dir / "replay-videos"
        mcap_excerpts_dir = before_after_dir / "mcap-excerpts"

        for p in (traces_dir, metrics_dir, replay_videos_dir, mcap_excerpts_dir):
            p.mkdir(parents=True, exist_ok=True)

        after_window_ms = self._patched_batching_window(patch)
        before_window_ms = self._pre_patch_batching_window(patch, system_model)

        before_metrics, before_traces = self._run_twin_evidence(
            before_window_ms=before_window_ms, model=system_model
        )
        after_metrics, after_traces = self._run_twin_evidence(
            before_window_ms=after_window_ms, model=system_model
        )

        (traces_dir / "before_traces.json").write_text(
            json.dumps(before_traces, indent=2), encoding="utf-8"
        )
        (traces_dir / "after_traces.json").write_text(
            json.dumps(after_traces, indent=2), encoding="utf-8"
        )
        self._write_metrics_csv(metrics_dir / "before_metrics.csv", before_metrics)
        self._write_metrics_csv(metrics_dir / "after_metrics.csv", after_metrics)

        # MCAP excerpts
        try:
            from mcap.writer import Writer

            for name, payload in [
                ("before_excerpt.mcap", before_metrics),
                ("after_excerpt.mcap", after_metrics),
            ]:
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
                            "safety_status": (
                                "EMERGENCY_STOP" if trial["emergency_stop"] else "NOMINAL"
                            ),
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
            logger.debug(f"MCAP excerpt synthesis note: {e}")

        (replay_videos_dir / "README.txt").write_text(
            "Replay videos are not synthesized. Attach MCAP recordings captured from the real "
            "system at incident time to this directory before review.\n",
            encoding="utf-8",
        )

        # 6. Diagnosis, Provenance & Reports
        causal_claim = "Root cause addressed by verified parameter intervention"
        if experiment and experiment.hypothesis_id:
            hyp = hypotheses_by_id.get(experiment.hypothesis_id)
            if hyp:
                causal_claim = hyp.causal_claim

        pr_content = f"""# Fix for Incident {incident_id}

## Summary
Patch candidate `{repair_id}` addresses root cause:
{causal_claim}

## Changes
- **Files changed**: {len(patch.affected_files)}
- **Lines changed**: {patch.lines_changed}
- **Parameters changed**: {", ".join(e.parameter for e in patch.config_edits) or "N/A"}

## Verification
- Clean apply: {patch.applied_cleanly}
- Regression test fails before patch: {patch.regression_test_fails_before}
- Regression test passes after patch: {patch.regression_test_passes_after}
- Original failure eliminated in twin: {patch.original_failure_not_reproduced}
- Safety invariant checks: {patch.safety_invariants_pass}
- Performance budget within limits: {patch.performance_within_budget}
- Forbidden change scan: {patch.forbidden_change_scan_passes}
- Rollback reversibility test: {patch.rollback_test_passes}
- Overall verified: {patch.verified}

## Deployment
Execute the verified zero-dependency patch installer:
```bash
python apply_patch.py --check
python apply_patch.py
```

## Rollback
Execute rollback script or apply rollback.patch:
```bash
bash rollback.sh
# or
git apply --reverse patch.patch
```
"""
        (package_dir / "PULL_REQUEST.md").write_text(pr_content, encoding="utf-8")

        checklist_content = """# Patch Reviewer Checklist

## Correctness
- [ ] The patch addresses the root cause directly rather than suppressing symptoms
- [ ] The regression test fails on the pre-patch incident and passes post-patch
- [ ] The patch applies cleanly without conflicts

## Safety & Invariants
- [ ] Safety watchdogs and freshness budgets are not weakened
- [ ] No increase in timeouts without justification
- [ ] No monitoring or metric drops

## Policy & Security
- [ ] No credentials, secrets, or safety bypasses introduced
- [ ] No hardcoded values specific to a single environment
- [ ] Rollback script and reverse patch verified
"""
        (package_dir / "reviewer-checklist.md").write_text(checklist_content, encoding="utf-8")

        rollback_script = f"""#!/bin/bash
# Rollback script for patch {repair_id} (Incident {incident_id})
set -euo pipefail

echo "Reverting patch {repair_id} for incident {incident_id}..."
if [ -f "rollback.patch" ]; then
    patch -p0 -R < rollback.patch || patch -p1 -R < rollback.patch
elif [ -f "patch.patch" ]; then
    patch -p0 -R < patch.patch || patch -p1 -R < patch.patch
elif [ -f "apply_patch.py" ]; then
    python apply_patch.py --rollback
else
    echo "Error: No rollback patch or script found" >&2
    exit 1
fi
echo "Rollback successfully completed."
"""
        rollback_path = package_dir / "rollback.sh"
        rollback_path.write_text(rollback_script, encoding="utf-8")
        try:
            os.chmod(rollback_path, 0o755)
        except Exception:
            pass

        diagnosis = {
            "incident_id": incident_id,
            "repair_id": repair_id,
            "causal_claim": causal_claim,
            "hypothesis_id": getattr(experiment, "hypothesis_id", None) if experiment else None,
            "supporting_artifacts": (
                getattr(
                    hypotheses_by_id.get(getattr(experiment, "hypothesis_id", "")),
                    "supporting_artifact_ids",
                    [],
                )
                if experiment
                else []
            ),
        }
        (package_dir / "diagnosis.json").write_text(json.dumps(diagnosis, indent=2), encoding="utf-8")
        (package_dir / "diagnosis.md").write_text(
            f"# Diagnosis for Incident {incident_id}\n\n**Candidate:** {repair_id}\n\n{causal_claim}\n",
            encoding="utf-8",
        )

        provenance = {
            "incident_id": incident_id,
            "repair_id": repair_id,
            "bundle_path": getattr(incident, "bundle_path", ""),
            "pipeline": "ingestion -> timeline -> causality -> hypothesis -> twin-simulation -> patch-forge -> verification -> package",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "is_demonstration": bool(getattr(incident, "is_demonstration", False)),
        }
        (package_dir / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")

        capability = {
            "verification_level": "verified" if patch.verified else "unverified",
            "checks_passed": 9 if patch.verified else 0,
            "supported_for_download": bool(patch.verified),
            "affected_files": patch.affected_files,
            "score": patch.score,
        }
        (package_dir / "capability-report.json").write_text(json.dumps(capability, indent=2), encoding="utf-8")

        baseline = {
            "experiment_id": getattr(experiment, "experiment_id", None) if experiment else None,
            "status": "reproduced" if getattr(patch, "regression_test_fails_before", False) else "not_reproduced",
        }
        (package_dir / "baseline-results.json").write_text(json.dumps(baseline, indent=2), encoding="utf-8")

        post = {
            "experiment_id": getattr(experiment, "experiment_id", None) if experiment else None,
            "status": "cleared" if getattr(patch, "original_failure_not_reproduced", False) else "not_cleared",
        }
        (package_dir / "post-intervention-results.json").write_text(json.dumps(post, indent=2), encoding="utf-8")

        (package_dir / "limitations.md").write_text(
            "# Limitations\n\nResults are calibrated from the uploaded evidence and isolated digital twin replay. Real deployment rollout remains operator-controlled.\n",
            encoding="utf-8",
        )
        (package_dir / "application-instructions.md").write_text(
            "# Application Instructions\n\n1. Run `python apply_patch.py --check --target <dir>` to dry run.\n2. Run `python apply_patch.py --target <dir>` to apply.\n3. Run `python apply_patch.py --rollback --target <dir>` if needed to revert.\n",
            encoding="utf-8",
        )

        # 7. Checksums and Manifest
        manifest = {
            "format": "cauveris-repair-package/v1",
            "incident_id": incident_id,
            "patch_candidate_id": repair_id,
            "verification_level": "verified" if patch.verified else "diagnosed",
            "is_demonstration": provenance["is_demonstration"],
            "files": sorted(p.name for p in package_dir.iterdir() if p.is_file()),
            "checksums": "checksums.sha256",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        (package_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        checksum_lines = []
        for path in sorted(p for p in package_dir.iterdir() if p.is_file() and p.name != "checksums.sha256"):
            file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            checksum_lines.append(f"{file_hash}  {path.name}")
        (package_dir / "checksums.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

        # 8. Create the Compressed ZIP Archive
        zip_base = base_dir / f"cauveris-repair-package-{incident_id}"
        shutil.make_archive(str(zip_base), "zip", str(package_dir))
        zip_file = Path(f"{zip_base}.zip")

        # Also create standard alias in root of report store if different
        alias_file = Path(self.settings.report_store_path) / f"{incident_id}_patch_package.zip"
        if alias_file.resolve() != zip_file.resolve():
            alias_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(zip_file), str(alias_file))

        zip_bytes = zip_file.read_bytes()
        zip_hash = hashlib.sha256(zip_bytes).hexdigest()
        (zip_file.parent / f"{zip_file.name}.sha256").write_text(f"{zip_hash}  {zip_file.name}\n", encoding="utf-8")

        logger.info(
            f"Sealed repair package archive {zip_file} ({len(zip_bytes)} bytes, sha256: {zip_hash[:12]}...)"
        )

        return PatchPackageResult(
            incident_id=incident_id,
            repair_id=repair_id,
            package_dir=package_dir,
            zip_path=zip_file,
            checksum_sha256=zip_hash,
            size_bytes=len(zip_bytes),
            manifest=manifest,
        )

    def _patched_batching_window(self, patch: PatchCandidate) -> float:
        for edit in getattr(patch, "config_edits", []):
            if getattr(edit, "parameter", None) == "batching_window_ms":
                try:
                    return float(edit.target_value)
                except (TypeError, ValueError):
                    break
        m = re.search(
            r"\+\s*batching_window_ms\s*[:=]\s*(\d+(?:\.\d+)?)", getattr(patch, "unified_diff", "")
        )
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
        return 100.0

    def _pre_patch_batching_window(
        self, patch: PatchCandidate, model: Optional[Any]
    ) -> float:
        for edit in getattr(patch, "config_edits", []):
            if getattr(edit, "parameter", None) == "batching_window_ms" and getattr(edit, "current_value", None) is not None:
                try:
                    return float(edit.current_value)
                except (TypeError, ValueError):
                    break
        if model is not None and hasattr(model, "has_fitted_model") and model.has_fitted_model():
            return float(model.parameters.batching_window_ms)
        return 200.0

    def _run_twin_evidence(
        self,
        before_window_ms: float,
        model: Optional[Any] = None,
    ):
        """Run digital twin and generate before/after evidence reflecting patch parameters."""
        if model is not None and hasattr(model, "has_fitted_model") and model.has_fitted_model():
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
                    "duration_ms": round(
                        sum(t["inference_latency_ms"] for t in trials) / len(trials), 2
                    ),
                    "attributes": {
                        "batch_window_ms": before_window_ms,
                        "avg": True,
                        "unit": "ms",
                    },
                },
                {
                    "name": "robot_control_loop",
                    "duration_ms": round(
                        sum(t["total_latency_ms"] for t in trials) / len(trials), 2
                    ),
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

    @staticmethod
    def _write_metrics_csv(path: Path, trials: List[Dict[str, Any]]) -> None:
        ts_base = datetime.now(timezone.utc)
        lines = [
            "timestamp,batch_wait_ms,gpu_compute_ms,inference_latency_ms,network_delay_ms,total_latency_ms,is_stale,emergency_stop"
        ]
        for i, t in enumerate(trials):
            ts = ts_base.replace(microsecond=0).isoformat().replace("+00:00", "Z")
            lines.append(
                f"{ts},{t.get('batch_wait_ms', 0.0)},{t.get('gpu_compute_ms', 0.0)},{t.get('inference_latency_ms', 0.0)},"
                f"{t.get('network_delay_ms', 0.0)},{t.get('total_latency_ms', 0.0)},{int(bool(t.get('is_stale', False)))},{int(bool(t.get('emergency_stop', False)))}"
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
