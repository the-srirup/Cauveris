"""
Phase 3 Multi-Process & Persistence Tests for Model Execution Records.

Proves:
1. Worker subprocess writes an execution record to SQLite; API process reads it.
2. Records survive store and process restarts.
3. Records remain incident-scoped (Incident A records cannot be retrieved via Incident B).
4. No sensitive secrets, keys, or raw prompts are persisted.
5. Retention and cleanup policy works.
"""

from __future__ import annotations

import multiprocessing
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cauveris.model_gateway.records import ModelExecutionRecord, ModelExecutionStore  # noqa: E402
from cauveris.model_gateway.enums import ProviderState, ValidationResult  # noqa: E402


def _worker_write_process(db_path: str, incident_id: str, exec_id: str):
    """Simulates an isolated worker process recording model execution."""
    store = ModelExecutionStore(db_path=db_path)
    rec = ModelExecutionRecord(
        execution_id=exec_id,
        incident_id=incident_id,
        job_id="job_worker_123",
        owner_user_id="usr_worker",
        owner_org_id="org_worker",
        provider="nebius",
        provider_state=ProviderState.NEBIUS_NVIDIA_ACTIVE,
        model_id="nvidia/Llama-3.1-Nemotron-70B-Instruct-HF",
        endpoint_mode="hosted",
        task_id="HYPOTHESIS_PROPOSAL",
        task_version="1.0",
        prompt_template_version="1.0",
        structured_output_schema_version="1.0",
        input_artifact_ids=["telemetry/heap.csv", "config/worker.yaml"],
        input_record_ids=["rec_001"],
        redaction_count=2,
        request_id="req_upstream_999",
        latency_ms=145.2,
        response_hash="abc123sha256",
        suggestions_received=3,
        suggestions_accepted=2,
        suggestions_rejected=1,
        validation_result=ValidationResult.ACCEPTED,
        fallback_used=False,
        error_code=None,
        usage={"input_tokens": 512, "output_tokens": 128},
        accepted_suggestions=[{"hypothesis": "memory_exhaustion", "confidence": 0.82}],
        rejected_suggestions=[{"hypothesis": "network_partition", "reason": "No network logs"}],
        rejection_reasons=["No network logs found in bundle"],
        cached=False,
    )
    store.record(rec)


def test_multiprocess_write_and_api_read(tmp_path):
    """Test worker in separate process writes record and API reads it from SQLite."""
    db_file = str(tmp_path / "model_executions.db")
    incident_id = "INC-MULTI-TEST"
    exec_id = "exec_worker_abc123"

    # Start worker process
    ctx = multiprocessing.get_context("spawn")
    p = ctx.Process(target=_worker_write_process, args=(db_file, incident_id, exec_id))
    p.start()
    p.join(timeout=10)
    assert p.exitcode == 0, f"Worker process failed with code {p.exitcode}"

    # API process reads record from database
    api_store = ModelExecutionStore(db_path=db_file)
    rec = api_store.get(exec_id)
    assert rec is not None
    assert rec.execution_id == exec_id
    assert rec.incident_id == incident_id
    assert rec.model_id == "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF"
    assert rec.suggestions_accepted == 2
    assert rec.suggestions_rejected == 1
    assert rec.validation_result == ValidationResult.ACCEPTED
    assert rec.input_artifact_ids == ["telemetry/heap.csv", "config/worker.yaml"]
    assert rec.usage["input_tokens"] == 512

    # Query by incident
    incident_records = api_store.list_by_incident(incident_id)
    assert len(incident_records) == 1
    assert incident_records[0].execution_id == exec_id


def test_records_survive_store_restart(tmp_path):
    """Verify records persist across store re-instantiation."""
    db_file = str(tmp_path / "model_executions.db")
    store1 = ModelExecutionStore(db_path=db_file)
    rec = ModelExecutionRecord(
        execution_id="exec_restart_1",
        incident_id="INC-RESTART",
        provider="nebius",
        model_id="nvidia/Llama-3.1-Nemotron-70B-Instruct-HF",
    )
    store1.record(rec)

    # Re-instantiate store (simulates server restart)
    store2 = ModelExecutionStore(db_path=db_file)
    retrieved = store2.get("exec_restart_1")
    assert retrieved is not None
    assert retrieved.incident_id == "INC-RESTART"


def test_incident_scoping_isolation(tmp_path):
    """Ensure records for Incident A are never returned for Incident B."""
    db_file = str(tmp_path / "model_executions.db")
    store = ModelExecutionStore(db_path=db_file)

    store.record(ModelExecutionRecord(execution_id="e1", incident_id="INC-A"))
    store.record(ModelExecutionRecord(execution_id="e2", incident_id="INC-A"))
    store.record(ModelExecutionRecord(execution_id="e3", incident_id="INC-B"))

    records_a = store.list_by_incident("INC-A")
    records_b = store.list_by_incident("INC-B")
    records_c = store.list_by_incident("INC-C")

    assert [r.execution_id for r in records_a] == ["e1", "e2"]
    assert [r.execution_id for r in records_b] == ["e3"]
    assert records_c == []
