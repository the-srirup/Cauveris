"""
Tests for Phase 15: Complete Report Generation.
Verifies comprehensive incident report generation (JSON + Markdown), all 8 canonical
sections, unambiguous UNAVAILABLE / NOT_PERFORMED annotations, full traceability,
and report API endpoints.
"""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from fastapi.testclient import TestClient

from cauveris.api.main import app, incidents, pipeline_contexts, PipelineContext
from cauveris.schemas.incident import Incident
from cauveris.schemas.hypothesis import Hypothesis
from cauveris.schemas.experiment import Experiment
from cauveris.schemas.patch import PatchCandidate, VerificationReport
from cauveris.verifier.atomic_checks import (
    AtomicCheckRecord,
    CheckStatus,
    VerificationLevel,
    VerificationSummary,
)
from cauveris.report.generator import ReportGenerator
from cauveris.model_gateway.records import get_execution_store, ModelExecutionRecord
from cauveris.model_gateway.enums import ProviderState, ModelTaskType


@pytest.mark.asyncio
async def test_report_generator_full_pipeline(tmp_path, monkeypatch):
    """
    Test generating full report with all components present.
    Verifies JSON schema and all 8 Markdown sections.
    """
    monkeypatch.setenv("CAUVERIS_REPORT_STORE_PATH", str(tmp_path / "reports"))

    inc_id = "INC-RPT-001"
    incident = Incident(
        id=inc_id,
        title="Order Queue Backpressure Failure",
        description="Excessive message queuing caused memory blowout",
        system_name="OrderProcessingCluster",
        approximate_time=datetime.now(timezone.utc),
    )

    # Hypotheses with full traceability
    hypotheses = [
        Hypothesis(
            incident_id=inc_id,
            hypothesis_id="hyp-001",
            causal_claim="Queue consumer worker count was set below required throughput",
            expected_observation="Queue latency drops under 50ms",
            intervention="Set worker threads to 16",
            confidence_prior=0.85,
            confidence_rationale="Observed worker count 2 against 1500 req/s load",
            supporting_evidence_ids=["ev-worker-count", "ev-load-spikes"],
            contradicting_evidence_ids=[],
            falsification_criteria="If worker thread count >= 16 and queue still grows",
            provider_execution_id="exec-model-456",
            speculative=False,
        )
    ]

    # Experiment with simulation metrics
    experiments = [
        Experiment(
            incident_id=inc_id,
            experiment_id="exp-001",
            hypothesis_id="hyp-001",
            branch_name="branch-scale-workers",
            intervention="worker_threads=16",
            reproduction_count=10,
            trial_count=10,
            reproduction_rate=1.0,
            conclusion="REPRODUCED",
        )
    ]

    # Patch Candidate
    patches = [
        PatchCandidate(
            incident_id=inc_id,
            candidate_id="patch-exp-001",
            hypothesis_id="hyp-001",
            rationale="Scale worker thread pool to absorb traffic spikes",
            target_file="config.yaml",
            affected_files=["config.yaml"],
            unified_diff="--- config.yaml\n+++ config.yaml\n@@ -1 +1 @@\n-workers: 2\n+workers: 16\n",
            before_hash="a" * 64,
            after_hash="b" * 64,
            file_checksums={"config.yaml": {"before": "a" * 64, "after": "b" * 64}},
            is_selected=True,
            verified=True,
            verification_level="RUNTIME_VERIFIED",
        )
    ]

    # Atomic Verification Report
    chk1 = AtomicCheckRecord(
        check_id="chk-001",
        name="syntax_check",
        description="Validates YAML syntax",
        target_level=VerificationLevel.MODEL_VERIFIED,
        required=True,
        status=CheckStatus.PASSED,
        actual="YAML valid",
    )
    chk2 = AtomicCheckRecord(
        check_id="chk-002",
        name="load_test",
        description="Simulates 2000 req/s",
        target_level=VerificationLevel.RUNTIME_VERIFIED,
        required=True,
        status=CheckStatus.PASSED,
        actual="Queue length steady at 4",
    )
    v_summary = VerificationSummary(
        summary_id="vsum-001",
        candidate_id="patch-exp-001",
        experiment_id="exp-001",
        invariant_set_id="inv-001",
        baseline_run_id="run-base-001",
        intervention_run_id="run-int-001",
        achieved_level=VerificationLevel.RUNTIME_VERIFIED,
        overall_status="PASSED",
        checks=[chk1, chk2],
        checks_passed_count=2,
        checks_failed_count=0,
        checks_skipped_count=0,
        verified=True,
    )

    v_reports = [
        VerificationReport(
            incident_id=inc_id,
            patch_candidate_id="patch-exp-001",
            verified=True,
            verification_level=VerificationLevel.RUNTIME_VERIFIED,
            verification_summary=v_summary.model_dump(),
        )
    ]

    # Model Execution Record
    rec = ModelExecutionRecord(
        execution_id="exec-model-456",
        incident_id=inc_id,
        provider="nebius",
        provider_state=ProviderState.NEBIUS_NVIDIA_ACTIVE,
        model_id="nvidia/llama-3.1-nemotron-70b-instruct",
        task_id=ModelTaskType.HYPOTHESIS_PROPOSAL.value,
        usage={"input_tokens": 300, "output_tokens": 120},
    )
    get_execution_store().record(rec)

    generator = ReportGenerator()
    report = await generator.generate(
        incident=incident,
        hypotheses=hypotheses,
        experiments=experiments,
        patch_candidates=patches,
        verification_reports=v_reports,
    )

    assert report["incident_id"] == inc_id
    assert report["title"] == incident.title
    assert "report_json_path" in report
    assert "report_markdown_path" in report

    # Verify JSON file exists on disk
    json_path = Path(report["report_json_path"])
    assert json_path.exists()
    with open(json_path, "r", encoding="utf-8") as f:
        loaded_json = json.load(f)
    assert loaded_json["incident_id"] == inc_id
    assert len(loaded_json["hypotheses"]) == 1
    assert loaded_json["hypotheses"][0]["causal_claim"] == hypotheses[0].causal_claim
    assert loaded_json["hypotheses"][0]["supporting_evidence_ids"] == ["ev-worker-count", "ev-load-spikes"]
    assert loaded_json["hypotheses"][0]["falsification_criteria"] == hypotheses[0].falsification_criteria

    # Verify Markdown file exists on disk and contains all 8 canonical sections
    md_path = Path(report["report_markdown_path"])
    assert md_path.exists()
    md_content = md_path.read_text(encoding="utf-8")

    assert "## 1. Incident Overview" in md_content
    assert "## 2. Evidence Grounding & Inventory" in md_content
    assert "## 3. Root Cause Analysis & Hypotheses" in md_content
    assert "## 4. Digital Twin Simulation & Verification" in md_content
    assert "## 5. Candidate Patches & Structure-Aware Edits" in md_content
    assert "## 6. Atomic Verification Summary" in md_content
    assert "## 7. Repair Package & Deployment References" in md_content
    assert "## 8. Model Assistance Transparency" in md_content

    # Verify Markdown content details
    assert "Order Processing Cluster" in md_content or "OrderProcessingCluster" in md_content
    assert "Queue consumer worker count was set below required throughput" in md_content
    assert "ev-worker-count, ev-load-spikes" in md_content
    assert "exec-model-456" in md_content
    assert "config.yaml" in md_content
    assert "RUNTIME_VERIFIED" in md_content
    assert "syntax_check" in md_content
    assert "load_test" in md_content


