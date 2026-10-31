"""
Sanitized provider execution records and database-backed persistent store for Cauveris Model Gateway.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .enums import ProviderState, ValidationResult

logger = logging.getLogger(__name__)


class ModelExecutionRecord(BaseModel):
    """
    Sanitized record of an individual model provider task execution.
    Never contains API keys, auth headers, database passwords, or unredacted secrets.
    """
    execution_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique execution UUID"
    )
    incident_id: str = Field(..., description="Target incident ID")
    job_id: Optional[str] = Field(None, description="Associated pipeline job ID if present")
    owner_user_id: Optional[str] = Field(None, description="Owner user ID for tenant scoping")
    owner_org_id: Optional[str] = Field(None, description="Owner organization ID for tenant scoping")
    provider: str = Field("nebius", description="Provider ID (nebius, local)")
    provider_state: ProviderState = Field(
        ProviderState.NEBIUS_NVIDIA_ACTIVE, description="State of the provider during execution"
    )
    model_id: str = Field(
        "nvidia/Nemotron-3_5-Lightning",
        description="Exact model ID used (e.g. nvidia/Nemotron-3_5-Lightning)",
    )
    endpoint_mode: str = Field("hosted", description="Endpoint mode: hosted | local")
    task_id: str = Field("HYPOTHESIS_PROPOSAL", description="Bounded task identifier (e.g. HYPOTHESIS_PROPOSAL)")
    task_version: str = Field("1.0", description="Version of the task definition")
    prompt_template_version: str = Field("1.0", description="Version of the prompt template")
    structured_output_schema_version: str = Field(
        "1.0", description="Version of the structured output schema"
    )
    input_artifact_ids: List[str] = Field(default_factory=list, description="Referenced artifact IDs")
    input_record_ids: List[str] = Field(default_factory=list, description="Referenced record/event IDs")
    redaction_count: int = Field(0, description="Number of sensitive tokens redacted from prompt")
    request_id: Optional[str] = Field(None, description="Upstream provider request ID")
    started_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 start timestamp",
    )
    completed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 completion timestamp",
    )
    latency_ms: float = Field(0.0, description="Round-trip latency in milliseconds")
    response_hash: str = Field("", description="SHA-256 digest of sanitized model response")
    suggestions_received: int = Field(0, description="Total proposals/suggestions emitted by model")
    suggestions_accepted: int = Field(0, description="Suggestions verified and accepted by deterministic validator")
    suggestions_rejected: int = Field(0, description="Suggestions rejected by deterministic validator")
    validation_result: ValidationResult = Field(
        ValidationResult.ACCEPTED, description="Outcome of deterministic validation"
    )
    fallback_used: bool = Field(False, description="Whether deterministic fallback was used instead")
    error_code: Optional[str] = Field(None, description="Standardized error code if failed")
    usage: Dict[str, Optional[int]] = Field(
        default_factory=lambda: {"input_tokens": None, "output_tokens": None},
        description="Token usage stats",
    )
    accepted_suggestions: List[Dict[str, Any]] = Field(
        default_factory=list, description="Accepted suggestions with deterministic rationale"
    )
    rejected_suggestions: List[Dict[str, Any]] = Field(
        default_factory=list, description="Rejected suggestions with reasons"
    )
    rejection_reasons: List[str] = Field(
        default_factory=list, description="Summary list of rejection reasons"
    )
    cached: bool = Field(False, description="Whether response was returned from input-hash cache")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 creation timestamp",
    )

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class ModelExecutionStore:
    """
    Database-backed persistent and incident-scoped store for execution records.
    Supports multi-process access across API and worker instances, restarts, and replica pools.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        if not db_path:
            try:
                from cauveris.config import get_settings
                db_path = get_settings().model_execution_db_path
            except Exception:
                db_path = os.getenv("CAUVERIS_MODEL_EXECUTION_DB_PATH", "data/model_executions.db")
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db_path), timeout=30.0)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=5000")
        return con

    def _init_db(self) -> None:
        with self._lock:
            with self._get_connection() as con:
                con.executescript("""
                CREATE TABLE IF NOT EXISTS model_executions (
                    execution_id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL,
                    job_id TEXT,
                    owner_user_id TEXT,
                    owner_org_id TEXT,
                    provider TEXT NOT NULL,
                    provider_state TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    endpoint_mode TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    task_version TEXT NOT NULL,
                    prompt_template_version TEXT NOT NULL,
                    structured_output_schema_version TEXT NOT NULL,
                    input_artifact_ids TEXT NOT NULL,
                    input_record_ids TEXT NOT NULL,
                    redaction_count INTEGER NOT NULL DEFAULT 0,
                    request_id TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    response_hash TEXT NOT NULL,
                    suggestions_received INTEGER NOT NULL DEFAULT 0,
                    suggestions_accepted INTEGER NOT NULL DEFAULT 0,
                    suggestions_rejected INTEGER NOT NULL DEFAULT 0,
                    validation_result TEXT NOT NULL,
                    fallback_used INTEGER NOT NULL DEFAULT 0,
                    error_code TEXT,
                    usage TEXT NOT NULL,
                    accepted_suggestions TEXT NOT NULL,
                    rejected_suggestions TEXT NOT NULL,
                    rejection_reasons TEXT NOT NULL,
                    cached INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_model_exec_incident ON model_executions(incident_id);
                CREATE INDEX IF NOT EXISTS idx_model_exec_created_at ON model_executions(created_at);
                """)

    def _row_to_record(self, row: sqlite3.Row) -> ModelExecutionRecord:
        return ModelExecutionRecord(
            execution_id=row["execution_id"],
            incident_id=row["incident_id"],
            job_id=row["job_id"],
            owner_user_id=row["owner_user_id"],
            owner_org_id=row["owner_org_id"],
            provider=row["provider"],
            provider_state=ProviderState(row["provider_state"]),
            model_id=row["model_id"],
            endpoint_mode=row["endpoint_mode"],
            task_id=row["task_id"],
            task_version=row["task_version"],
            prompt_template_version=row["prompt_template_version"],
            structured_output_schema_version=row["structured_output_schema_version"],
            input_artifact_ids=json.loads(row["input_artifact_ids"]),
            input_record_ids=json.loads(row["input_record_ids"]),
            redaction_count=row["redaction_count"],
            request_id=row["request_id"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            latency_ms=row["latency_ms"],
            response_hash=row["response_hash"],
            suggestions_received=row["suggestions_received"],
            suggestions_accepted=row["suggestions_accepted"],
            suggestions_rejected=row["suggestions_rejected"],
            validation_result=ValidationResult(row["validation_result"]),
            fallback_used=bool(row["fallback_used"]),
            error_code=row["error_code"],
            usage=json.loads(row["usage"]),
            accepted_suggestions=json.loads(row["accepted_suggestions"]),
            rejected_suggestions=json.loads(row["rejected_suggestions"]),
            rejection_reasons=json.loads(row["rejection_reasons"]),
            cached=bool(row["cached"]),
            created_at=row["created_at"],
        )

    def record(self, record: ModelExecutionRecord) -> None:
        with self._lock:
            with self._get_connection() as con:
                con.execute(
                    """
                    INSERT OR REPLACE INTO model_executions (
                        execution_id, incident_id, job_id, owner_user_id, owner_org_id,
                        provider, provider_state, model_id, endpoint_mode, task_id,
                        task_version, prompt_template_version, structured_output_schema_version,
                        input_artifact_ids, input_record_ids, redaction_count, request_id,
                        started_at, completed_at, latency_ms, response_hash, suggestions_received,
                        suggestions_accepted, suggestions_rejected, validation_result, fallback_used,
                        error_code, usage, accepted_suggestions, rejected_suggestions, rejection_reasons,
                        cached, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.execution_id,
                        record.incident_id,
                        record.job_id,
                        record.owner_user_id,
                        record.owner_org_id,
                        record.provider,
                        record.provider_state.value if hasattr(record.provider_state, "value") else str(record.provider_state),
                        record.model_id,
                        record.endpoint_mode,
                        record.task_id,
                        record.task_version,
                        record.prompt_template_version,
                        record.structured_output_schema_version,
                        json.dumps(record.input_artifact_ids),
                        json.dumps(record.input_record_ids),
                        record.redaction_count,
                        record.request_id,
                        record.started_at,
                        record.completed_at,
                        record.latency_ms,
                        record.response_hash,
                        record.suggestions_received,
                        record.suggestions_accepted,
                        record.suggestions_rejected,
                        record.validation_result.value if hasattr(record.validation_result, "value") else str(record.validation_result),
                        1 if record.fallback_used else 0,
                        record.error_code,
                        json.dumps(record.usage),
                        json.dumps(record.accepted_suggestions),
                        json.dumps(record.rejected_suggestions),
                        json.dumps(record.rejection_reasons),
                        1 if record.cached else 0,
                        record.created_at,
                    ),
                )

    def add(self, record: ModelExecutionRecord) -> None:
        self.record(record)

    def get(self, execution_id: str) -> Optional[ModelExecutionRecord]:
        with self._get_connection() as con:
            cur = con.execute("SELECT * FROM model_executions WHERE execution_id = ?", (execution_id,))
            row = cur.fetchone()
            return self._row_to_record(row) if row else None

    def get_by_id(self, execution_id: str) -> Optional[ModelExecutionRecord]:
        return self.get(execution_id)

    def list_by_incident(self, incident_id: str) -> List[ModelExecutionRecord]:
        with self._get_connection() as con:
            cur = con.execute(
                "SELECT * FROM model_executions WHERE incident_id = ? ORDER BY created_at ASC",
                (incident_id,),
            )
            return [self._row_to_record(row) for row in cur.fetchall()]

    def get_by_incident(self, incident_id: str) -> List[ModelExecutionRecord]:
        return self.list_by_incident(incident_id)

    def clear(self) -> None:
        with self._lock:
            with self._get_connection() as con:
                con.execute("DELETE FROM model_executions")

    def cleanup_old_records(self, max_age_days: int = 30) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
        with self._lock:
            with self._get_connection() as con:
                cur = con.execute("DELETE FROM model_executions WHERE created_at < ?", (cutoff,))
                return cur.rowcount


_global_execution_store: Optional[ModelExecutionStore] = None


def get_execution_store(db_path: Optional[str] = None) -> ModelExecutionStore:
    """Get singleton execution store with persistent SQLite backend."""
    global _global_execution_store
    if db_path is not None:
        _global_execution_store = ModelExecutionStore(db_path=db_path)
        return _global_execution_store
    if _global_execution_store is None:
        _global_execution_store = ModelExecutionStore()
    return _global_execution_store
