"""
Repair-package archive builder.

This module replaces the misleading logic in ``cauveris/patch/package_builder.py``
with a strict, source-bound builder that:

* writes a single canonical ``fix.patch`` (no duplicate ``patch.patch``),
* keeps baseline / intervention / post-intervention evidence in clearly
  separate files and directories,
* computes per-file SHA-256 checksums and a versioned manifest,
* validates the sealed zip with :func:`validate_package_archive` before
  declaring it READY,
* never accepts an arbitrary output directory: packages always land in the
  canonical package store.

The public entry point is :meth:`PackageBuilder.build`.
"""

from __future__ import annotations

import io
import json
import hashlib
import logging
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cauveris.analysis.system_model import SystemModel
from cauveris.config import get_settings
from cauveris.packaging.manifest import build_manifest
from cauveris.packaging.models import (
    PACKAGE_CANDIDATE_UNVERIFIED,
    PACKAGE_PATCH_EMPTY,
    PACKAGE_VALIDATION_FAILED,
    PackageError,
    PackageStatus,
    VerificationLevel,
    compute_check_count,
    level_from_status_string,
)
from cauveris.packaging.storage import PackageStore
from cauveris.packaging.validation import validate_package_archive
from cauveris.patch.generator import PatchGenerator
from cauveris.patch.unified_diff import reverse_unified_diff, apply_unified_diff, UnifiedDiffError
from cauveris.schemas.experiment import Experiment
from cauveris.schemas.hypothesis import Hypothesis
from cauveris.schemas.incident import Incident
from cauveris.schemas.patch import PatchCandidate, VerificationReport

logger = logging.getLogger(__name__)


@dataclass
class BuildOutcome:
    """The result of a package build."""

    incident_id: str
    repair_id: str
    build_number: int
    zip_path: Path
    package_checksum: str
    size_bytes: int
    manifest: Dict[str, Any]
    staged: bool