@pytest.mark.asyncio
async def test_report_generator_missing_sections_unambiguous(tmp_path, monkeypatch):
    """
    Test generating report for incident where steps were not performed.
    Verifies that missing sections explicitly report UNAVAILABLE or NOT_PERFORMED
    with clear explanations rather than omitting content.
    """
    monkeypatch.setenv("CAUVERIS_REPORT_STORE_PATH", str(tmp_path / "reports"))

    inc_id = "INC-RPT-EMPTY"
    incident = Incident(
        id=inc_id,
        title="Empty Incident For Negative Test",
        description="No pipeline execution performed",
        system_name="TestSystem",
        approximate_time=datetime.now(timezone.utc),
    )

    generator = ReportGenerator()
    report = await generator.generate(
        incident=incident,
        hypotheses=[],
        experiments=[],
        patch_candidates=[],
        verification_reports=[],
    )

    md_path = Path(report["report_markdown_path"])
    assert md_path.exists()
    md_content = md_path.read_text(encoding="utf-8")

    # Check for all 8 section headings
    assert "## 1. Incident Overview" in md_content
    assert "## 2. Evidence Grounding & Inventory" in md_content
    assert "## 3. Root Cause Analysis & Hypotheses" in md_content
    assert "## 4. Digital Twin Simulation & Verification" in md_content
    assert "## 5. Candidate Patches & Structure-Aware Edits" in md_content
    assert "## 6. Atomic Verification Summary" in md_content
    assert "## 7. Repair Package & Deployment References" in md_content
    assert "## 8. Model Assistance Transparency" in md_content

    # Check unambiguous missing annotations with reasons
    assert "UNAVAILABLE: No causal hypotheses were formulated for this incident." in md_content
    assert "NOT_PERFORMED: No digital twin simulations were executed." in md_content
    assert "UNAVAILABLE: No candidate patches were produced." in md_content
    assert "NOT_PERFORMED: No atomic verification checks were executed." in md_content
    assert "NOT_PERFORMED: No verified repair package has been built or staged." in md_content
    assert "NOT_PERFORMED: No external model provider executions recorded for this incident." in md_content


