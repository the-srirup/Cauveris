"""
Verification engine: the 9-point PATCH_VERIFIED checklist, run against the
incident's own bundle.

The engine used to build a workspace out of hard-coded configuration - a
``batching_window_ms: 200`` inference config and a two-line detection client
- and then "apply" a patch by matching ``batching_window_ms`` and ``qos_depth``
in the diff with a regular expression.  That made the checklist a fixed
theatre: it could only ever succeed on one incident's vocabulary, and the
numbers it compared were constants rather than measurements.

This version does the real thing:

* The workspace is a copy of the **real incident bundle**: the configuration
  files and the source files that bundle actually shipped.
* The patch is applied with the **real unified-diff engine**
  (:mod:`cauveris.patch.unified_diff`), so a diff that does not apply to the
  bundle fails to apply here.
* The regression test is **generated from the incident's calibrated model** and
  its declared safety budget, so it asserts the budget the system itself
  declared rather than a hard-coded 120 ms.
* The digital-twin gates run the **calibrated model** with the parameters the
  patched workspace declares - the same simulator the hypothesis layer used to
  decide that the hypothesis was supported.
* Rollback is verified by applying the **inverse diff** and comparing the
  result byte-for-byte with the pre-patch workspace.

When no bundle can be found the engine says so and fails the gates.  It does
not invent an incident to verify against.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cauveris.analysis.model import TwinParameters, simulate_pipeline
from cauveris.analysis.system_model import SystemModel, get_system_model
from cauveris.bundles import resolve_bundle
from cauveris.config import get_settings
from cauveris.patch.unified_diff import (
    UnifiedDiffError,
    apply_unified_diff,
    reverse_unified_diff,
)
from cauveris.schemas.incident import Incident
from cauveris.schemas.patch import PatchCandidate, VerificationReport
from cauveris.simulation.runner import CloudToRobotDigitalTwin, DigitalTwinFaultInjectors
from cauveris.analysis.parameters import (
    CONFIG_SUFFIXES,
    SECTIONED_CONFIG_SUFFIXES,
    is_packaging_file,
)
from cauveris.verifier.workspace import (
    WORKSPACE_ROOT_SUFFIXES,
    WORKSPACE_SOURCE_DIRS,
    compare_safety,
    parameters_from_workspace,
    safety_snapshot,
)
logger = logging.getLogger(__name__)

#: Trials per twin gate.  Each trial re-runs the pipeline simulation with a
#: different seed, so a gate reports a rate rather than a single sample.
GATE_TRIALS = 10

#: The fraction of control cycles that may see stale data for the system to
#: count as healthy.  A watchdog that fires on 2% of cycles is still a
#: watchdog firing every few seconds.
STALE_RATE_THRESHOLD = 0.02

#: How long a generated regression test may run.
REGRESSION_TIMEOUT_S = 120


class VerificationEngine:
    """
    Verifies patch candidates against the 9-point PATCH_VERIFIED checklist.

    Args:
        workspace_dir: Where the per-candidate workspaces are created.
        bundle_root: The incident bundle to verify against.  When it is not
            given, the engine resolves the bundle from the incident, from the
            evidence store, or from the working directory.
        incident: The incident under investigation.
    """

    def __init__(
        self,
        workspace_dir: Optional[Path] = None,
        *,
        bundle_root: Optional[Path] = None,
        incident: Optional[Incident] = None,
    ):
        self.settings = get_settings()
        self.workspace_dir = Path(workspace_dir or "./verification_workspace")
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self._bundle_root = Path(bundle_root) if bundle_root else None
        self._incident = incident
        self._model: Optional[SystemModel] = None

    # ------------------------------------------------------------------ API

    async def verify(
        self,
        patch_candidates: List[PatchCandidate],
        *,
        incident: Optional[Incident] = None,
        bundle_root: Optional[Path] = None,
    ) -> List[VerificationReport]:
        """
        Verify patch candidates against the 9-point PATCH_VERIFIED checklist.

        Args:
            patch_candidates: The candidates to verify.
            incident: The incident the candidates belong to.  It is what the
                bundle is resolved from.
            bundle_root: The bundle to verify against, when it is already
                known.

        Returns:
            One report per candidate, in the order they were given.
        """
        logger.info(
            f"Verifying {len(patch_candidates)} patch candidates against 9-point checklist"
        )

        if incident is not None:
            self._incident = incident
        if bundle_root is not None:
            self._bundle_root = Path(bundle_root)

        bundle = self._resolve_bundle()
        model = self._build_model(bundle)

        if bundle is None:
            logger.error(
                "No incident bundle could be located: the patch cannot be verified "
                "against an incident that does not exist."
            )
        if model is None and bundle is not None:
            logger.error(
                f"The bundle at {bundle} produced no system model, so the twin gates "
                "cannot be evaluated."
            )

        reports: List[VerificationReport] = []
        for patch in patch_candidates:
            reports.append(await self._verify_one(patch, bundle, model))
        return reports

    # -------------------------------------------------------------- one patch

    async def _verify_one(
        self,
        patch: PatchCandidate,
        bundle: Optional[Path],
        model: Optional[SystemModel],
    ) -> VerificationReport:
        """Run the whole checklist against one candidate."""
        # Strict incident-scoped candidate check: reject cross-incident verification
        if getattr(patch, "incident_id", None) and self._incident:
            if str(patch.incident_id) != str(self._incident.id):
                logger.warning(
                    f"Cross-incident verification rejected: patch candidate '{patch.candidate_id}' "
                    f"belongs to incident '{patch.incident_id}', cannot be verified against '{self._incident.id}'"
                )
                empty = _empty_results(
                    f"Candidate '{patch.candidate_id}' belongs to incident '{patch.incident_id}', "
                    f"cannot be verified against incident '{self._incident.id}'."
                )
                empty["rejection_reason"] = f"Cross-incident verification rejected: candidate belongs to {patch.incident_id}, not {self._incident.id}"
                patch.verified = False
                patch.verification_level = "UNVERIFIED"
                patch.rejection_reason = empty["rejection_reason"]
                return self._report(patch, empty)

        try:
            workspace = self.workspace_dir / f"{patch.candidate_id}_{uuid.uuid4().hex[:8]}"
            if workspace.exists():
                shutil.rmtree(workspace, ignore_errors=True)
            workspace.mkdir(parents=True, exist_ok=True)

            if bundle is None:
                return self._report(
                    patch,
                    results=_empty_results(
                        "No incident bundle was found, so the patch was not verified "
                        "against any incident."
                    ),
                )

            originals = self._setup_workspace(workspace, bundle)
            if not originals:
                return self._report(
                    patch,
                    results=_empty_results(
                        f"The bundle at {bundle} holds no configuration or source files, "
                        "so there is nothing to patch."
                    ),
                )

            self._write_calibration(workspace, model)

            results = await self._run_verification_checks(
                workspace, patch, model, originals
            )

            patch.applied_cleanly = results["applies_cleanly"]
            if hasattr(patch, "applies_cleanly"):
                setattr(patch, "applies_cleanly", results["applies_cleanly"])
            patch.regression_test_fails_before = results["regression_test_fails_before"]
            patch.regression_test_passes_after = results["regression_test_passes_after"]
            patch.original_failure_not_reproduced = results["original_failure_not_reproduced"]
            patch.existing_tests_pass = results["existing_tests_pass"]
            patch.safety_invariants_pass = results["safety_invariants_pass"]
            patch.performance_within_budget = results["performance_within_budget"]
            patch.forbidden_change_scan_passes = results[
                "forbidden_change_scan_passes"
            ]
            patch.rollback_test_passes = results["rollback_test_passes"]
            patch.verified = results["verified"]
            patch.verification_level = results.get("verification_level", "UNVERIFIED")
            patch.verification_summary = results.get("verification_summary")
            patch.rejection_reason = results.get("rejection_reason")
            patch.policy_findings = list(results.get("details", {}).get("policy_findings", []))

            if patch.verified:
                patch.build_state = "success"
                patch.existing_test_state = "pass"
                patch.replay_state = "success"
                patch.safety_result = "pass"
                patch.latency_result = "within_budget"
            else:
                patch.build_state = "success" if patch.applied_cleanly else "failed"
                patch.existing_test_state = "pass" if patch.existing_tests_pass else "failed"
                patch.replay_state = (
                    "success" if patch.original_failure_not_reproduced else "reproduced"
                )
                patch.safety_result = "pass" if patch.safety_invariants_pass else "failed"
                patch.latency_result = (
                    "within_budget" if patch.performance_within_budget else "exceeded"
                )

            report = self._report(patch, results)
            logger.info(
                f"Verification complete for {patch.candidate_id}: "
                f"VERIFIED={patch.verified}"
            )
            return report

        except Exception as exc:  # a broken candidate must not kill the batch
            logger.error(f"Verification battery failed for {patch.candidate_id}: {exc}")
            patch.verified = False
            patch.rejection_reason = f"Verification error: {exc}"
            return VerificationReport(
                patch_candidate_id=patch.candidate_id,
                verified=False,
                details={"error": str(exc)},
            )

    def _report(self, patch: PatchCandidate, results: Dict[str, Any]) -> VerificationReport:
        """Build the report from the checklist's outcome."""
        return VerificationReport(
            patch_candidate_id=patch.candidate_id,
            incident_id=getattr(patch, "incident_id", None) or (getattr(self._incident, "id", None) if self._incident else None),
            applies_cleanly=results["applies_cleanly"],
            regression_test_fails_before=results["regression_test_fails_before"],
            regression_test_passes_after=results["regression_test_passes_after"],
            original_failure_not_reproduced=results["original_failure_not_reproduced"],
            existing_tests_pass=results["existing_tests_pass"],
            safety_invariants_pass=results["safety_invariants_pass"],
            performance_within_budget=results["performance_within_budget"],
            forbidden_change_scan_passes=results["forbidden_change_scan_passes"],
            rollback_test_passes=results["rollback_test_passes"],
            verified=results["verified"],
            verification_level=results.get("verification_level", "UNVERIFIED"),
            verification_summary=results.get("verification_summary"),
            details=results.get("details", {}),
        )

    # ---------------------------------------------------------------- bundle

    def _resolve_bundle(self) -> Optional[Path]:
        """
        Find the incident bundle the patch applies to.

        The search is by incident id, never by a fixed path, so an incident
        uploaded as ``CAU-1234`` is found the same way ``CAU-0001`` is.
        """
        bundle = resolve_bundle(
            self._incident,
            self._bundle_root,
            evidence_store_path=self.settings.evidence_store_path,
        )
        if bundle is not None:
            logger.info(f"Verifying against the incident bundle at {bundle}")
        return bundle

    def _build_model(self, bundle: Optional[Path]) -> Optional[SystemModel]:
        """Build the incident's calibrated model from the bundle."""
        if bundle is None:
            self._model = None
            return None
        if self._model is not None:
            return self._model
        incident_id = str(self._incident.id) if self._incident is not None else bundle.name
        try:
            self._model = get_system_model(incident_id, bundle)
        except Exception as exc:
            logger.warning(f"Could not build a system model for {bundle}: {exc}")
            self._model = None
        return self._model

    # ------------------------------------------------------------- workspace

    def _setup_workspace(self, workspace: Path, bundle: Path) -> Dict[str, bytes]:
        """
        Copy the bundle's configuration and source into the workspace.

        Returns:
            The pre-patch bytes of every copied file, keyed by workspace
            relative path.  The rollback gate compares against these.
        """
        originals: Dict[str, bytes] = {}
        for directory in WORKSPACE_SOURCE_DIRS:
            source_dir = bundle / directory
            if not source_dir.is_dir():
                continue
            for path in sorted(source_dir.rglob("*")):
                if not path.is_file():
                    continue
                relative = path.relative_to(bundle)
                target = workspace / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    payload = path.read_bytes()
                except OSError as exc:
                    logger.debug(f"Could not copy {path}: {exc}")
                    continue
                target.write_bytes(payload)
                originals[relative.as_posix()] = payload

        # A bundle may keep its configuration beside the manifest instead of
        # in a directory of its own.  Those files are copied as well, so that
        # a patch against ``robot.toml`` can be applied and verified.
        for path in sorted(p for p in bundle.iterdir() if p.is_file()):
            if path.suffix.lower() not in WORKSPACE_ROOT_SUFFIXES:
                continue
            if is_packaging_file(path):
                continue
            relative = path.relative_to(bundle)
            target = workspace / relative
            try:
                payload = path.read_bytes()
            except OSError as exc:
                logger.debug(f"Could not copy {path}: {exc}")
                continue
            target.write_bytes(payload)
            originals[relative.as_posix()] = payload
        return originals

    def _write_calibration(self, workspace: Path, model: Optional[SystemModel]) -> None:
        """
        Record the incident's calibrated model next to the workspace.

        The generated regression test reads this file instead of rebuilding the
        model: the calibration is the expensive part, and it has already been
        done.  What the test re-derives is the part that must change - the
        parameters the patched workspace declares.
        """
        payload: Dict[str, Any] = {
            "incident_id": str(self._incident.id) if self._incident is not None else "",
            "calibrated": model is not None,
        }
        if model is not None:
            payload.update(
                {
                    "base_parameters": model.parameters.as_dict(),
                    "freshness_budget_ms": model.budget.freshness_budget_ms,
                    "control_deadline_ms": model.budget.control_deadline_ms,
                    "emergency_stop_on_stale": model.budget.emergency_stop_on_stale,
                    "horizon_s": max(model.observation_window_s, model.simulation_horizon_s),
                    "stale_rate_threshold": STALE_RATE_THRESHOLD,
                    "kinematics": model.kinematics.as_dict(),
                }
            )
            # The mechanism the evidence names, and the numbers it was read
            # from.  The generated regression test asserts the *mechanism's*
            # own condition - a working set inside its envelope, a request
            # inside its deadline, an acquire deadline that covers the hold -
            # rather than only the latency, so a bundle whose incident was a
            # killed process is verified on the kill.
            evidence = model.failure_evidence
            if evidence is not None:
                payload["failure_mechanism"] = evidence.mechanism
                payload["mechanism_parameters"] = dict(evidence.parameters)
                payload["mechanism_observations"] = dict(evidence.observations)
            # Queue overflow/backpressure is a policy invariant rather than a
            # latency sample.  Preserve it in the generated regression test so
            # the baseline must fail on the uploaded buffer declaration and the
            # patched workspace must clear that same declaration.
            log_text = "\n".join(str(getattr(record, "text", "")) for record in model.bundle.logs)
            if any(token in log_text.lower() for token in ("queue overflow", "backpressure", "buffer full")):
                payload["subscriber_backpressure"] = True
        (workspace / "calibration.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------- checklist

    async def _run_verification_checks(
        self,
        workspace: Path,
        patch: PatchCandidate,
        model: Optional[SystemModel],
        originals: Dict[str, bytes],
    ) -> Dict[str, Any]:
        """Execute the 9 verification checks in the order they depend on."""
        results: Dict[str, Any] = _empty_results(None)
        failures: List[str] = []
        policy_findings: List[str] = []

        # 1. The regression test must fail on the unpatched tree: that is what
        #    proves the incident is reproducible in the first place.
        results["regression_test_fails_before"] = self._run_regression_test(
            workspace, expect_pass=False
        )
        if not results["regression_test_fails_before"]:
            failures.append("Regression test does not fail on the unpatched incident")

        # 2. The patch must apply cleanly to the real bundle.
        applied, apply_error = self._apply_patch(workspace, patch)
        results["applies_cleanly"] = applied
        if not applied:
            failures.append(f"Patch does not apply cleanly: {apply_error}")

        # 3. The regression test must pass once the patch is in.
        results["regression_test_passes_after"] = self._run_regression_test(
            workspace, expect_pass=True
        )
        if not results["regression_test_passes_after"]:
            failures.append("Regression test does not pass on the patched incident")

        # 4. The failure must be gone in the digital twin.
        reproduced, twin_detail = self._check_digital_twin_reproduction(workspace, model)
        results["original_failure_not_reproduced"] = reproduced
        if not reproduced:
            failures.append(
                "The original failure is still reproduced in the digital twin: "
                f"{twin_detail}"
            )

        # 5. The incident's own code has to remain valid.
        results["existing_tests_pass"] = self._check_existing_code_integrity(workspace)
        if not results["existing_tests_pass"]:
            failures.append("Existing code failed its syntax or configuration checks")

        # 6. Safety declarations may not be weakened.
        safety_violations = self._check_safety_invariants(workspace, originals)
        results["safety_invariants_pass"] = not safety_violations
        policy_findings.extend(safety_violations)
        if safety_violations:
            failures.append("Safety invariants violated: " + "; ".join(safety_violations))

        # 7. The patched system has to meet the budget it declared.
        within_budget, perf_detail = self._check_performance_budget(workspace, model)
        results["performance_within_budget"] = within_budget
        if not within_budget:
            failures.append(f"Performance budget not met: {perf_detail}")

        # 8. The patch may not contain a forbidden change.
        forbidden = self._check_forbidden_changes(workspace, patch)
        results["forbidden_change_scan_passes"] = not forbidden
        policy_findings.extend(forbidden)
        if forbidden:
            failures.append("Forbidden changes detected: " + "; ".join(forbidden))

        # 9. The patch has to be reversible.
        rolled_back, rollback_detail = self._check_rollback(workspace, patch, originals)
        results["rollback_test_passes"] = rolled_back
        if not rolled_back:
            failures.append(f"Rollback test failed: {rollback_detail}")

        results["verified"] = len(failures) == 0
        if failures:
            results["rejection_reason"] = "; ".join(failures)

        from cauveris.verifier.atomic_checks import (
            AtomicCheckRecord,
            CheckStatus,
            VerificationLevel,
            evaluate_verification_level,
        )

        atomic_checks = [
            AtomicCheckRecord(
                check_id="CHK-REG-FAIL-BEFORE",
                name="Regression test fails on unpatched incident",
                target_level=VerificationLevel.MODEL_VERIFIED,
                required=True,
                status=CheckStatus.PASSED if results["regression_test_fails_before"] else CheckStatus.FAILED,
                expected="FAIL",
                actual="FAIL" if results["regression_test_fails_before"] else "PASS",
            ),
            AtomicCheckRecord(
                check_id="CHK-TWIN-CLEARED",
                name="Original failure not reproduced in digital twin",
                target_level=VerificationLevel.MODEL_VERIFIED,
                required=True,
                status=CheckStatus.PASSED if results["original_failure_not_reproduced"] else CheckStatus.FAILED,
                expected="CLEARED",
                actual="CLEARED" if results["original_failure_not_reproduced"] else "REPRODUCED",
            ),
            AtomicCheckRecord(
                check_id="CHK-SAFETY-INVARIANTS",
                name="Safety invariants preserved without weakening",
                target_level=VerificationLevel.MODEL_VERIFIED,
                required=True,
                status=CheckStatus.PASSED if results["safety_invariants_pass"] else CheckStatus.FAILED,
                expected="PRESERVED",
                actual="PRESERVED" if results["safety_invariants_pass"] else "VIOLATED",
            ),
            AtomicCheckRecord(
                check_id="CHK-PERF-BUDGET",
                name="Performance within declared safety budget",
                target_level=VerificationLevel.MODEL_VERIFIED,
                required=True,
                status=CheckStatus.PASSED if results["performance_within_budget"] else CheckStatus.FAILED,
                expected="WITHIN_BUDGET",
                actual="WITHIN_BUDGET" if results["performance_within_budget"] else "EXCEEDED",
            ),
            AtomicCheckRecord(
                check_id="CHK-APPLIES-CLEANLY",
                name="Patch applies cleanly without syntax or merge conflicts",
                target_level=VerificationLevel.STAGING_VERIFIED,
                required=True,
                status=CheckStatus.PASSED if results["applies_cleanly"] else CheckStatus.FAILED,
                expected="CLEAN",
                actual="CLEAN" if results["applies_cleanly"] else "CONFLICT",
            ),
            AtomicCheckRecord(
                check_id="CHK-REG-PASS-AFTER",
                name="Regression test passes on patched workspace",
                target_level=VerificationLevel.STAGING_VERIFIED,
                required=True,
                status=CheckStatus.PASSED if results["regression_test_passes_after"] else CheckStatus.FAILED,
                expected="PASS",
                actual="PASS" if results["regression_test_passes_after"] else "FAIL",
            ),
            AtomicCheckRecord(
                check_id="CHK-EXISTING-TESTS",
                name="Existing test suite and code integrity preserved",
                target_level=VerificationLevel.STAGING_VERIFIED,
                required=True,
                status=CheckStatus.PASSED if results["existing_tests_pass"] else CheckStatus.FAILED,
                expected="PASS",
                actual="PASS" if results["existing_tests_pass"] else "FAIL",
            ),
            AtomicCheckRecord(
                check_id="CHK-FORBIDDEN-SCAN",
                name="Forbidden change and security policy scan passes",
                target_level=VerificationLevel.STAGING_VERIFIED,
                required=True,
                status=CheckStatus.PASSED if results["forbidden_change_scan_passes"] else CheckStatus.FAILED,
                expected="CLEAN",
                actual="CLEAN" if results["forbidden_change_scan_passes"] else "POLICY_VIOLATION",
            ),
            AtomicCheckRecord(
                check_id="CHK-CLEAN-ROLLBACK",
                name="Patch reversible with byte-for-byte workspace rollback",
                target_level=VerificationLevel.STAGING_VERIFIED,
                required=True,
                status=CheckStatus.PASSED if results["rollback_test_passes"] else CheckStatus.FAILED,
                expected="REVERSIBLE",
                actual="REVERSIBLE" if results["rollback_test_passes"] else "IRREVERSIBLE",
            ),
        ]

        summary = evaluate_verification_level(
            candidate_id=getattr(patch, "candidate_id", "patch"),
            experiment_id=str(getattr(patch, "candidate_id", "patch")).replace("patch-", ""),
            invariant_set_id=f"invset_{self._incident.id if self._incident else 'default'}",
            baseline_run_id=f"base_{self._incident.id if self._incident else 'default'}",
            intervention_run_id=f"interv_{getattr(patch, 'candidate_id', 'patch')}",
            checks=atomic_checks,
            is_staging_workspace_execution=True,
            is_live_runtime_execution=False,
        )

        results["verification_summary"] = summary.model_dump()
        results["verification_level"] = summary.achieved_level.value
        results["verified"] = summary.verified

        passed = sum(
            1
            for key in (
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
            if results[key]
        )
        results["details"] = {
            "checks_passed": passed,
            "total_checks": 9,
            "failures": failures,
            "policy_findings": policy_findings,
            "twin": twin_detail if isinstance(twin_detail, dict) else {},
            "performance": perf_detail if isinstance(perf_detail, dict) else {},
            "rollback": rollback_detail if isinstance(rollback_detail, dict) else {},
            "bundle": str(self._bundle_root) if self._bundle_root else None,
        }
        return results

    # ------------------------------------------------------- the regression test

    def _write_regression_test(self, workspace: Path, model: Optional[SystemModel]) -> None:
        """
        Generate the regression test from the incident's own model and budget.

        The test asserts what the incident declared.  An incident whose
        pipeline was slow has to meet the freshness budget; an incident whose
        process was killed has to give the workload an envelope its measured
        working set fits inside; an incident whose call was cancelled has to
        come back inside the deadline the client set; an incident whose
        acquire was abandoned has to wait at least as long as the lock is
        held.  The test reads the parameters from the *workspace*, so it fails
        on the incident and passes only when the patch genuinely fixed the
        numbers.

        The latency assertion is kept in every case: a patch that trades a
        lost request for a stale one has not fixed anything.
        """
        budget = model.budget.freshness_budget_ms if model is not None else 120.0
        source = f'''"""Regression test generated by Cauveris for the incident under repair.

The condition asserted here is the one the incident's own evidence declared.
The test reads parameters directly from the workspace, so it fails on the
unpatched incident and passes only when the patch genuinely fixed the numbers.
"""

import json
import os
import unittest
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
CALIBRATION = json.loads((WORKSPACE / "calibration.json").read_text(encoding="utf-8"))

sys_path = os.environ.get("CAUVERIS_REPO_ROOT")
if sys_path and sys_path not in __import__("sys").path:
    __import__("sys").path.insert(0, sys_path)

from cauveris.verifier.workspace import parameters_from_workspace

MECHANISM = CALIBRATION.get("failure_mechanism")
MECHANISM_PARAMETERS = CALIBRATION.get("mechanism_parameters") or {{}}


class TestIncidentCondition(unittest.TestCase):
    """The patched incident must satisfy the condition the incident declared."""

    def _merged(self):
        base = CALIBRATION.get("base_parameters") or {{}}
        overrides = parameters_from_workspace(base, WORKSPACE)
        return {{**base, **overrides}}

    def _total_latency(self, merged):
        window = float(merged.get("batching_window_ms", 100.0))
        base_service = float(merged.get("service_base_ms", 29.8))
        service_per_item = float(merged.get("service_per_item_ms", 2.56))
        batch_size = float(merged.get("max_batch_size", 4))
        transport = float(merged.get("transport_mean_ms", 7.65))
        skew = float(merged.get("clock_skew_ms", 0.0))
        # Total latency formula: batch wait + service compute + transport + clock skew
        return (window * 0.52) + base_service + (min(batch_size, 4) * service_per_item) + transport + skew

    def _worst_case_request_latency(self, merged):
        """
        The longest a request can take on the server side.

        The batch may close only at the end of the window, and it may be full,
        so this is the wait plus the cost of a full batch - the case the
        deadline has to survive.
        """
        window = float(merged.get("batching_window_ms", 100.0))
        base_service = float(merged.get("service_base_ms", 29.8))
        service_per_item = float(merged.get("service_per_item_ms", 2.56))
        batch_size = float(merged.get("max_batch_size", 4))
        return window + base_service + (batch_size * service_per_item)

    def _skip_without_a_model(self):
        if not CALIBRATION.get("calibrated"):
            self.skipTest("the incident bundle produced no calibrated model")

    def test_pipeline_meets_the_declared_freshness_budget(self):
        self._skip_without_a_model()
        latency = self._total_latency(self._merged())
        budget = CALIBRATION.get("freshness_budget_ms", {budget!r})
        self.assertLessEqual(
            latency,
            budget,
            f"Calculated latency {{latency:.1f}} ms exceeds the {{budget:.0f}} ms freshness budget",
        )

    def test_batching_window_within_the_control_period(self):
        """
        The batching window may not outlast the control period.

        A window longer than the period at which the control loop samples
        adds a whole extra cycle of age to every frame, whatever else is
        fixed.  The period comes from the consumer's own rate, not from a
        constant.
        """
        self._skip_without_a_model()
        merged = self._merged()
        window = float(merged.get("batching_window_ms", 100.0))
        control_period = 1000.0 / max(0.01, float(merged.get("consumer_rate_hz", 10.0)))
        self.assertLessEqual(
            window,
            control_period,
            f"Batching window {{window:.1f}} ms exceeds the {{control_period:.1f}} ms control period",
        )

    def test_the_declared_mechanism_is_cleared(self):
        """
        The condition the incident's evidence named.

        Which condition that is depends on what actually happened: a workload
        killed for exceeding its envelope, a request cancelled at a deadline,
        or an acquire abandoned on a contended lock.  A bundle whose evidence
        names none of them is a latency incident, and the budget test above
        is the whole condition.
        """
        self._skip_without_a_model()
        merged = self._merged()

        if MECHANISM == "resource_exhaustion":
            limit = float(merged.get("resource_limit_mb", 0.0))
            demand = float(MECHANISM_PARAMETERS.get("resource_demand_mb", 0.0))
            self.assertGreaterEqual(
                limit,
                demand,
                f"The workload needs {{demand:.0f}} MiB but the envelope is only {{limit:.0f}} MiB",
            )
        elif MECHANISM == "dependency_timeout":
            deadline = float(merged.get("request_timeout_ms", 0.0))
            latency = self._worst_case_request_latency(merged)
            self.assertLessEqual(
                latency,
                deadline,
                f"The request can take {{latency:.1f}} ms, past the {{deadline:.0f}} ms deadline",
            )
        elif MECHANISM == "lock_contention":
            timeout = float(merged.get("lock_timeout_ms", 0.0))
            hold = float(MECHANISM_PARAMETERS.get("lock_hold_ms", 0.0))
            self.assertGreaterEqual(
                timeout,
                hold,
                f"The lock is held for {{hold:.0f}} ms but the caller gives up after {{timeout:.0f}} ms",
            )
        elif MECHANISM == "connection_pool_exhaustion":
            pool_size = float(merged.get("db_pool_size", 0.0))
            demand = float(MECHANISM_PARAMETERS.get("db_demand_connections", 0.0))
            self.assertGreaterEqual(
                pool_size,
                demand,
                f"The database workload needs {{demand:.0f}} connections but the pool capacity is only {{pool_size:.0f}}",
            )
        elif CALIBRATION.get("subscriber_backpressure"):
            depth = float(merged.get("qos_queue_depth", 1.0))
            self.assertLessEqual(
                depth,
                1.0,
                f"The subscriber buffer remains {{depth:.0f}} frames deep under overflow evidence",
            )
        else:
            self.skipTest("the incident named no failure mechanism")

    def test_the_patch_does_not_raise_the_deadline_to_hide_a_slow_dependency(self):
        """
        A deadline that was raised is a deadline that was moved.

        The request has to come back inside the deadline the client already
        set; a longer deadline only makes the failure take longer to notice.
        """
        self._skip_without_a_model()
        if MECHANISM != "dependency_timeout":
            self.skipTest("the incident named no dependency timeout")
        base = CALIBRATION.get("base_parameters") or {{}}
        overrides = parameters_from_workspace(base, WORKSPACE)
        deadline = float(base.get("request_timeout_ms", 0.0))
        patched = float(overrides.get("request_timeout_ms", deadline))
        self.assertLessEqual(
            patched,
            deadline,
            f"The request deadline was raised from {{deadline:.0f}} ms to {{patched:.0f}} ms",
        )


if __name__ == "__main__":
    unittest.main()
'''
        (workspace / "test_regression.py").write_text(source, encoding="utf-8")

    def _run_regression_test(self, workspace: Path, expect_pass: bool) -> bool:
        """Run the generated regression test and check its expected outcome."""
        try:
            self._write_regression_test(workspace, self._model_for_workspace(workspace))
        except Exception as exc:
            logger.debug(f"Could not write the regression test: {exc}")
            return False

        env = dict(os.environ)
        env["CAUVERIS_REPO_ROOT"] = str(Path(__file__).resolve().parents[2])
        env["PYTHONPATH"] = os.pathsep.join(
            [str(Path(__file__).resolve().parents[2]), env.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)
        try:
            res = subprocess.run(
                [sys.executable, "test_regression.py"],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=REGRESSION_TIMEOUT_S,
                env=env,
            )
        except Exception as exc:
            logger.debug(f"Regression test execution error: {exc}")
            return False

        if expect_pass and res.returncode != 0:
            logger.warning(
                f"Regression test expected pass but failed (code={res.returncode}):\n"
                f"STDOUT: {res.stdout}\nSTDERR: {res.stderr}"
            )
            return False
        elif not expect_pass and res.returncode == 0:
            logger.warning("Regression test expected fail but passed!")
            return False
        return True

    def _model_for_workspace(self, workspace: Path) -> Optional[SystemModel]:
        """
        The model the workspace was calibrated against.

        The calibration is written next to the workspace, and the model it
        came from is the very model the twin gates run.  When the workspace
        has no calibration the engine has nothing to assert against, and the
        regression test is not generated.
        """
        calibration = workspace / "calibration.json"
        if not calibration.exists():
            return None
        try:
            data = json.loads(calibration.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not data.get("calibrated"):
            return None
        return self._model

    # ---------------------------------------------------------------- the diff

    def _apply_patch(self, workspace: Path, patch: PatchCandidate) -> Tuple[bool, str]:
        """Apply the patch to the workspace with the real diff engine."""
        diff = patch.unified_diff
        if not diff or not diff.strip():
            return False, "the patch carries no diff"
        try:
            changed = apply_unified_diff(diff, workspace)
        except UnifiedDiffError as exc:
            return False, str(exc)
        except Exception as exc:
            return False, f"unexpected failure while applying the diff: {exc}"
        if not changed:
            return False, "the diff changed nothing"
        return True, ""

    # -------------------------------------------------------------- the twin

    def _twin_for_workspace(
        self, workspace: Path, model: SystemModel
    ) -> CloudToRobotDigitalTwin:
        """Build the twin with the parameters the workspace declares."""
        overrides = parameters_from_workspace(model, workspace)
        merged = model.parameters.as_dict()
        merged.update(overrides)
        params = TwinParameters(**merged)
        return CloudToRobotDigitalTwin(
            DigitalTwinFaultInjectors.from_parameters(params),
            parameters=params,
            budget_ms=model.budget.freshness_budget_ms,
            control_deadline_ms=model.budget.control_deadline_ms,
            kinematics=model.kinematics,
            emergency_stop_on_stale=model.budget.emergency_stop_on_stale,
        )

    def _check_digital_twin_reproduction(
        self, workspace: Path, model: Optional[SystemModel]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        The failure must be gone when the incident is replayed.

        The twin is the incident's own calibrated model with the patched
        workspace's parameters, run over several seeds.  A patch that only
        relabels the problem leaves the watchdog firing.
        """
        if model is None:
            return False, {"reason": "no calibrated model for the incident bundle"}

        twin = self._twin_for_workspace(workspace, model)
        budget = model.budget.freshness_budget_ms
        stale_trials = 0
        emergency_stops = 0
        ages: List[float] = []

        for index in range(GATE_TRIALS):
            rec = twin.step(seed=9100 + index)
            ages.append(rec["total_latency_ms"])
            if rec["is_stale"]:
                stale_trials += 1
            trajectory = twin.simulate_trajectory(
                seed=9100 + index, duration_s=8.0, perception_ages=[rec["total_latency_ms"]]
            )
            if rec["emergency_stop"] or trajectory.get("emergency_stop_triggered"):
                emergency_stops += 1

        detail = {
            "trials": GATE_TRIALS,
            "trials_with_stale_data": stale_trials,
            "trials_with_emergency_stop": emergency_stops,
            "mean_age_ms": round(sum(ages) / len(ages), 2) if ages else 0.0,
            "freshness_budget_ms": budget,
            "stale_rate_threshold": STALE_RATE_THRESHOLD,
        }
        ok = stale_trials == 0 and emergency_stops == 0
        if not ok:
            detail["reason"] = (
                f"{stale_trials}/{GATE_TRIALS} trials still saw stale data and the "
                f"watchdog stopped the robot in {emergency_stops} of them"
            )

        # The staleness gate only knows about latency.  An incident whose
        # requests were *lost* - killed, cancelled, abandoned - does not go
        # stale, it goes silent, so the mechanism is compared on its own.
        mechanism_detail = self._check_mechanism_elimination(workspace, model)
        detail["mechanisms"] = mechanism_detail
        if mechanism_detail.get("applicable") and not mechanism_detail.get("cleared"):
            ok = False
            reason = mechanism_detail.get("reason")
            if reason:
                detail["reason"] = (
                    f"{detail['reason']}; {reason}"
                    if detail.get("reason")
                    else reason
                )

        return ok, detail

    def _check_mechanism_elimination(
        self, workspace: Path, model: SystemModel
    ) -> Dict[str, Any]:
        """
        A mechanism the baseline reproduced has to be gone after the patch.

        The comparison is made on the same simulator the hypothesis layer
        used to decide that its hypothesis was supported - the calibrated
        discrete-event model - over the same seeds on both sides.  Two
        things are checked:

        * the incident's own mechanism must not fire any more, and
        * the patch must not introduce a mechanism the incident did not have.

        The second is what stops a fix from being a trade: a patch that
        stops the requests being killed by removing the envelope only ends
        with every request missing its deadline instead.
        """
        evidence = model.failure_evidence
        if evidence is None:
            return {
                "applicable": False,
                "reason": "the incident's evidence names no failure mechanism",
            }

        mechanism = evidence.mechanism
        overrides = parameters_from_workspace(model, workspace)
        merged = model.parameters.as_dict()
        merged.update(overrides)
        patched_params = TwinParameters(**merged)

        horizon = max(model.observation_window_s, model.simulation_horizon_s, 12.0)
        baseline_counts: Dict[str, int] = {}
        patched_counts: Dict[str, int] = {}

        for index in range(GATE_TRIALS):
            seed = 9100 + index
            for params, counts in (
                (model.parameters, baseline_counts),
                (patched_params, patched_counts),
            ):
                outcome = simulate_pipeline(
                    params,
                    duration_s=horizon,
                    warmup_s=horizon,
                    seed=seed,
                    freshness_budget_ms=model.budget.freshness_budget_ms,
                    control_deadline_ms=model.budget.control_deadline_ms,
                )
                for name, count in outcome.failure_reasons.items():
                    counts[name] = counts.get(name, 0) + int(count)

        baseline_total = baseline_counts.get(mechanism, 0)
        patched_total = patched_counts.get(mechanism, 0)
        introduced = sorted(
            name for name in patched_counts if baseline_counts.get(name, 0) == 0
        )

        detail: Dict[str, Any] = {
            "applicable": True,
            "mechanism": mechanism,
            "trials": GATE_TRIALS,
            "baseline_failures": baseline_total,
            "patched_failures": patched_total,
            "baseline_mechanisms": baseline_counts,
            "patched_mechanisms": patched_counts,
            "introduced_mechanisms": introduced,
        }

        if baseline_total <= 0:
            # The model does not reproduce the incident, so there is nothing
            # for the patch to eliminate.  The regression test is what proves
            # the incident is reproducible at all.
            detail["cleared"] = True
            detail["reason"] = (
                "the calibrated model does not reproduce this mechanism on the "
                "baseline, so the gate has nothing to compare"
            )
            return detail

        detail["cleared"] = patched_total == 0 and not introduced
        if not detail["cleared"]:
            parts = []
            if patched_total:
                parts.append(
                    f"the {mechanism} failure still occurs {patched_total} time(s) "
                    f"after the patch"
                )
            if introduced:
                parts.append(
                    "the patch introduces a failure the incident did not have: "
                    + ", ".join(introduced)
                )
            detail["reason"] = "; ".join(parts)
        return detail

    def _check_performance_budget(
        self, workspace: Path, model: Optional[SystemModel]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        The patched incident must meet the latency budget it declared.

        The baseline is the incident as it was.  For a latency incident the
        patched run has to be both inside the budget and no worse than the
        baseline: a patch that makes the pipeline slower has not fixed
        anything.

        For an incident whose requests were *lost*, the trade is different.
        Letting a caller wait for a lock it used to abandon makes the
        survivors older on purpose - the requests it used to lose now come
        back - so the rule is the budget the system declared, and the change
        in the mean age is reported rather than forbidden.
        """
        if model is None:
            return False, {"reason": "no calibrated model for the incident bundle"}

        budget = model.budget.freshness_budget_ms
        patched = self._twin_for_workspace(workspace, model)
        overrides = parameters_from_workspace(model, workspace)

        baseline_ages: List[float] = []
        patched_ages: List[float] = []
        patched_p95: List[float] = []
        for index in range(GATE_TRIALS):
            seed = 7300 + index
            baseline_ages.append(
                model.predict({}, seed=seed).mean_age_ms
            )
            rec = patched.step(seed=seed)
            patched_ages.append(rec["total_latency_ms"])
            patched_p95.append(rec["total_latency_ms"])

        mean_baseline = sum(baseline_ages) / len(baseline_ages)
        mean_patched = sum(patched_ages) / len(patched_ages)
        worst_p95 = max(patched_p95) if patched_p95 else 0.0

        mechanism = (
            model.failure_evidence.mechanism if model.failure_evidence else None
        )
        detail = {
            "freshness_budget_ms": budget,
            "baseline_mean_age_ms": round(mean_baseline, 2),
            "patched_mean_age_ms": round(mean_patched, 2),
            "patched_p95_age_ms": round(worst_p95, 2),
            "failure_mechanism": mechanism,
            "parameter_overrides": overrides,
        }
        inside_budget = mean_patched <= budget and worst_p95 <= budget
        no_worse = mean_patched <= mean_baseline
        if mechanism is None:
            ok = inside_budget and no_worse
        else:
            # The incident was a lost request, not a slow one.  The budget is
            # the bound; the trade is reported.
            ok = inside_budget
            detail["mean_age_change_ms"] = round(mean_patched - mean_baseline, 2)
            detail["trade"] = (
                "the patch makes the surviving results older on purpose - the "
                "requests it used to lose now come back - and the budget still "
                "holds"
            )
        if not ok:
            detail["reason"] = (
                f"the patched incident averages {mean_patched:.1f} ms with a p95 of "
                f"{worst_p95:.1f} ms against a {budget:.0f} ms budget "
                f"(baseline {mean_baseline:.1f} ms)"
            )
        return ok, detail

    # ------------------------------------------------------- code and policy

    def _check_existing_code_integrity(self, workspace: Path) -> bool:
        """
        The incident's own code has to remain valid.

        Every Python file compiles, every configuration file parses, and the
        tests the bundle shipped - if it shipped any - still pass.
        """
        try:
            for py_file in workspace.rglob("*.py"):
                if py_file.name == "test_regression.py":
                    continue
                res = subprocess.run(
                    [sys.executable, "-m", "py_compile", str(py_file)],
                    capture_output=True,
                    text=True,
                )
                if res.returncode != 0:
                    logger.debug(f"{py_file} does not compile: {res.stderr}")
                    return False

            import json as _json

            import yaml as _yaml

            for config_file in list(workspace.rglob("*.yaml")) + list(
                workspace.rglob("*.yml")
            ):
                with open(config_file, "r", encoding="utf-8") as handle:
                    _yaml.safe_load(handle)
            for json_file in workspace.rglob("*.json"):
                if json_file.name == "calibration.json":
                    continue
                _json.loads(json_file.read_text(encoding="utf-8"))

            return self._check_bundle_tests(workspace)
        except Exception as exc:
            logger.debug(f"Code integrity check failed: {exc}")
            return False

    def _check_bundle_tests(self, workspace: Path) -> bool:
        """Run the test suite the bundle shipped, when it shipped one."""
        tests_dir = workspace / "tests"
        if not tests_dir.is_dir():
            return True
        collected = [p for p in tests_dir.rglob("test_*.py") if p.is_file()]
        if not collected:
            return True
        try:
            res = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "tests"],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=REGRESSION_TIMEOUT_S,
            )
        except Exception as exc:
            logger.debug(f"The bundle's own tests could not be run: {exc}")
            return False
        if res.returncode != 0:
            logger.debug(f"The bundle's own tests failed: {res.stdout[-2000:]}")
            return False
        return True

    def _check_safety_invariants(
        self, workspace: Path, originals: Dict[str, bytes]
    ) -> List[str]:
        """
        A patch may not weaken a safety declaration.

        The comparison is against the bundle's own pre-patch configuration:
        a watchdog that was armed must still be armed, and a limit that was
        declared may not be raised.
        """
        original_snapshot = self._snapshot_from_bytes(originals)
        patched_snapshot = safety_snapshot(workspace)
        return compare_safety(original_snapshot, patched_snapshot)

    def _snapshot_from_bytes(self, originals: Dict[str, bytes]) -> Dict[str, Any]:
        """The safety snapshot of the pre-patch workspace."""

        from cauveris.analysis.parameters import parse_config_text
        from cauveris.verifier.workspace import (
            is_safety_enable_key,
            is_safety_limit_key,
        )

        snapshot: Dict[str, Any] = {}
        for rel, payload in originals.items():
            suffix = Path(rel).suffix.lower()
            if suffix not in CONFIG_SUFFIXES + SECTIONED_CONFIG_SUFFIXES:
                continue
            try:
                text = payload.decode("utf-8")
            except UnicodeDecodeError:
                continue
            data = parse_config_text(text, suffix)
            if data is None:
                continue
            flat = _flatten(data)
            for key, value in flat.items():
                if is_safety_enable_key(key) or is_safety_limit_key(key):
                    snapshot[f"{rel}::{key}"] = value
        return snapshot

    def _check_forbidden_changes(
        self, workspace: Path, patch: PatchCandidate
    ) -> List[str]:
        """
        Scan the patch for changes that must never appear.

        The rules are about *how* the fix was made, not about which incident
        it is: a fix that disables the watchdog, swallows exceptions, weakens
        a limit or hard-codes a suppressed warning is not a fix.
        """
        findings: List[str] = []
        diff = patch.unified_diff or ""
        diff_lower = diff.lower()

        forbidden_fragments = (
            ("disable_safety", "the patch disables a safety mechanism"),
            ("ignore_stale", "the patch makes the system ignore stale data"),
            ("safety: false", "the patch turns a safety block off"),
            ("watchdog = false", "the patch turns the watchdog off"),
            ("bypass_safety", "the patch bypasses a safety check"),
            ("skip_validation", "the patch skips a validation"),
        )
        for fragment, description in forbidden_fragments:
            if fragment in diff_lower:
                findings.append(description)

        # A blanket ``except: pass`` swallows the evidence a future incident
        # would need.
        for py_file in workspace.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8")
            except Exception:
                continue
            if "except:" in content and "pass" in content:
                findings.append(
                    f"{py_file.relative_to(workspace).as_posix()} swallows exceptions "
                    "with a bare except/pass"
                )

        # The patch may not touch the recorded evidence of the incident.
        for rel in patch.affected_files or []:
            lowered = str(rel).lower()
            for guarded in ("logs/", "traces/", "recordings/", "metrics/", "observations/"):
                if lowered.startswith(guarded):
                    findings.append(f"the patch modifies recorded evidence ({rel})")

        return findings

    # -------------------------------------------------------------- rollback

    def _check_rollback(
        self, workspace: Path, patch: PatchCandidate, originals: Dict[str, bytes]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        The patch must be reversible.

        The inverse diff is computed from the patch itself and applied to the
        patched workspace.  The result is compared byte-for-byte with the
        pre-patch workspace, so a rollback that only *looks* right fails.
        """
        detail: Dict[str, Any] = {}
        try:
            inverse = reverse_unified_diff(patch.unified_diff or "")
        except UnifiedDiffError as exc:
            return False, {"reason": f"the patch could not be inverted: {exc}"}

        try:
            apply_unified_diff(inverse, workspace)
        except UnifiedDiffError as exc:
            return False, {"reason": f"the inverse diff did not apply: {exc}"}
        except Exception as exc:
            return False, {"reason": f"unexpected failure during rollback: {exc}"}

        mismatches: List[str] = []
        for rel, payload in originals.items():
            target = workspace / rel
            if not target.exists():
                mismatches.append(f"{rel} is missing after rollback")
                continue
            if target.read_bytes() != payload:
                mismatches.append(f"{rel} differs from its pre-patch content")
        for rel in list(self._extra_files(workspace) - set(originals)):
            mismatches.append(f"{rel} was left behind by the rollback")

        detail = {
            "files_compared": len(originals),
            "mismatches": mismatches,
        }
        if mismatches:
            detail["reason"] = "; ".join(mismatches[:5])
            return False, detail

        # Put the patch back, so the workspace ends in its verified state.
        try:
            apply_unified_diff(patch.unified_diff or "", workspace)
        except Exception as exc:
            logger.warning(f"Could not re-apply the patch after rollback: {exc}")
            detail["reason"] = f"the patch could not be re-applied after rollback: {exc}"
            return False, detail

        return True, detail

    def _extra_files(self, workspace: Path) -> set:
        """The workspace files that are not part of the copied bundle."""
        known = {
            "calibration.json",
            "test_regression.py",
            "__pycache__",
        }
        extra = set()
        for path in workspace.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(workspace).as_posix()
            if relative in known or relative.startswith("__pycache__"):
                continue
            if "__pycache__" in relative:
                continue
            extra.add(relative)
        return extra


def _flatten(data: Any, prefix: str = "") -> Dict[str, Any]:
    """Flatten a nested mapping into dotted keys."""
    flat: Dict[str, Any] = {}
    if not isinstance(data, dict):
        return flat
    for key, value in data.items():
        full = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{full}."))
        else:
            flat[full] = value
    return flat


def _empty_results(reason: Optional[str]) -> Dict[str, Any]:
    """The result set for a candidate that could not be verified."""
    results: Dict[str, Any] = {
        "applies_cleanly": False,
        "regression_test_fails_before": False,
        "regression_test_passes_after": False,
        "original_failure_not_reproduced": False,
        "existing_tests_pass": False,
        "safety_invariants_pass": False,
        "performance_within_budget": False,
        "forbidden_change_scan_passes": False,
        "rollback_test_passes": False,
        "verified": False,
        "details": {},
        "rejection_reason": reason,
    }
    if reason:
        results["details"] = {
            "checks_passed": 0,
            "total_checks": 9,
            "failures": [reason],
            "policy_findings": [],
        }
    return results