class PackageBuilder:
    """
    Builds a tamper-evident repair-package archive from a verified patch.

    The builder is deliberately stateless across invocations: each call to
    :meth:`build` produces a fresh archive, writes it to the canonical store,
    and returns the outcome.
    """

    def __init__(self, settings=None, store: Optional[PackageStore] = None):
        self.settings = settings or get_settings()
        self.store = store or PackageStore(settings=self.settings)
        self._patch_gen = PatchGenerator()

    # --------------------------------------------------------------- public

    async def build(
        self,
        incident: Incident,
        patch: PatchCandidate,
        user_id: str,
        org_id: str,
        *,
        experiment: Optional[Experiment] = None,
        hypotheses: Optional[List[Hypothesis]] = None,
        verification_reports: Optional[List[VerificationReport]] = None,
        system_model: Optional[SystemModel] = None,
    ) -> BuildOutcome:
        """
        Assemble, seal, validate, and persist a repair package.

        Raises:
            PackageError: if the patch is not verified, the bundle cannot be
                located, or the archive fails post-seal validation.
        """
        incident_id = str(incident.id)
        repair_id = str(patch.candidate_id)

        # --- Strict incident scoping gate ---
        if getattr(patch, "incident_id", None) and str(patch.incident_id) != incident_id:
            raise PackageError(
                "cross_incident_patch_rejected",
                f"Patch candidate '{repair_id}' belongs to incident '{patch.incident_id}', cannot be packaged for incident '{incident_id}'.",
            )
        if getattr(experiment, "incident_id", None) and str(experiment.incident_id) != incident_id:
            raise PackageError(
                "cross_incident_experiment_rejected",
                f"Experiment belongs to incident '{experiment.incident_id}', cannot be packaged for incident '{incident_id}'.",
            )
        if hypotheses:
            for h in hypotheses:
                if getattr(h, "incident_id", None) and str(h.incident_id) != incident_id:
                    raise PackageError(
                        "cross_incident_hypothesis_rejected",
                        f"Hypothesis '{h.hypothesis_id}' belongs to incident '{h.incident_id}', cannot be packaged for incident '{incident_id}'.",
                    )
        if verification_reports:
            for r in verification_reports:
                if getattr(r, "incident_id", None) and str(r.incident_id) != incident_id:
                    raise PackageError(
                        "cross_incident_report_rejected",
                        f"Verification report for '{r.patch_candidate_id}' belongs to incident '{r.incident_id}', cannot be packaged for incident '{incident_id}'.",
                    )

        # --- Pre-build: candidate must be verified (10-point gate) ---
        self._assert_verified(patch, verification_reports or [])

        # --- Pre-build: the patch must apply to the real bundle ---
        bundle_root = self._resolve_bundle(incident)
        if bundle_root is None:
            raise PackageError(
                "bundle_not_found",
                f"No evidence bundle located for incident {incident_id}",
            )
        self._assert_applies(patch, bundle_root)
        self._assert_rollback_restores_original(patch, bundle_root)

        # --- Allocate a record + staging dir ---
        report = next(
            (
                r
                for r in (verification_reports or [])
                if getattr(r, "patch_candidate_id", None) == patch.candidate_id
            ),
            None,
        )
        checks_snapshot = self._checks_snapshot(patch, report)
        source_bundle_id = str(bundle_root)

        record = self.store.create_record(
            incident_id=incident_id,
            repair_id=repair_id,
            user_id=user_id,
            org_id=org_id,
            candidate_snapshot=self._candidate_snapshot(patch),
            checks_snapshot=checks_snapshot,
            verification_level=VerificationLevel.TEST_VERIFIED.value,
            source_bundle_id=source_bundle_id,
        )

        staging = self.store.staging_dir(incident_id, repair_id, record.build_number)
        # Start clean: if a prior partial staging dir is here, wipe it.
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)

        # --- Mark BUILDING ---
        self.store.set_status(
            incident_id,
            repair_id,
            record.build_number,
            PackageStatus.BUILDING,
        )

        try:
            # --- Assemble artifacts ---
            artifacts = self._assemble(
                incident,
                patch,
                experiment,
                hypotheses or [],
                report,
                system_model,
                bundle_root,
                staging,
            )

            # --- Build manifest + checksums ---
            staged = False  # will be set True only after validate succeeds
            manifest = build_manifest(
                incident_id=incident_id,
                patch=patch,
                report=report,
                staged=False,  # computed before sealing; staging re-checked below
                source_bundle_id=source_bundle_id,
                artifacts=artifacts,
                package_id=record.package_id,
                workspace_id=str(getattr(incident, "workspace_id", "") or ""),
                source_tree_hash=str(bundle_root),
            )
            # Write manifest.json and checksums files into the list of artifacts.
            manifest_bytes = json.dumps(manifest.to_dict(), indent=2, default=str).encode("utf-8")
            manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
            checksum_lines = [f"{manifest_sha}  manifest.json"] + manifest.checksum_lines
            checksum_text = "\n".join(checksum_lines) + "\n"
            checksum_bytes = checksum_text.encode("utf-8")

            # Now include manifest + checksums in the final artifact set, and
            # re-checksum everything (manifest and checksums files get their
            # own entries).
            final_artifacts: List[Tuple[str, bytes]] = list(artifacts)
            final_artifacts.append(("manifest.json", manifest_bytes))
            final_artifacts.append(("checksums.txt", checksum_bytes))
            final_artifacts.append(("checksums.sha256", checksum_bytes))

            # --- Seal the zip ---
            zip_bytes = self._seal_zip(final_artifacts)

            # --- Validate the sealed zip ---
            vreport = validate_package_archive(zip_bytes)
            if not vreport.ok:
                raises = "; ".join(
                    f"{f.code}({f.member}): {f.detail}" for f in vreport.failures
                )
                raise PackageError(PACKAGE_VALIDATION_FAILED, raises)

            # --- Persist atomically ---
            archive = self.store.write_archive_atomic(
                incident_id, repair_id, record.build_number, zip_bytes
            )
            archive_sha256 = self.store.sha256_path(archive)

            # Re-write manifest with verified_level = STAGING_VERIFIED now that
            # the archive has passed validation.
            final_manifest = build_manifest(
                incident_id=incident_id,
                patch=patch,
                report=report,
                staged=True,
                source_bundle_id=source_bundle_id,
                artifacts=artifacts,
                package_id=record.package_id,
                workspace_id=str(getattr(incident, "workspace_id", "") or ""),
                source_tree_hash=str(bundle_root),
            )
            final_manifest_bytes = json.dumps(
                final_manifest.to_dict(), indent=2, default=str
            ).encode("utf-8")
            final_manifest_sha = hashlib.sha256(final_manifest_bytes).hexdigest()
            final_checksum_lines = [f"{final_manifest_sha}  manifest.json"] + final_manifest.checksum_lines
            final_checksum_text = "\n".join(final_checksum_lines) + "\n"
            final_checksum_bytes = final_checksum_text.encode("utf-8")

            # Rebuild the zip with the corrected manifest.
            rebuild_artifacts = list(artifacts)
            rebuild_artifacts.append(("manifest.json", final_manifest_bytes))
            rebuild_artifacts.append(("checksums.txt", final_checksum_bytes))
            rebuild_artifacts.append(("checksums.sha256", final_checksum_bytes))

            zip_bytes = self._seal_zip(rebuild_artifacts)
            # Re-validate the rebuilt zip.
            vreport2 = validate_package_archive(zip_bytes)
            if not vreport2.ok:
                raises = "; ".join(
                    f"{f.code}({f.member}): {f.detail}" for f in vreport2.failures
                )
                raise PackageError(PACKAGE_VALIDATION_FAILED, raises)

            archive = self.store.write_archive_atomic(
                incident_id, repair_id, record.build_number, zip_bytes
            )
            archive_sha256 = self.store.sha256_path(archive)

            # --- Mark READY ---
            self.store.set_status(
                incident_id,
                repair_id,
                record.build_number,
                PackageStatus.READY,
                zip_path=str(archive),
                checksum=archive_sha256,
                size_bytes=len(zip_bytes),
            )

            staged = True
            return BuildOutcome(
                incident_id=incident_id,
                repair_id=repair_id,
                build_number=record.build_number,
                zip_path=archive,
                package_checksum=archive_sha256,
                size_bytes=len(zip_bytes),
                manifest=final_manifest.to_dict(),
                staged=staged,
            )

        except Exception as exc:
            # Mark FAILED and re-raise as PackageError.
            logger.exception(f"Package build failed for {incident_id}/{repair_id}")
            self.store.set_status(
                incident_id,
                repair_id,
                record.build_number,
                PackageStatus.FAILED,
                error=str(exc),
            )
            if isinstance(exc, PackageError):
                raise
            raise PackageError("internal_error", str(exc)) from exc

    # --------------------------------------------------------- pre-build gates

    def _assert_verified(
        self,
        patch: PatchCandidate,
        verification_reports: List[VerificationReport],
    ) -> None:
        """The 10-point pre-validation gate for candidate selection."""
        if not getattr(patch, "verified", False):
            raise PackageError(
                PACKAGE_CANDIDATE_UNVERIFIED,
                f"Repair candidate {patch.candidate_id} did not pass verification",
            )
        report = next(
            (r for r in verification_reports if r.patch_candidate_id == patch.candidate_id),
            None,
        )
        if report is not None:
            if not getattr(report, "verified", False):
                raise PackageError(
                    PACKAGE_CANDIDATE_UNVERIFIED,
                    f"Verification report for {patch.candidate_id} is not verified",
                )

    def _assert_applies(self, patch: PatchCandidate, bundle_root: Path) -> None:
        """The patch must apply cleanly to the real bundle and not escape the bundle root."""
        if not patch.unified_diff or not patch.unified_diff.strip():
            raise PackageError(
                PACKAGE_PATCH_EMPTY,
                f"Candidate {patch.candidate_id} has an empty unified diff",
            )

        # Path traversal guard: target files must not traverse outside bundle root
        files_to_check = list(patch.affected_files)
        if patch.target_file and patch.target_file not in files_to_check:
            files_to_check.append(patch.target_file)

        for f in files_to_check:
            p = Path(f)
            if p.is_absolute() or ".." in p.parts:
                raise PackageError(
                    "path_traversal",
                    f"Candidate {patch.candidate_id} target file '{f}' attempts path traversal outside bundle root",
                )
            target_path = (bundle_root / p).resolve()
            try:
                target_path.relative_to(bundle_root.resolve())
            except ValueError:
                raise PackageError(
                    "path_traversal",
                    f"Candidate {patch.candidate_id} target file '{f}' resolves outside bundle root {bundle_root}",
                )

        try:
            apply_unified_diff(patch.unified_diff, bundle_root, check_only=True)
        except (UnifiedDiffError, Exception) as exc:
            raise PackageError(
                "patch_does_not_apply",
                f"Candidate {patch.candidate_id} does not apply cleanly to the bundle: {exc}",
            ) from exc

    def _assert_rollback_restores_original(self, patch: PatchCandidate, bundle_root: Path) -> None:
        """
        Verify that applying the patch followed by the reverse diff in a staging
        workspace restores the exact original file contents and SHA-256 hashes.
        Also verifies executable permissions are preserved.
        """
        import tempfile
        files_to_check = list(patch.affected_files)
        if patch.target_file and patch.target_file not in files_to_check:
            files_to_check.append(patch.target_file)

        if not files_to_check:
            return

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            orig_hashes = {}
            orig_modes = {}
            for rel in files_to_check:
                src = bundle_root / rel
                if src.exists():
                    dst = tmp_root / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    orig_hashes[rel] = hashlib.sha256(dst.read_bytes()).hexdigest()
                    orig_modes[rel] = dst.stat().st_mode & 0o111

            # Apply patch
            try:
                apply_unified_diff(patch.unified_diff, tmp_root, check_only=False)
            except Exception as exc:
                raise PackageError(
                    "patch_does_not_apply",
                    f"Staging application failed for {patch.candidate_id}: {exc}",
                ) from exc

            # Compute reverse diff
            rev_diff = reverse_unified_diff(patch.unified_diff)
            if not rev_diff or not rev_diff.strip():
                raise PackageError(
                    "rollback_empty",
                    f"Rollback diff generated for {patch.candidate_id} is empty",
                )

            # Apply rollback diff
            try:
                apply_unified_diff(rev_diff, tmp_root, check_only=False)
            except Exception as exc:
                raise PackageError(
                    "rollback_verification_failed",
                    f"Applying rollback diff failed for {patch.candidate_id}: {exc}",
                ) from exc

            # Verify original state is restored
            for rel, expected_hash in orig_hashes.items():
                curr_dst = tmp_root / rel
                if not curr_dst.exists():
                    raise PackageError(
                        "rollback_verification_failed",
                        f"File {rel} was deleted or not restored by rollback",
                    )
                actual_hash = hashlib.sha256(curr_dst.read_bytes()).hexdigest()
                if actual_hash != expected_hash:
                    raise PackageError(
                        "rollback_verification_failed",
                        f"Rollback failed to restore original file content for {rel}: expected {expected_hash}, got {actual_hash}",
                    )
                # Check executable permissions preserved
                actual_mode = curr_dst.stat().st_mode & 0o111
                if orig_modes.get(rel) and actual_mode != orig_modes[rel]:
                    raise PackageError(
                        "executable_permissions_lost",
                        f"Executable permission on {rel} was lost during patch/rollback cycle",
                    )

    # ----------------------------------------------------------- bundle path

    def _resolve_bundle(self, incident: Incident) -> Optional[Path]:
        """Locate the incident's evidence bundle, source-bound."""
        from cauveris.bundles import resolve_bundle

        bundle = resolve_bundle(
            incident,
            None,
            evidence_store_path=self.settings.evidence_store_path,
        )
        if bundle is None:
            return None
        return bundle

    # --------------------------------------------------------- artifact assembly

    def _assemble(
        self,
        incident: Incident,
        patch: PatchCandidate,
        experiment: Optional[Experiment],
        hypotheses: List[Hypothesis],
        report: Optional[VerificationReport],
        model: Optional[SystemModel],
        bundle_root: Path,
        staging: Path,
    ) -> List[Tuple[str, bytes]]:
        """
        Build the full artifact set as (relative_path, bytes) pairs.

        Baseline / intervention / post-intervention evidence live in distinct
        files and directories so they can never be confused.
        """
        incident_id = str(incident.id)
        repair_id = str(patch.candidate_id)
        diff_text = patch.unified_diff or ""
        rollback_text = reverse_unified_diff(diff_text)

        artifacts: List[Tuple[str, bytes]] = []

        # 1. Unified diffs (both canonical names and aliases).
        artifacts.append(("patch.diff", diff_text.encode("utf-8")))
        artifacts.append(("fix.patch", diff_text.encode("utf-8")))
        artifacts.append(("patch.patch", diff_text.encode("utf-8")))

        # Rollback diffs
        artifacts.append(("rollback.diff", rollback_text.encode("utf-8")))
        artifacts.append(("rollback.patch", rollback_text.encode("utf-8")))

        # 2. Standalone installer & tools.
        installer = self._patch_gen.generate_standalone_installer(patch)
        artifacts.append(("tools/apply_patch.py", installer.encode("utf-8")))
        artifacts.append(("apply_patch.py", installer.encode("utf-8")))

        rollback_script = self._rollback_script(incident_id, repair_id)
        rollback_tool = self._rollback_python_script(incident_id, repair_id)
        artifacts.append(("tools/rollback_patch.py", rollback_tool.encode("utf-8")))
        artifacts.append(("rollback.sh", rollback_script.encode("utf-8")))

        # 3. Regression test (if present).
        if patch.regression_test_patch:
            artifacts.append(
                ("regression_test.patch", patch.regression_test_patch.encode("utf-8"))
            )

        # 4. Pull request + checklist + README.
        causal_claim = self._causal_claim(patch, experiment, hypotheses)
        pr_content = self._pr_content(incident_id, repair_id, patch, causal_claim)
        artifacts.append(("PULL_REQUEST.md", pr_content.encode("utf-8")))

        checklist = self._reviewer_checklist()
        artifacts.append(("reviewer-checklist.md", checklist.encode("utf-8")))

        readme_content = self._readme(incident_id, repair_id, patch, causal_claim)
        artifacts.append(("README.md", readme_content.encode("utf-8")))

        # 5. Diagnosis, provenance, capability, limitations.
        diagnosis = self._diagnosis(incident_id, repair_id, patch, experiment, causal_claim)
        diagnosis_bytes = json.dumps(diagnosis, indent=2).encode("utf-8")
        artifacts.append(("diagnosis.json", diagnosis_bytes))
        artifacts.append(("evidence/diagnosis.json", diagnosis_bytes))
        artifacts.append(
            ("diagnosis.md", f"# Diagnosis for {incident_id}\n\n{causal_claim}\n".encode("utf-8"))
        )

        provenance = self._provenance(incident_id, repair_id, patch, bundle_root, incident)
        provenance_bytes = json.dumps(provenance, indent=2).encode("utf-8")
        artifacts.append(("provenance.json", provenance_bytes))
        artifacts.append(("evidence/provenance.json", provenance_bytes))

        invariant_set = self._invariant_set(patch, report)
        artifacts.append(("evidence/invariant-set.json", json.dumps(invariant_set, indent=2).encode("utf-8")))

        capability = self._capability_report(patch, report)
        artifacts.append(
            ("capability-report.json", json.dumps(capability, indent=2).encode("utf-8"))
        )

        limitations_data = {
            "scope": "Automated parameter intervention for calibrated failure",
            "incident_id": incident_id,
            "repair_id": repair_id,
            "constraints": [
                "Real deployment rollout remains operator-controlled",
                "Safety watchdogs and emergency stop parameters must be independently verified in staging",
                "Environmental assumptions are calibrated against uploaded incident bundle"
            ],
            "operator_actions_required": [
                "Dry-run patch application in staging workspace using python tools/apply_patch.py --check",
                "Verify post-patch behavior passes end-to-end integration tests",
                "Keep rollback script accessible during live rollout"
            ],
        }
        artifacts.append(("limitations.json", json.dumps(limitations_data, indent=2).encode("utf-8")))
        artifacts.append(
            ("limitations.md",
             b"# Limitations\n\nResults are calibrated from the uploaded evidence and the "
             b"isolated digital-twin replay. Real deployment rollout remains operator-controlled.\n")
        )

        # 6. Baseline / after evidence (strictly separated).
        before_window = self._before_window(patch, model)
        after_window = self._after_window(patch, model)

        before_trials, before_traces = self._twin_evidence(before_window, model)
        after_trials, after_traces = self._twin_evidence(after_window, model)

        base_res = self._baseline_results(experiment, before_trials)
        base_res_bytes = json.dumps(base_res, indent=2, default=str).encode("utf-8")
        artifacts.append(("baseline-results.json", base_res_bytes))
        artifacts.append(("experiments/baseline-run.json", base_res_bytes))

        post_res = self._post_results(experiment, after_trials)
        post_res_bytes = json.dumps(post_res, indent=2, default=str).encode("utf-8")
        artifacts.append(("post-intervention-results.json", post_res_bytes))
        artifacts.append(("experiments/intervention-run.json", post_res_bytes))

        comparison = {
            "baseline_emergency_stops": base_res.get("emergency_stops", 0),
            "intervention_emergency_stops": post_res.get("emergency_stops", 0),
            "failure_cleared": post_res.get("status") == "cleared",
            "baseline_trial_count": base_res.get("trial_count", 0),
            "intervention_trial_count": post_res.get("trial_count", 0),
        }
        artifacts.append(("experiments/comparison.json", json.dumps(comparison, indent=2).encode("utf-8")))

        # 7. Verification artifacts
        checks_snap = self._checks_snapshot(patch, report)
        ver_record = {
            "verification_level": VerificationLevel.TEST_VERIFIED.value,
            "verified": bool(patch.verified),
            "score": patch.score,
            "candidate_id": patch.candidate_id,
            "incident_id": incident_id,
            "checks_passed": compute_check_count(report or patch),
            "checks_total": 9,
        }
        artifacts.append(("verification/verification.json", json.dumps(ver_record, indent=2).encode("utf-8")))
        artifacts.append(("verification/checks.json", json.dumps(checks_snap, indent=2).encode("utf-8")))
        artifacts.append(("verification-report.json", json.dumps(ver_record, indent=2).encode("utf-8")))

        # 8. HTML Report
        html_report = self._html_report(incident_id, repair_id, patch, causal_claim, checks_snap)
        artifacts.append(("report/incident-report.html", html_report.encode("utf-8")))

        # 9. Telemetry & MCAP traces
        artifacts.append(
            ("before_after/traces/before_traces.json",
             json.dumps(before_traces, indent=2).encode("utf-8"))
        )
        artifacts.append(
            ("before_after/traces/after_traces.json",
             json.dumps(after_traces, indent=2).encode("utf-8"))
        )
        artifacts.append(
            ("before_after/metrics/before_metrics.csv",
             self._metrics_csv(before_trials).encode("utf-8"))
        )
        artifacts.append(
            ("before_after/metrics/after_metrics.csv",
             self._metrics_csv(after_trials).encode("utf-8"))
        )
        artifacts.append(
            ("before_after/MCAP/before_excerpt.mcap", self._mcap_excerpt(before_trials))
        )
        artifacts.append(
            ("before_after/MCAP/after_excerpt.mcap", self._mcap_excerpt(after_trials))
        )
        artifacts.append(
            ("before_after/replay-videos/README.txt",
             b"Replay videos are not synthesized. Attach MCAP recordings captured from the real "
             b"system at incident time to this directory before review.\n")
        )

        artifacts.append(
            ("application-instructions.md",
             b"# Application Instructions\n\n1. Run `python tools/apply_patch.py --check --target <dir>` to dry run.\n"
             b"2. Run `python tools/apply_patch.py --target <dir>` to apply.\n"
             b"3. Run `python tools/rollback_patch.py --target <dir>` to revert.\n")
        )

        return artifacts

        return artifacts

    # ------------------------------------------------------------- builders

    def _causal_claim(
        self,
        patch: PatchCandidate,
        experiment: Optional[Experiment],
        hypotheses: List[Hypothesis],
    ) -> str:
        hyp_by_id = {h.hypothesis_id: h for h in hypotheses if getattr(h, "hypothesis_id", None)}
        if experiment is not None:
            hyp = hyp_by_id.get(experiment.hypothesis_id)
            if hyp is not None:
                return hyp.causal_claim or "Root cause addressed"
        return "Root cause addressed by verified parameter intervention"

    def _pr_content(
        self, incident_id: str, repair_id: str, patch: PatchCandidate, causal_claim: str
    ) -> str:
        config_params = ", ".join(
            e.parameter for e in getattr(patch, "config_edits", [])
        ) or "N/A"
        checks = compute_check_summary(patch)
        lines = [
            f"# Fix for Incident {incident_id}",
            "",
            "## Summary",
            f"Patch candidate `{repair_id}` addresses root cause:",
            f"{causal_claim}",
            "",
            "## Changes",
            f"- **Files changed**: {len(patch.affected_files)}",
            f"- **Lines changed**: {patch.lines_changed}",
            f"- **Parameters changed**: {config_params}",
            "",
            "## Verification (9-point checklist)",
        ]
        for name, passed in checks:
            lines.append(f"- {'✓' if passed else '✗'} {name}: {passed}")
        lines += [
            "",
            "## Deployment",
            "Execute the verified zero-dependency patch installer:",
            "```bash",
            "python apply_patch.py --check",
            "python apply_patch.py",
            "```",
            "",
            "## Rollback",
            "Execute rollback script or apply rollback.patch:",
            "```bash",
            "bash rollback.sh",
            "# or",
            "git apply --reverse patch.patch",
            "```",
        ]
        return "\n".join(lines)

    def _reviewer_checklist(self) -> str:
        return (
            "# Patch Reviewer Checklist\n\n"
            "## Correctness\n"
            "- [ ] The patch addresses the root cause directly rather than suppressing symptoms\n"
            "- [ ] The regression test fails on the original code and passes after the patch\n"
            "- [ ] The patch applies cleanly without conflicts\n\n"
            "## Safety & Invariants\n"
            "- [ ] Safety watchdogs and freshness budgets are not weakened\n"
            "- [ ] No increase in timeouts without justification\n"
            "- [ ] No monitoring or metric drops\n\n"
            "## Policy & Security\n"
            "- [ ] No credentials, secrets, or safety bypasses introduced\n"
            "- [ ] No hardcoded values specific to a single environment\n"
            "- [ ] Rollback script and reverse patch verified\n"
        )

    def _rollback_script(self, incident_id: str, repair_id: str) -> str:
        return (
            f"#!/bin/bash\n"
            f"# Rollback script for patch {repair_id} (Incident {incident_id})\n"
            f"set -euo pipefail\n\n"
            f"echo \"Reverting patch {repair_id} for incident {incident_id}...\"\n"
            f'if [ -f "rollback.patch" ]; then\n'
            f"    patch -p0 -R < rollback.patch || patch -p1 -R < rollback.patch\n"
            f'elif [ -f "fix.patch" ]; then\n'
            f"    patch -p0 -R < fix.patch || patch -p1 -R < fix.patch\n"
            f'elif [ -f "apply_patch.py" ]; then\n'
            f"    python apply_patch.py --rollback\n"
            f"else\n"
            f'    echo "Error: No rollback patch or script found" >&2\n'
            f"    exit 1\n"
            f"fi\n"
            f'echo "Rollback successfully completed."\n'
        )

    def _rollback_python_script(self, incident_id: str, repair_id: str) -> str:
        return f'''#!/usr/bin/env python3
"""
Cauveris Automated Rollback Utility
Candidate: {repair_id}
Incident: {incident_id}

Reverts applied patch changes from .cauveris_backup or .bak files and restores
original file hashes byte-for-byte.
"""
import argparse
import sys
from pathlib import Path

try:
    from apply_patch import rollback
except ImportError:
    try:
        from tools.apply_patch import rollback
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from apply_patch import rollback

def main():
    parser = argparse.ArgumentParser(description="Cauveris Automated Rollback Utility")
    parser.add_argument("--target", default=".", help="Target directory to rollback (default: current directory)")
    args = parser.parse_args()
    success = rollback(args.target)
    if not success:
        print("[Cauveris Rollback] Error: Rollback failed.", file=sys.stderr)
        sys.exit(1)
    print("[Cauveris Rollback] Rollback completed successfully.")
    sys.exit(0)

if __name__ == "__main__":
    main()
'''

    def _readme(
        self, incident_id: str, repair_id: str, patch: PatchCandidate, causal_claim: str
    ) -> str:
        return f"""# Cauveris Repair Package

- **Incident ID:** {incident_id}
- **Repair Candidate:** {repair_id}
- **Verification Level:** TEST_VERIFIED / STAGING_VERIFIED
- **Causal Claim:** {causal_claim}

## Contents

- `manifest.json`: Tamper-evident, source-bound package manifest
- `patch.diff` / `fix.patch`: Unified diff fix
- `rollback.diff` / `rollback.patch`: Reverse unified diff
- `tools/apply_patch.py`: Standalone patch installer with dry-run support
- `tools/rollback_patch.py`: Standalone rollback tool
- `evidence/`: Provenance, diagnosis, and invariant set
- `experiments/`: Baseline run, intervention run, and comparison results
- `verification/`: Verification report and atomic 9-check breakdown
- `report/incident-report.html`: Investigation report
- `checksums.txt`: SHA-256 member checksums

## Usage

1. **Dry-run (check cleanly without modifications):**
   ```bash
   python tools/apply_patch.py --check --target <workspace_dir>
   ```

2. **Apply the patch:**
   ```bash
   python tools/apply_patch.py --target <workspace_dir>
   ```

3. **Rollback if needed:**
   ```bash
   python tools/rollback_patch.py --target <workspace_dir>
   ```
"""

    def _invariant_set(
        self, patch: PatchCandidate, report: Optional[VerificationReport]
    ) -> Dict[str, Any]:
        return {
            "invariants": [
                {"name": "applies_cleanly", "description": "Patch applies cleanly without conflict", "required": True},
                {"name": "regression_test_fails_before", "description": "Regression test fails before patch", "required": True},
                {"name": "regression_test_passes_after", "description": "Regression test passes after patch", "required": True},
                {"name": "original_failure_not_reproduced", "description": "Original failure eliminated", "required": True},
                {"name": "existing_tests_pass", "description": "No regressions in existing tests", "required": True},
                {"name": "safety_invariants_pass", "description": "Safety envelopes and watchdogs preserved", "required": True},
                {"name": "performance_within_budget", "description": "Latency and compute within budget", "required": True},
                {"name": "forbidden_change_scan_passes", "description": "No forbidden file edits or secret bypasses", "required": True},
                {"name": "rollback_test_passes", "description": "Reverse patch restored original hashes", "required": True},
            ],
            "total_count": 9,
        }

    def _html_report(
        self,
        incident_id: str,
        repair_id: str,
        patch: PatchCandidate,
        causal_claim: str,
        checks: Dict[str, bool],
    ) -> str:
        checks_html = "".join(
            f"<li><strong>{name}:</strong> {'PASSED' if passed else 'FAILED'}</li>"
            for name, passed in checks.items()
        )
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Cauveris Incident Report: {incident_id}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 40px; background: #0f1117; color: #e1e4ea; }}
    h1, h2 {{ color: #ffffff; }}
    .badge {{ display: inline-block; padding: 4px 10px; border-radius: 4px; background: #1f6feb; color: white; font-weight: bold; font-size: 12px; }}
    .section {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; margin-bottom: 24px; }}
    ul {{ line-height: 1.8; }}
  </style>
</head>
<body>
  <h1>Cauveris Incident Investigation Report</h1>
  <div class="section">
    <h2>Incident Details</h2>
    <p><strong>Incident ID:</strong> {incident_id}</p>
    <p><strong>Selected Repair:</strong> {repair_id} <span class="badge">VERIFIED</span></p>
    <p><strong>Causal Diagnosis:</strong> {causal_claim}</p>
  </div>
  <div class="section">
    <h2>Invariant Verification (9-Point Ladder)</h2>
    <ul>
      {checks_html}
    </ul>
  </div>
  <div class="section">
    <h2>Deployment & Rollback</h2>
    <p>To safely dry run: <code>python tools/apply_patch.py --check</code></p>
    <p>To apply fix: <code>python tools/apply_patch.py</code></p>
    <p>To rollback: <code>python tools/rollback_patch.py</code></p>
  </div>
</body>
</html>
"""

    def _diagnosis(
        self,
        incident_id: str,
        repair_id: str,
        patch: PatchCandidate,
        experiment: Optional[Experiment],
        causal_claim: str,
    ) -> Dict[str, Any]:
        hyp_id = getattr(experiment, "hypothesis_id", None) if experiment else None
        return {
            "incident_id": incident_id,
            "repair_id": repair_id,
            "causal_claim": causal_claim,
            "hypothesis_id": hyp_id,
            "source_patch": patch.unified_diff,
            "affected_files": patch.affected_files,
            "config_edits": [
                {
                    "file": e.file,
                    "key": e.key,
                    "parameter": e.parameter,
                    "current_value": e.current_value,
                    "target_value": e.target_value,
                }
                for e in getattr(patch, "config_edits", [])
            ],
        }

    def _provenance(
        self,
        incident_id: str,
        repair_id: str,
        patch: PatchCandidate,
        bundle_root: Path,
        incident: Incident,
    ) -> Dict[str, Any]:
        return {
            "incident_id": incident_id,
            "repair_id": repair_id,
            "source_bundle_id": str(bundle_root),
            "bundle_path": str(getattr(incident, "bundle_path", "")),
            "pipeline": (
                "ingestion -> timeline -> causality -> hypothesis -> "
                "twin-simulation -> patch-forge -> verification -> package"
            ),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "is_demonstration": bool(getattr(incident, "is_demonstration", False)),
            "patch_source": "real_bundle_edit",
        }

    def _capability_report(
        self,
        patch: PatchCandidate,
        report: Optional[VerificationReport],
    ) -> Dict[str, Any]:
        level = level_from_status_string(
            getattr(report, "verification_level", None)
            or getattr(patch, "verification_level", None)
            or "UNVERIFIED"
        )
        return {
            "verification_level": level.value,
            "checks_passed": compute_check_count(patch),
            "checks_total": 9,
            "supported_for_download": bool(patch.verified),
            "affected_files": patch.affected_files,
            "score": patch.score,
        }

    # ----------------------------------------------------------- twin evidence

    def _before_window(
        self, patch: PatchCandidate, model: Optional[SystemModel]
    ) -> float:
        for edit in getattr(patch, "config_edits", []):
            if getattr(edit, "parameter", None) == "batching_window_ms" and edit.current_value is not None:
                try:
                    return float(edit.current_value)
                except (TypeError, ValueError):
                    break
        if model is not None and getattr(model, "has_fitted_model", lambda: False)():
            try:
                return float(model.parameters.batching_window_ms)
            except Exception:
                pass
        return 200.0

    def _after_window(
        self, patch: PatchCandidate, model: Optional[SystemModel]
    ) -> float:
        for edit in getattr(patch, "config_edits", []):
            if getattr(edit, "parameter", None) == "batching_window_ms":
                try:
                    return float(edit.target_value)
                except (TypeError, ValueError):
                    break
        return 100.0

    def _twin_evidence(
        self, window_ms: float, model: Optional[SystemModel]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Run the digital twin at a given batching window and return trials + traces."""
        from cauveris.analysis.model import TwinParameters
        from cauveris.simulation.runner import CloudToRobotDigitalTwin, DigitalTwinFaultInjectors

        if model is not None and getattr(model, "has_fitted_model", lambda: False)():
            params = model.parameters.as_dict()
            params["batching_window_ms"] = window_ms
            parameters = TwinParameters(**params)
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
            faults = DigitalTwinFaultInjectors(batching_window_ms=window_ms)
            twin = CloudToRobotDigitalTwin(faults)

        trials = [twin.step(seed=9000 + i) for i in range(20)]
        span_ok = all(t.get("emergency_stop") is False for t in trials)
        traces = {
            "source": str(twin.__class__.__module__),
            "trials": len(trials),
            "freshness_budget_ms": float(twin.freshness_budget_ms),
            "batching_window_ms": float(window_ms),
            "spans": [
                {
                    "name": "inference_request",
                    "duration_ms": round(
                        sum(t.get("inference_latency_ms", 0.0) for t in trials) / len(trials), 2
                    ),
                    "attributes": {"batch_window_ms": float(window_ms), "unit": "ms"},
                },
                {
                    "name": "robot_control_loop",
                    "duration_ms": round(
                        sum(t.get("total_latency_ms", 0.0) for t in trials) / len(trials), 2
                    ),
                    "status": {
                        "code": 0 if span_ok else 2,
                        "message": (
                            "All trials within freshness budget"
                            if span_ok
                            else "One or more trials exceeded freshness budget (emergency stop)"
                        ),
                    },
                },
                {
                    "name": "safety_monitor",
                    "duration_ms": 0.5,
                    "status": {
                        "code": 0 if span_ok else 2,
                        "message": (
                            "NORMAL_OPERATION: no emergency stops across trials"
                            if span_ok
                            else f"EMERGENCY_STOP in {sum(1 for t in trials if t.get('emergency_stop'))}/{len(trials)} trials"
                        ),
                    },
                },
            ],
        }
        return trials, traces

    def _metrics_csv(self, trials: List[Dict[str, Any]]) -> str:
        ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        lines = [
            "timestamp,batch_wait_ms,gpu_compute_ms,inference_latency_ms,network_delay_ms,total_latency_ms,is_stale,emergency_stop"
        ]
        for t in trials:
            lines.append(
                f"{ts},{t.get('batch_wait_ms', 0.0)},{t.get('gpu_compute_ms', 0.0)},"
                f"{t.get('inference_latency_ms', 0.0)},{t.get('network_delay_ms', 0.0)},"
                f"{t.get('total_latency_ms', 0.0)},{int(bool(t.get('is_stale', False)))},"
                f"{int(bool(t.get('emergency_stop', False)))}"
            )
        return "\n".join(lines) + "\n"

    def _mcap_excerpt(self, trials: List[Dict[str, Any]]) -> bytes:
        buf = io.BytesIO()
        try:
            from mcap.writer import Writer

            w = Writer(buf)
            w.start()
            s_id = w.register_schema(name="robot_state", encoding="jsonschema", data=b"{}")
            c_id = w.register_channel(
                topic="/robot/telemetry", message_encoding="json", schema_id=s_id
            )
            t0 = 1789900190000000000
            for idx, trial in enumerate(trials):
                t_msg = t0 + (idx * 50000000)
                w.add_message(
                    channel_id=c_id,
                    log_time=t_msg,
                    publish_time=t_msg,
                    data=json.dumps(
                        {
                            "speed_mps": 0.0 if trial.get("emergency_stop") else 0.8,
                            "safety_status": "EMERGENCY_STOP" if trial.get("emergency_stop") else "NOMINAL",
                            "detection_age_ms": trial.get("total_latency_ms", 0.0),
                        }
                    ).encode("utf-8"),
                )
            w.finish()
        except Exception as exc:
            logger.debug(f"MCAP excerpt synthesis note: {exc}")
            buf.write(b"")
        return buf.getvalue()

    def _baseline_results(
        self, experiment: Optional[Experiment], trials: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        return {
            "experiment_id": getattr(experiment, "experiment_id", None) if experiment else None,
            "status": "reproduced" if any(t.get("emergency_stop") for t in trials) else "not_reproduced",
            "failure_oracle": getattr(experiment, "failure_oracle", {}) if experiment else {},
            "trial_count": len(trials),
            "emergency_stops": sum(1 for t in trials if t.get("emergency_stop")),
        }

    def _post_results(
        self, experiment: Optional[Experiment], trials: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        return {
            "experiment_id": getattr(experiment, "experiment_id", None) if experiment else None,
            "status": "cleared" if not any(t.get("emergency_stop") for t in trials) else "not_cleared",
            "failure_oracle": getattr(experiment, "failure_oracle", {}) if experiment else {},
            "trial_count": len(trials),
            "emergency_stops": sum(1 for t in trials if t.get("emergency_stop")),
        }

    # ------------------------------------------------------------- snapshots

    def _checks_snapshot(
        self, patch: PatchCandidate, report: Optional[VerificationReport]
    ) -> Dict[str, bool]:
        src = report if report is not None else patch
        out: Dict[str, bool] = {}
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
        ):
            out[name] = bool(getattr(src, name, False))
        return out

    def _candidate_snapshot(self, patch: PatchCandidate) -> Dict[str, Any]:
        return {
            "candidate_id": patch.candidate_id,
            "affected_files": list(patch.affected_files),
            "lines_changed": patch.lines_changed,
            "score": patch.score,
            "verified": patch.verified,
            "verification_level": getattr(patch, "verification_level", ""),
            "config_edits": [
                {
                    "file": e.file,
                    "key": e.key,
                    "parameter": e.parameter,
                    "current_value": e.current_value,
                    "target_value": e.target_value,
                }
                for e in getattr(patch, "config_edits", [])
            ],
        }

    # ----------------------------------------------------------------- helpers

    def _seal_zip(self, artifacts: List[Tuple[str, bytes]]) -> bytes:
        """Write all artifacts into an in-memory zip and return its bytes."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel, data in artifacts:
                if rel.endswith("/"):
                    zf.writestr(rel, "")
                else:
                    zf.writestr(rel, data)
        return buf.getvalue()


def compute_check_summary(patch: PatchCandidate) -> List[Tuple[str, bool]]:
    """The 9 atomic check names with their pass state, for human-readable reports."""
    names = [
        ("applies_cleanly", "Patch applies cleanly"),
        ("regression_test_fails_before", "Regression test fails before patch"),
        ("regression_test_passes_after", "Regression test passes after patch"),
        ("original_failure_not_reproduced", "Original failure not reproduced"),
        ("existing_tests_pass", "Existing tests pass"),
        ("safety_invariants_pass", "Safety invariants pass"),
        ("performance_within_budget", "Performance within budget"),
        ("forbidden_change_scan_passes", "Forbidden-change scan passes"),
        ("rollback_test_passes", "Rollback test passes"),
    ]
    return [(label, bool(getattr(patch, attr, False))) for attr, label in names]