def test_report_api_endpoints(test_user, tmp_path, monkeypatch):
    """
    Test report API endpoints:
    - GET /api/v1/incidents/{incident_id}/report (JSON)
    - GET /api/v1/incidents/{incident_id}/report?format=markdown (Markdown text)
    - GET /api/v1/incidents/{incident_id}/reports/{report_id}
    - GET /api/v1/incidents/{incident_id}/reports/{report_id}?format=markdown
    """
    monkeypatch.setenv("CAUVERIS_REPORT_STORE_PATH", str(tmp_path / "reports"))
    client = TestClient(app)

    inc_id = "INC-RPT-API-TEST"
    inc = Incident(
        id=inc_id,
        title="API Test Incident",
        description="Testing report endpoint formats",
        system_name="ApiGateway",
    )
    user_id = test_user["user"].id if "user" in test_user else test_user.get("user_id")
    setattr(inc, "_owner_user_id", user_id)
    incidents[inc_id] = inc

    report_payload = {
        "incident_id": inc_id,
        "title": "API Test Incident",
        "system_name": "ApiGateway",
        "description": "Testing report endpoint formats",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "COMPLETED",
        "hypotheses": [],
        "experiments": [],
        "patch_candidates": [],
        "verification_reports": [],
        "report_markdown": "# Incident Investigation Report: INC-RPT-API-TEST\n## 1. Incident Overview\n- **Incident ID**: INC-RPT-API-TEST\n",
    }

    # Store in pipeline_contexts
    ctx = PipelineContext(incident=inc)
    ctx.final_report = report_payload
    pipeline_contexts[inc_id] = ctx

    headers = test_user["headers"]

    # 1. JSON Report
    resp_json = client.get(f"/api/v1/incidents/{inc_id}/report", headers=headers)
    assert resp_json.status_code == 200
    assert resp_json.json()["incident_id"] == inc_id

    # 2. Markdown Report via query param
    resp_md = client.get(f"/api/v1/incidents/{inc_id}/report?format=markdown", headers=headers)
    assert resp_md.status_code == 200
    assert resp_md.headers["content-type"].startswith("text/markdown")
    assert "# Incident Investigation Report: INC-RPT-API-TEST" in resp_md.text

    # 3. Report by ID JSON
    resp_by_id = client.get(f"/api/v1/incidents/{inc_id}/reports/rpt-{inc_id}-001", headers=headers)
    assert resp_by_id.status_code == 200
    assert resp_by_id.json()["incident_id"] == inc_id

    # 4. Report by ID Markdown
    resp_by_id_md = client.get(f"/api/v1/incidents/{inc_id}/reports/rpt-{inc_id}-001?format=markdown", headers=headers)
    assert resp_by_id_md.status_code == 200
    assert resp_by_id_md.headers["content-type"].startswith("text/markdown")
    assert "# Incident Investigation Report: INC-RPT-API-TEST" in resp_by_id_md.text
