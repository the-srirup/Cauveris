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
from cauveris.config import get_settings
import logging
import hashlib
from cauveris.patch.unified_diff import reverse_unified_diff

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
        stage_statuses: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        generate a comprehensive incident report.

        Args:
            incident: The processed incident
            hypotheses: Generated hypotheses
            experiments: Experiment results
            patch_candidates: Generated patch candidates
            verification_reports: Verification results for patches
            stage_statuses: The pipeline's per-stage outcomes, when known.  A
                report that says ``COMPLETED`` while a stage was blocked must
                not hide that, so the caller hands them over rather than the
                report guessing.

        Returns:
            Dictionary containing the report and paths to generated artifacts
        """
        logger.info(f"Generating report for incident {incident.id}")

        # The incident's calibrated model, so that every number the report
        # shows is computed from this incident's own evidence rather than
        # from a default pipeline.
        self._model = self._resolve_model(incident)
        self._verification_reports = verification_reports
        self._incident_bundle = getattr(incident, "bundle_path", "")
        self._incident_is_sample = bool(getattr(incident, "is_demonstration", False))

        # Index hypotheses by id so patches can be traced back to their causal claim
        self._hypotheses_by_id = {
            h.hypothesis_id: h for h in hypotheses if getattr(h, "hypothesis_id", None)
        }

        # Create report directory
        report_dir = Path(self.settings.report_store_path) / incident.id
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
            "artifact_inventory": getattr(incident, "artifact_inventory", []),
            "capability_report": getattr(incident, "capability_report", None),
            "discovered_repository": getattr(incident, "discovered_repository", None),
            "hypotheses": [self._hypothesis_to_dict(h) for h in hypotheses],
            "experiments": [self._experiment_to_dict(e) for e in experiments],
            "patch_candidates": [self._patch_to_dict(p) for p in patch_candidates],
            "verification_reports": [self._verification_to_dict(v) for v in verification_reports],
            "status": self._report_status(
                hypotheses, experiments, patch_candidates, verification_reports, stage_statuses
            ),
            "summary": self._report_summary(
                hypotheses, experiments, patch_candidates, verification_reports
            ),
            "stage_outcomes": list(stage_statuses or []),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Attach recorded model executions if available
        try:
            from cauveris.model_gateway.records import get_execution_store
            incident_report["model_executions"] = [
                rec.model_dump() for rec in get_execution_store().get_by_incident(incident.id)
            ]
        except Exception as exc:
            logger.debug(f"Could not attach model executions: {exc}")
            incident_report["model_executions"] = []

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
            from cauveris.patch.package_builder import PatchPackageBuilder
            builder = PatchPackageBuilder(settings=self.settings)
            pkg_res = await builder.build_package(
                incident=incident,
                patch=target_patch,
                experiment=experiment,
                hypotheses=hypotheses,
                verification_reports=verification_reports,
                system_model=self._model,
                output_dir=report_dir,
            )
            incident_report["selected_repair_id"] = target_patch.candidate_id
            incident_report["patch_package_path"] = str(pkg_res.package_dir)
            incident_report["patch_package_zip_path"] = str(pkg_res.zip_path)
            incident_report["patch_package_checksum_sha256"] = pkg_res.checksum_sha256

        # Generate comprehensive human-readable Markdown report
        md_text = self._generate_markdown_report(incident_report)
        md_report_path = report_dir / "incident_report.md"
        with open(md_report_path, "w", encoding="utf-8") as f:
            f.write(md_text)

        incident_report["report_markdown_path"] = str(md_report_path)
        incident_report["report_json_path"] = str(report_path)
        incident_report["report_markdown"] = md_text

        # Re-save JSON with the paths
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(incident_report, f, indent=2, default=str)

        # Materialize the per-audience markdown variants as real artifacts, so
        # the reports inventory only ever lists files that exist on disk.
        for _variant in ("technical", "executive", "compliance"):
            try:
                render_variant_markdown(incident_report, _variant, report_dir)
            except Exception as exc:
                logger.warning(f"Could not render report variant '{_variant}': {exc}")

        logger.info(f"Report generated at {report_dir}")
        return incident_report

    def _generate_markdown_report(self, data: Dict[str, Any]) -> str:
        lines: List[str] = []
        inc_id = data.get("incident_id", "UNKNOWN")
        title = data.get("title", "Incident Report")
        status = data.get("status", "INCOMPLETE")
        gen_at = data.get("generated_at", "UNAVAILABLE")

        lines.append(f"# Incident Investigation Report: {inc_id} - {title}\n")
        lines.append(f"**Generated**: `{gen_at}` | **Investigation Status**: `{status}`\n")
        lines.append("---\n")

        # 1. Incident Overview
        lines.append("## 1. Incident Overview\n")
        lines.append(f"- **Incident ID**: {inc_id}")
        lines.append(f"- **Title**: {title}")
        lines.append(f"- **System**: {data.get('system_name') or 'UNAVAILABLE'}")
        lines.append(f"- **Description**: {data.get('description') or 'UNAVAILABLE'}")
        timeline = data.get("timeline") or []
        if timeline:
            lines.append(f"- **Timeline Events**: {len(timeline)} event(s) recorded.")
        else:
            lines.append("- **Timeline**: UNAVAILABLE: No timeline events recorded")
        lines.append("")

        # 2. Evidence Grounding & Inventory
        lines.append("## 2. Evidence Grounding & Inventory\n")
        ev_sum = data.get("evidence_summary", {})
        total_ev = ev_sum.get("total_evidence_items", 0)
        req_ev = ev_sum.get("required_evidence_items", 0)
        missing_req = ev_sum.get("missing_required_evidence", [])
        lines.append(f"- **Total Evidence Items**: {total_ev}")
        lines.append(f"- **Required Evidence Items**: {req_ev}")
        if missing_req:
            lines.append(f"- **Missing Required Evidence**: {', '.join(missing_req)}")
        else:
            lines.append("- **Missing Required Evidence**: None")
        lines.append("")

        # 3. Root Cause Analysis & Hypotheses
        lines.append("## 3. Root Cause Analysis & Hypotheses\n")
        hyps = data.get("hypotheses") or []
        if hyps:
            for i, h in enumerate(hyps, 1):
                h_id = h.get("hypothesis_id", f"H{i}")
                claim = h.get("causal_claim", "UNAVAILABLE")
                conf = h.get("confidence_prior", 0.0)
                supp = h.get("supporting_evidence_ids") or h.get("supporting_artifact_ids") or []
                contra = h.get("contradicting_evidence_ids") or h.get("contradicting_artifact_ids") or []
                falsify = h.get("falsification_criteria") or h.get("falsifying_observation") or "UNAVAILABLE"
                speculative = h.get("speculative", False)
                lines.append(f"### {h_id}: {claim}")
                lines.append(f"- **Confidence**: {conf:.2f} ({'SPECULATIVE' if speculative else 'GROUNDED'})")
                if h.get("confidence_rationale"):
                    lines.append(f"- **Confidence Rationale**: {h['confidence_rationale']}")
                if h.get("provider_execution_id"):
                    lines.append(f"- **Provider Execution ID**: `{h['provider_execution_id']}`")
                lines.append(f"- **Supporting Evidence**: {', '.join(supp) if supp else 'None'}")
                lines.append(f"- **Contradicting Evidence**: {', '.join(contra) if contra else 'None'}")
                lines.append(f"- **Falsification Criteria**: {falsify}")
                lines.append("")
        else:
            lines.append("UNAVAILABLE: No causal hypotheses were formulated for this incident.\n")

        # 4. Simulation Results & Reproduction
        lines.append("## 4. Digital Twin Simulation & Verification\n")
        exps = data.get("experiments") or []
        if exps:
            for exp in exps:
                exp_id = exp.get("experiment_id", "")
                repro_rate = exp.get("reproduction_rate", 0.0)
                repro_count = exp.get("reproduction_count", 0)
                trial_count = exp.get("trial_count", 0)
                conclusion = exp.get("conclusion", "UNAVAILABLE")
                lines.append(f"### Experiment `{exp_id}`")
                lines.append(f"- **Intervention**: {exp.get('intervention', 'UNAVAILABLE')}")
                lines.append(f"- **Reproduction**: {repro_count}/{trial_count} trials ({repro_rate:.1%})")
                lines.append(f"- **Conclusion**: {conclusion}")
                lines.append("")
        else:
            lines.append("NOT_PERFORMED: No digital twin simulations were executed.\n")

        # 5. Patch Details
        lines.append("## 5. Candidate Patches & Structure-Aware Edits\n")
        patches = data.get("patch_candidates") or []
        if patches:
            for p in patches:
                p_id = p.get("candidate_id", "")
                aff = p.get("affected_files") or []
                level = p.get("verification_level", "UNVERIFIED")
                is_sel = p.get("is_selected", False)
                lines.append(f"### Candidate `{p_id}` ({'SELECTED' if is_sel else 'NOT_SELECTED'})")
                lines.append(f"- **Target Files**: {', '.join(aff) if aff else 'None'}")
                lines.append(f"- **Verification Level**: `{level}` | **Verified**: `{p.get('verified', False)}`")
                if p.get("before_hash") and p.get("after_hash"):
                    lines.append(f"- **Target Checksums**: before `{p['before_hash'][:12]}...` -> after `{p['after_hash'][:12]}...`")
                if p.get("rationale"):
                    lines.append(f"- **Rationale**: {p['rationale']}")
                if p.get("unified_diff"):
                    lines.append("\n```diff")
                    lines.append(p["unified_diff"].strip())
                    lines.append("```\n")
        else:
            lines.append("UNAVAILABLE: No candidate patches were produced.\n")

        # 6. Verification Summary
        lines.append("## 6. Atomic Verification Summary\n")
        v_reports = data.get("verification_reports") or []
        if v_reports:
            for rep in v_reports:
                cand_id = rep.get("patch_candidate_id", "")
                v_level = rep.get("verification_level", "UNVERIFIED")
                v_sum = rep.get("verification_summary") or {}
                ov_status = v_sum.get("overall_status", "UNKNOWN")
                lines.append(f"### Verification for `{cand_id}`: `{v_level}` ({ov_status})")
                checks = v_sum.get("checks") or []
                if checks:
                    lines.append("| Check Name | Required | Status | Target Level | Details |")
                    lines.append("|---|---|---|---|---|")
                    for c in checks:
                        lines.append(f"| {c.get('name')} | {'Yes' if c.get('required') else 'No'} | `{c.get('status')}` | `{c.get('target_level')}` | {c.get('failure_reason') or c.get('actual') or 'OK'} |")
                    lines.append("")
                if v_sum.get("rejection_reasons"):
                    lines.append("**Rejection Reasons**:")
                    for rr in v_sum["rejection_reasons"]:
                        lines.append(f"- {rr}")
                    lines.append("")
        else:
            lines.append("NOT_PERFORMED: No atomic verification checks were executed.\n")

        # 7. Repair Package & Deployment
        lines.append("## 7. Repair Package & Deployment References\n")
        sel_rep = data.get("selected_repair_id")
        pkg_path = data.get("patch_package_path")
        pkg_zip = data.get("patch_package_zip_path")
        pkg_sha = data.get("patch_package_checksum_sha256")
        if sel_rep and pkg_zip:
            lines.append(f"- **Selected Repair Candidate**: `{sel_rep}`")
            if pkg_path:
                lines.append(f"- **Package Staging Path**: `{pkg_path}`")
            lines.append(f"- **Package ZIP Path**: `{pkg_zip}`")
            lines.append(f"- **Package Checksum (SHA-256)**: `{pkg_sha}`")
        else:
            lines.append("NOT_PERFORMED: No verified repair package has been built or staged.\n")

        # 8. Model Assistance Transparency
        lines.append("## 8. Model Assistance Transparency\n")
        mod_execs = data.get("model_executions") or []
        if mod_execs:
            lines.append("| Execution ID | Provider | Model | Task | Tokens | Created At |")
            lines.append("|---|---|---|---|---|---|")
            for m in mod_execs:
                m_model = m.get("model_name") or m.get("model_id") or "UNAVAILABLE"
                m_task = m.get("task_type") or m.get("task_id") or "UNAVAILABLE"
                usage = m.get("usage") or {}
                tokens = m.get("total_tokens") or ((usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0))
                lines.append(f"| `{m.get('execution_id', '')[:16]}` | {m.get('provider')} | {m_model} | {m_task} | {tokens} | {m.get('created_at', '')} |")
            lines.append("")
        else:
            lines.append("NOT_PERFORMED: No external model provider executions recorded for this incident.\n")

        return "\n".join(lines)

    async def _generate_patch_package(
        self,
        incident_id: str,
        patch: PatchCandidate,
        experiment: Optional[Experiment],
        report_dir: Path,
    ) -> Path:
        """
        Generate a patch package directory with all required artifacts.
        """
        from cauveris.patch.package_builder import PatchPackageBuilder
        builder = PatchPackageBuilder(settings=self.settings)
        incident_obj = getattr(self, "_incident", None) or Incident(
            id=incident_id,
            title=f"Incident {incident_id}",
            bundle_path=getattr(self, "_incident_bundle", ""),
        )
        pkg_res = await builder.build_package(
            incident=incident_obj,
            patch=patch,
            experiment=experiment,
            hypotheses=list(self._hypotheses_by_id.values()) if hasattr(self, "_hypotheses_by_id") else [],
            verification_reports=getattr(self, "_verification_reports", []),
            system_model=self._model,
            output_dir=report_dir,
        )
        return pkg_res.package_dir

    def _report_status(
        self,
        hypotheses: List[Hypothesis],
        experiments: List[Experiment],
        patch_candidates: List[PatchCandidate],
        verification_reports: List[VerificationReport],
        stage_statuses: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """The status the report actually earned.

        A report that says ``COMPLETED`` must mean the investigation reached a
        remediation, not merely that the process ran out of stages.  The
        states are:

        ``COMPLETED``
            A patch was produced and passed verification.
        ``DIAGNOSED``
            Root causes were identified and tested, but no patch survived
            verification.  The diagnosis is real; the fix is not.
        ``INCOMPLETE``
            Evidence was insufficient to say anything conclusive.
        ``PARTIAL``
            Some stage of the pipeline failed or was blocked, so the report
            covers only part of the investigation.
        """
        blocked = [
            s
            for s in (stage_statuses or [])
            if str(s.get("status", "")).upper() in ("FAILED", "SKIPPED", "CANCELLED")
        ]
        if blocked:
            return "PARTIAL"

        verified = [v for v in verification_reports if getattr(v, "verified", False)]
        if verified:
            return "COMPLETED"
        if patch_candidates:
            # A patch exists but did not clear the nine gates.  That is a
            # diagnosis with an unverified fix attached, and it must not be
            # presented as a completed repair.
            return "DIAGNOSED"
        if hypotheses:
            return "DIAGNOSED"
        return "INCOMPLETE"

    def _report_summary(
        self,
        hypotheses: List[Hypothesis],
        experiments: List[Experiment],
        patch_candidates: List[PatchCandidate],
        verification_reports: List[VerificationReport],
    ) -> Dict[str, Any]:
        """A one-glance account of what the investigation delivered."""
        verified = [v for v in verification_reports if getattr(v, "verified", False)]
        checks_passed = 0
        for report in verified:
            checks_passed = max(
                checks_passed,
                int(report.details.get("checks_passed", 9) or 0)
                if isinstance(report.details, dict)
                else 9,
            )
        top = max((getattr(p, "score", 0.0) for p in patch_candidates), default=0.0)
        return {
            "hypotheses": len(hypotheses),
            "experiments": len(experiments),
            "patches": len(patch_candidates),
            "verified_patches": len(verified),
            "best_patch_score": round(top, 4),
            "verification_checks_passed": checks_passed,
            "verification_checks_total": 9,
            "remediation_available": bool(verified),
        }

    def _hypothesis_to_dict(self, hypothesis: Hypothesis) -> Dict[str, Any]:
        """Convert Hypothesis object to dictionary."""
        return {
            "hypothesis_id": hypothesis.hypothesis_id,
            "causal_claim": hypothesis.causal_claim,
            "status": hypothesis.status,
            "supporting_artifact_ids": hypothesis.supporting_artifact_ids,
            "supporting_evidence_ids": getattr(hypothesis, "supporting_evidence_ids", []) or hypothesis.supporting_artifact_ids,
            "contradicting_artifact_ids": hypothesis.contradicting_artifact_ids,
            "contradicting_evidence_ids": getattr(hypothesis, "contradicting_evidence_ids", []) or hypothesis.contradicting_artifact_ids,
            "missing_evidence": hypothesis.missing_evidence,
            "confidence_prior": hypothesis.confidence_prior,
            "confidence_rationale": getattr(hypothesis, "confidence_rationale", None),
            "provider_execution_id": getattr(hypothesis, "provider_execution_id", None),
            "falsification_criteria": getattr(hypothesis, "falsification_criteria", None) or hypothesis.falsifying_observation,
            "speculative": getattr(hypothesis, "speculative", False),
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
            "incident_id": getattr(patch, "incident_id", None),
            "hypothesis_id": getattr(patch, "hypothesis_id", None),
            "target_file": getattr(patch, "target_file", None) or (patch.affected_files[0] if patch.affected_files else None),
            "rationale": getattr(patch, "rationale", None),
            "before_hash": getattr(patch, "before_hash", None),
            "after_hash": getattr(patch, "after_hash", None),
            "file_checksums": getattr(patch, "file_checksums", {}),
            "is_selected": getattr(patch, "is_selected", False),
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
            "applies_cleanly": getattr(patch, "applies_cleanly", patch.applied_cleanly),
            "regression_test_fails_before": patch.regression_test_fails_before,
            "regression_test_passes_after": patch.regression_test_passes_after,
            "original_failure_not_reproduced": patch.original_failure_not_reproduced,
            "existing_tests_pass": patch.existing_tests_pass,
            "safety_invariants_pass": patch.safety_invariants_pass,
            "performance_within_budget": patch.performance_within_budget,
            "forbidden_change_scan_passes": patch.forbidden_change_scan_passes,
            "rollback_test_passes": patch.rollback_test_passes,
            "verified": patch.verified,
            "verification_level": getattr(patch, "verification_level", "UNVERIFIED"),
            "verification_summary": getattr(patch, "verification_summary", None),
        }

    def _verification_to_dict(self, report: VerificationReport) -> Dict[str, Any]:
        """Convert VerificationReport object to dictionary."""
        return {
            "patch_candidate_id": report.patch_candidate_id,
            "incident_id": getattr(report, "incident_id", None),
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
            "verification_level": getattr(report, "verification_level", "UNVERIFIED"),
            "verification_summary": getattr(report, "verification_summary", None),
            "details": report.details,
        }

    async def _generate_legacy_patch_package(
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
git apply --reverse --check patch.patch || echo "Patch check failed"

# Apply the reverse patch
echo "Applying reverse patch..."
git apply --reverse patch.patch

echo "Rollback complete. Please verify the system is back to its previous state."
"""
        with open(rollback_path, "w", encoding="utf-8") as f:
            f.write(rollback_content)
        # Make it executable
        os.chmod(rollback_path, 0o755)

        # The downloadable package is an audit artifact, not just a diff.  Keep
        # every claim alongside the bytes that support it so a consumer can
        # validate a download without access to Cauveris.
        verification = next(
            (v for v in getattr(self, "_verification_reports", [])
             if getattr(v, "patch_candidate_id", None) == patch.candidate_id),
            None,
        )
        diagnosis = {
            "incident_id": incident_id,
            "causal_claim": causal_claim,
            "hypothesis_id": getattr(experiment, "hypothesis_id", None) if experiment else None,
            "supporting_artifacts": getattr(
                self._hypotheses_by_id.get(getattr(experiment, "hypothesis_id", "")),
                "supporting_artifact_ids", [],
            ) if experiment else [],
        }
        provenance = {
            "incident_id": incident_id,
            "bundle_path": str(getattr(self, "_incident_bundle", "")),
            "pipeline": "uploaded-bytes -> extraction -> inventory -> readers -> normalization -> timeline -> mechanism -> hypothesis -> baseline -> intervention -> patch -> isolated-apply -> validation -> verification -> rollback",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "is_sample": bool(getattr(self, "_incident_is_sample", False)),
        }
        capability = {
            "verification_level": "verified" if patch.verified else "diagnosed",
            "checks": 9,
            "supported_for_download": bool(patch.verified),
            "affected_files": patch.affected_files,
            "syntax_or_build_validation": patch.existing_test_state,
        }
        baseline = {
            "experiment_id": getattr(experiment, "experiment_id", None) if experiment else None,
            "failure_oracle": getattr(experiment, "failure_oracle", {}) if experiment else {},
            "status": "reproduced" if getattr(patch, "regression_test_fails_before", False) else "not_reproduced",
        }
        post = {
            "experiment_id": getattr(experiment, "experiment_id", None) if experiment else None,
            "failure_oracle": getattr(experiment, "failure_oracle", {}) if experiment else {},
            "status": "cleared" if getattr(patch, "original_failure_not_reproduced", False) else "not_cleared",
        }
        (package_dir / "patch.patch").write_text(patch.unified_diff, encoding="utf-8")
        (package_dir / "rollback.patch").write_text(
            reverse_unified_diff(patch.unified_diff), encoding="utf-8"
        )
        (package_dir / "diagnosis.json").write_text(json.dumps(diagnosis, indent=2), encoding="utf-8")
        (package_dir / "diagnosis.md").write_text(
            f"# Diagnosis for {incident_id}\n\n{causal_claim}\n", encoding="utf-8"
        )
        (package_dir / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
        (package_dir / "capability-report.json").write_text(json.dumps(capability, indent=2), encoding="utf-8")
        (package_dir / "baseline-results.json").write_text(json.dumps(baseline, indent=2, default=str), encoding="utf-8")
        (package_dir / "post-intervention-results.json").write_text(json.dumps(post, indent=2, default=str), encoding="utf-8")
        (package_dir / "verification-report.json").write_text(
            json.dumps(self._verification_to_dict(verification) if verification else {}, indent=2, default=str),
            encoding="utf-8",
        )
        (package_dir / "limitations.md").write_text(
            "# Limitations\n\nResults are calibrated from the uploaded evidence and the isolated digital-twin replay. Real deployment rollout remains operator-controlled.\n",
            encoding="utf-8",
        )
        (package_dir / "application-instructions.md").write_text(
            "# Application\n\nRun `python apply_patch.py --check --target <workspace>` before `python apply_patch.py --target <workspace>`. Review `verification-report.json` and keep `rollback.patch` with the deployment record.\n",
            encoding="utf-8",
        )

        manifest = {
            "format": "cauveris-repair-package/v1",
            "incident_id": incident_id,
            "patch_candidate_id": patch.candidate_id,
            "verification_level": capability["verification_level"],
            "is_sample": provenance["is_sample"],
            "files": sorted(p.name for p in package_dir.iterdir() if p.is_file()),
            "checksums": "checksums.sha256",
        }
        (package_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        checksum_lines = []
        for path in sorted(p for p in package_dir.iterdir() if p.is_file() and p.name != "checksums.sha256"):
            checksum_lines.append(
                f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
            )
        (package_dir / "checksums.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

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
        # The diff is the fallback, and it comes in the shape the file's own
        # format uses: ``batching_window_ms: 7.5`` in YAML, and
        # ``batching_window_ms = 7.5`` in TOML or INI.
        m = re.search(
            r"\+\s*batching_window_ms\s*[:=]\s*(\d+(?:\.\d+)?)", patch.unified_diff
        )
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


# ---------------------------------------------------------------------------
# Per-audience report variants
#
# Every variant below is rendered from the finished incident report dict —
# the same evidence, hypotheses, experiments, patches and verification records
# the full report contains.  Nothing is asserted that the report does not
# contain.
# ---------------------------------------------------------------------------

#: The nine invariant gates, in the order the verifier applies them.  Keep in
#: sync with the keys `_verification_to_dict` emits.
INVARIANT_GATES: List[tuple] = [
    ("applies_cleanly", "Patch applies cleanly"),
    ("regression_test_fails_before", "Regression test fails before the fix"),
    ("regression_test_passes_after", "Regression test passes after the fix"),
    ("original_failure_not_reproduced", "Original failure is not reproduced"),
    ("existing_tests_pass", "Existing tests still pass"),
    ("safety_invariants_pass", "Safety invariants hold"),
    ("performance_within_budget", "Performance stays within budget"),
    ("forbidden_change_scan_passes", "Forbidden-change scan passes"),
    ("rollback_test_passes", "Rollback restores the original state"),
]


def _enum_val(x: Any) -> Any:
    """Render enum members by their value, not their repr (StatusLabel.INFERRED)."""
    return getattr(x, "value", x)


def render_executive_markdown(data: Dict[str, Any]) -> str:
    """Render an executive summary derived from a finished report dict."""
    inc_id = data.get("incident_id", "UNKNOWN")
    status = _enum_val(data.get("status", "UNKNOWN"))
    gen_at = data.get("generated_at", "UNAVAILABLE")
    summary = data.get("summary") or {}
    ev = data.get("evidence_summary") or {}
    hyps = data.get("hypotheses") or []
    exps = data.get("experiments") or []
    patches = data.get("patch_candidates") or []
    verifs = [v for v in (data.get("verification_reports") or []) if v.get("verified")]

    lines: List[str] = []
    lines.append(f"# Executive Summary — {inc_id}\n")
    lines.append(f"**Investigation status**: `{status}` | **Generated**: `{gen_at}`\n")

    lines.append("## Key findings\n")
    if hyps:
        ranked = sorted(
            hyps,
            key=lambda h: (h.get("confidence_posterior") or h.get("confidence_prior") or 0.0),
            reverse=True,
        )
        top = ranked[0]
        conf = top.get("confidence_posterior") or top.get("confidence_prior") or 0.0
        lines.append(
            f"- **Most likely root cause** (`{top.get('hypothesis_id', '?')}`, "
            f"{conf:.0%} confidence, status {_enum_val(top.get('status', 'UNKNOWN'))}): "
            f"{top.get('causal_claim', 'UNAVAILABLE')}"
        )
        lines.append(
            f"- **Hypotheses evaluated**: {summary.get('hypotheses', len(hyps))} | "
            f"**Experiments run**: {summary.get('experiments', len(exps))}"
        )
    else:
        lines.append("- No causal hypotheses were produced for this incident.")
    lines.append("")

    lines.append("## Evidence\n")
    lines.append(
        f"- Evidence items: **{ev.get('total_evidence_items', 0)}** total, "
        f"**{ev.get('required_evidence_items', 0)}** required"
    )
    missing = ev.get("missing_required_evidence") or []
    lines.append(f"- Missing required evidence: {', '.join(str(m) for m in missing) if missing else 'none'}\n")

    lines.append("## Remediation\n")
    if verifs:
        v = verifs[0]
        gates = sum(1 for key, _label in INVARIANT_GATES if v.get(key))
        lines.append(
            f"- **Verified patch** `{v.get('patch_candidate_id', 'unknown')}` passed "
            f"**{gates}/9** invariant gates (verification level `{_enum_val(v.get('verification_level', 'UNVERIFIED'))}`)."
        )
        if data.get("patch_package_checksum_sha256"):
            lines.append(f"- Repair package SHA-256: `{data['patch_package_checksum_sha256']}`")
    elif patches:
        lines.append(
            f"- **No verified remediation exists**: {len(patches)} patch candidate(s) were "
            "produced, but none cleared all nine invariant gates."
        )
    else:
        lines.append("- No patch candidate could be derived for this incident.")
    lines.append("")

    lines.append("## Model assistance\n")
    execs = data.get("model_executions") or []
    if execs:
        lines.append(
            f"- {len(execs)} external model execution(s) were recorded; see the full report's "
            "transparency section for provider, model and token usage."
        )
    else:
        lines.append("- No external model calls were made; analysis ran on the deterministic local pipeline.")
    lines.append("")
    return "\n".join(lines)


def render_compliance_markdown(data: Dict[str, Any]) -> str:
    """Render a compliance/audit-trail document derived from a report dict."""
    inc_id = data.get("incident_id", "UNKNOWN")
    status = _enum_val(data.get("status", "UNKNOWN"))
    gen_at = data.get("generated_at", "UNAVAILABLE")
    ev = data.get("evidence_summary") or {}
    verifs = data.get("verification_reports") or []
    execs = data.get("model_executions") or []
    stages = data.get("stage_outcomes") or []

    lines: List[str] = []
    lines.append(f"# Compliance & Audit Report — {inc_id}\n")
    lines.append(f"**Generated**: `{gen_at}` | **Investigation status**: `{status}`\n")

    lines.append("## 1. Pipeline stage outcomes\n")
    if stages:
        lines.append("| Stage | Status | Error |")
        lines.append("|---|---|---|")
        for s in stages:
            err = (s.get("error") or "").replace("|", "\\|") or "—"
            lines.append(f"| `{s.get('id', s.get('stage_id', '?'))}` | {_enum_val(s.get('status', 'UNKNOWN'))} | {err} |")
        lines.append("")
    else:
        lines.append("No per-stage outcomes were recorded for this report.\n")

    lines.append("## 2. Evidence grounding\n")
    lines.append(f"- Total evidence items: **{ev.get('total_evidence_items', 0)}**")
    lines.append(f"- Required evidence items: **{ev.get('required_evidence_items', 0)}**")
    missing = ev.get("missing_required_evidence") or []
    lines.append(f"- Missing required evidence: {', '.join(str(m) for m in missing) if missing else 'none'}\n")

    lines.append("## 3. Verification gates\n")
    if verifs:
        for v in verifs:
            gates = sum(1 for key, _label in INVARIANT_GATES if v.get(key))
            lines.append(
                f"### `{v.get('patch_candidate_id', 'unknown')}` — verified: `{v.get('verified')}`, "
                f"level `{_enum_val(v.get('verification_level', 'UNVERIFIED'))}`, gates passed **{gates}/9**"
            )
            lines.append("| Gate | Result |")
            lines.append("|---|---|")
            for key, label in INVARIANT_GATES:
                lines.append(f"| {label} | {'PASS' if v.get(key) else 'FAIL'} |")
            lines.append("")
            reasons = (v.get("verification_summary") or {}).get("rejection_reasons") or []
            if reasons:
                lines.append("**Rejection reasons**:")
                for r in reasons:
                    lines.append(f"- {r}")
                lines.append("")
    else:
        lines.append("NOT_PERFORMED: No atomic verification checks were executed.\n")

    lines.append("## 4. Remediation package & provenance\n")
    if data.get("selected_repair_id") and data.get("patch_package_zip_path"):
        lines.append(f"- Selected repair candidate: `{data['selected_repair_id']}`")
        lines.append(f"- Package ZIP: `{data['patch_package_zip_path']}`")
        lines.append(f"- Package SHA-256: `{data.get('patch_package_checksum_sha256') or 'UNAVAILABLE'}`")
    else:
        lines.append("NOT_PERFORMED: No verified repair package has been built or staged.\n")
    lines.append("")

    lines.append("## 5. Model execution provenance\n")
    if execs:
        lines.append("| Execution | Provider | Model | Task | Tokens |")
        lines.append("|---|---|---|---|---|")
        for m in execs:
            usage = m.get("usage") or {}
            tokens = m.get("total_tokens") or ((usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0))
            lines.append(
                f"| `{str(m.get('execution_id', ''))[:16]}` | {m.get('provider', '?')} | "
                f"{m.get('model_name') or m.get('model_id') or '?'} | {m.get('task_type', m.get('task_id', '?'))} | {tokens} |"
            )
        lines.append("")
    else:
        lines.append("NOT_PERFORMED: No external model provider executions recorded for this incident.\n")

    lines.append("## 6. Artifact paths\n")
    lines.append(f"- JSON report: `{data.get('report_json_path') or 'UNAVAILABLE'}`")
    lines.append(f"- Markdown report: `{data.get('report_markdown_path') or 'UNAVAILABLE'}`")
    lines.append("")
    return "\n".join(lines)


def render_variant_markdown(report: Dict[str, Any], variant: str, report_dir: Path) -> Optional[Path]:
    """Materialize a per-type markdown artifact from a finished report dict.

    The ``investigation`` variant is the JSON report itself and needs no extra
    file.  ``technical`` reuses the report's own markdown.  ``executive`` and
    ``compliance`` are rendered from ``report`` and written next to it, so the
    reports inventory only ever lists files that actually exist.
    """
    variant = (variant or "investigation").strip().lower()
    report_dir = Path(report_dir)
    if variant == "executive":
        path = report_dir / "incident_report_executive.md"
        text = render_executive_markdown(report)
    elif variant == "compliance":
        path = report_dir / "incident_report_compliance.md"
        text = render_compliance_markdown(report)
    elif variant == "technical":
        path = report_dir / "incident_report.md"
        text = report.get("report_markdown")
        if not text:
            return None
    else:
        return None
    path.write_text(text, encoding="utf-8")
    return path
