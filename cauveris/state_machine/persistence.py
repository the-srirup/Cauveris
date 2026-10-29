"""
Pipeline stage and event persistence store for Cauveris.
Stores all 18 pipeline stages and provides ordered, sequence-numbered events
for SSE streaming, reconnect, deduplication, and safe retry.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import threading
import logging

from cauveris.config import get_settings

logger = logging.getLogger(__name__)

CANONICAL_STAGE_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "id": "upload_accepted",
        "name": "Upload accepted",
        "description": "Evidence bundle archive received and initial upload integrity validated",
        "required": True,
        "depends_on": [],
    },
    {
        "id": "archive_validated",
        "name": "Archive validated",
        "description": "ZIP archive decompressed safely, checksums calculated, and path constraints checked",
        "required": True,
        "depends_on": ["upload_accepted"],
    },
    {
        "id": "artifacts_inventoried",
        "name": "Artifacts inventoried",
        "description": "Artifacts indexed, classified, and capability constraints verified",
        "required": True,
        "depends_on": ["archive_validated"],
    },
    {
        "id": "evidence_extracted",
        "name": "Evidence extracted",
        "description": "Evidence records parsed, schemas validated, and secrets redacted",
        "required": True,
        "depends_on": ["artifacts_inventoried"],
    },
    {
        "id": "timeline_normalized",
        "name": "Timeline normalized",
        "description": "Multi-lane logs, traces, and metrics aligned to monotonic timeline",
        "required": True,
        "depends_on": ["evidence_extracted"],
    },
    {
        "id": "invariants_resolved",
        "name": "Invariants resolved",
        "description": "Safety and physical system invariants resolved and normalized",
        "required": True,
        "depends_on": ["timeline_normalized"],
    },
    {
        "id": "model_assistance",
        "name": "Model assistance",
        "description": "Model reasoning queried via bounded provider with secret scrubbing",
        "required": False,
        "depends_on": ["invariants_resolved"],
    },
    {
        "id": "model_output_validation",
        "name": "Model-output validation",
        "description": "Deterministic validation of model proposals against schema and grounding criteria",
        "required": False,
        "depends_on": ["model_assistance"],
    },
    {
        "id": "hypotheses_generated",
        "name": "Hypotheses generated",
        "description": "Falsifiable root-cause hypotheses formulated with causal claims",
        "required": True,
        "depends_on": ["invariants_resolved"],
    },
    {
        "id": "capability_planning",
        "name": "Capability planning",
        "description": "Physical AI capability boundaries evaluated and sandboxes planned",
        "required": True,
        "depends_on": ["hypotheses_generated"],
    },
    {
        "id": "baseline_calculation",
        "name": "Baseline calculation",
        "description": "Digital twin baseline executed to reproduce the observed failure",
        "required": True,
        "depends_on": ["capability_planning"],
    },
    {
        "id": "intervention_calculation",
        "name": "Intervention calculation",
        "description": "Counterfactual repair interventions evaluated under calibrated conditions",
        "required": True,
        "depends_on": ["baseline_calculation"],
    },
    {
        "id": "patch_generation",
        "name": "Patch generation",
        "description": "Parser-aware configuration and source code patches generated",
        "required": True,
        "depends_on": ["intervention_calculation"],
    },
    {
        "id": "staged_patch_validation",
        "name": "Staged patch validation",
        "description": "Synthesized diff staged and syntax/structure validated against target files",
        "required": True,
        "depends_on": ["patch_generation"],
    },
    {
        "id": "verification",
        "name": "Verification",
        "description": "9-point formal invariant checks and atomic verification performed",
        "required": True,
        "depends_on": ["staged_patch_validation"],
    },
    {
        "id": "report_generation",
        "name": "Report generation",
        "description": "Audit report compiled with cryptographic hashes and execution traces",
        "required": False,
        "depends_on": ["verification"],
    },
    {
        "id": "repair_package_generation",
        "name": "Repair-package generation",
        "description": "Self-contained reversible installer package built with rollback artifacts",
        "required": True,
        "depends_on": ["verification"],
    },
    {
        "id": "package_ready",
        "name": "Package ready",
        "description": "Repair package validated and staged for authorized browser download",
        "required": True,
        "depends_on": ["repair_package_generation"],
    },
]


@dataclass
class PipelineStageRecord:
    """Persistent representation of a single pipeline stage."""

    incident_id: str
    stage_id: str
    name: str
    status: str = "NOT_STARTED"
    job_id: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: Optional[float] = None
    input_references: List[str] = field(default_factory=list)
    output_references: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error_code: Optional[str] = None
    error: Optional[str] = None
    retryability: bool = True
    attempt_count: int = 0
    required: bool = True
    depends_on: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "job_id": self.job_id,
            "id": self.stage_id,
            "stage_id": self.stage_id,
            "name": self.name,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "input_references": self.input_references,
            "output_references": self.output_references,
            "warnings": self.warnings,
            "error_code": self.error_code,
            "error": self.error,
            "retryability": self.retryability,
            "attempt_count": self.attempt_count,
            "required": self.required,
            "depends_on": self.depends_on,
            "details": self.details,
            "updated_at": self.updated_at,
        }


class PipelinePersistenceStore:
    """Thread-safe SQLite store for pipeline stage states and events."""

    _instance: Optional[PipelinePersistenceStore] = None
    _lock = threading.Lock()

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            settings = get_settings()
            db_path = getattr(settings, "pipeline_db_path", "data/pipeline_stages.db")
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @classmethod
    def get_instance(cls, db_path: Optional[str] = None) -> PipelinePersistenceStore:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(db_path=db_path)
            return cls._instance

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pipeline_stages (
                    incident_id TEXT NOT NULL,
                    stage_id TEXT NOT NULL,
                    job_id TEXT,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    required INTEGER NOT NULL DEFAULT 1,
                    depends_on TEXT NOT NULL DEFAULT '[]',
                    started_at TEXT,
                    completed_at TEXT,
                    duration_ms REAL,
                    input_references TEXT NOT NULL DEFAULT '[]',
                    output_references TEXT NOT NULL DEFAULT '[]',
                    warnings TEXT NOT NULL DEFAULT '[]',
                    error_code TEXT,
                    error TEXT,
                    retryability INTEGER NOT NULL DEFAULT 1,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    details TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (incident_id, stage_id)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_pipeline_stages_incident
                ON pipeline_stages(incident_id)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pipeline_events (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_id TEXT NOT NULL,
                    job_id TEXT,
                    event_type TEXT NOT NULL,
                    stage_id TEXT,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_pipeline_events_incident_seq
                ON pipeline_events(incident_id, sequence_id)
                """
            )
            conn.commit()

    def initialize_incident_stages(
        self, incident_id: str, job_id: Optional[str] = None, overwrite: bool = False
    ) -> List[PipelineStageRecord]:
        """Initialize the 18 canonical stages for an incident."""
        now = datetime.now(timezone.utc).isoformat()
        records: List[PipelineStageRecord] = []

        with self._get_connection() as conn:
            for s in CANONICAL_STAGE_DEFINITIONS:
                existing = conn.execute(
                    "SELECT * FROM pipeline_stages WHERE incident_id = ? AND stage_id = ?",
                    (incident_id, s["id"]),
                ).fetchone()

                if existing and not overwrite:
                    records.append(self._row_to_record(existing))
                    continue

                rec = PipelineStageRecord(
                    incident_id=incident_id,
                    stage_id=s["id"],
                    name=s["name"],
                    status="NOT_STARTED",
                    job_id=job_id,
                    required=s["required"],
                    depends_on=s["depends_on"],
                    retryability=True,
                    attempt_count=0,
                    updated_at=now,
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO pipeline_stages (
                        incident_id, stage_id, job_id, name, status, required, depends_on,
                        started_at, completed_at, duration_ms, input_references, output_references,
                        warnings, error_code, error, retryability, attempt_count, details, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rec.incident_id,
                        rec.stage_id,
                        rec.job_id,
                        rec.name,
                        rec.status,
                        1 if rec.required else 0,
                        json.dumps(rec.depends_on),
                        rec.started_at,
                        rec.completed_at,
                        rec.duration_ms,
                        json.dumps(rec.input_references),
                        json.dumps(rec.output_references),
                        json.dumps(rec.warnings),
                        rec.error_code,
                        rec.error,
                        1 if rec.retryability else 0,
                        rec.attempt_count,
                        json.dumps(rec.details),
                        rec.updated_at,
                    ),
                )
                records.append(rec)

            conn.commit()

        self.record_event(
            incident_id=incident_id,
            event_type="PIPELINE_INITIALIZED",
            stage_id=None,
            payload={"stages_count": len(records), "status": "NOT_STARTED"},
            job_id=job_id,
        )
        return records

    def get_stage(self, incident_id: str, stage_id: str) -> Optional[PipelineStageRecord]:
        """Fetch a specific stage record."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM pipeline_stages WHERE incident_id = ? AND stage_id = ?",
                (incident_id, stage_id),
            ).fetchone()
            if row:
                return self._row_to_record(row)
        return None

    def get_stages(self, incident_id: str) -> List[PipelineStageRecord]:
        """Fetch all stages for an incident in canonical order."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM pipeline_stages WHERE incident_id = ?",
                (incident_id,),
            ).fetchall()
            row_map = {row["stage_id"]: self._row_to_record(row) for row in rows}

            # Return in canonical order if defined, followed by any custom stages
            ordered: List[PipelineStageRecord] = []
            for s in CANONICAL_STAGE_DEFINITIONS:
                if s["id"] in row_map:
                    ordered.append(row_map.pop(s["id"]))
            ordered.extend(row_map.values())
            return ordered

    def update_stage(self, record: PipelineStageRecord) -> int:
        """Update a stage and record an event with sequence ID."""
        now = datetime.now(timezone.utc).isoformat()
        record.updated_at = now

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO pipeline_stages (
                    incident_id, stage_id, job_id, name, status, required, depends_on,
                    started_at, completed_at, duration_ms, input_references, output_references,
                    warnings, error_code, error, retryability, attempt_count, details, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.incident_id,
                    record.stage_id,
                    record.job_id,
                    record.name,
                    record.status,
                    1 if record.required else 0,
                    json.dumps(record.depends_on),
                    record.started_at,
                    record.completed_at,
                    record.duration_ms,
                    json.dumps(record.input_references),
                    json.dumps(record.output_references),
                    json.dumps(record.warnings),
                    record.error_code,
                    record.error,
                    1 if record.retryability else 0,
                    record.attempt_count,
                    json.dumps(record.details),
                    record.updated_at,
                ),
            )
            conn.commit()

        return self.record_event(
            incident_id=record.incident_id,
            event_type="STAGE_UPDATED",
            stage_id=record.stage_id,
            payload=record.to_dict(),
            job_id=record.job_id,
        )

    def record_event(
        self,
        incident_id: str,
        event_type: str,
        stage_id: Optional[str],
        payload: Dict[str, Any],
        job_id: Optional[str] = None,
    ) -> int:
        """Record an event with auto-incrementing sequence ID."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO pipeline_events (incident_id, job_id, event_type, stage_id, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (incident_id, job_id, event_type, stage_id, json.dumps(payload), now),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def get_events(
        self, incident_id: str, after_sequence_id: Optional[int] = None, limit: int = 500
    ) -> List[Dict[str, Any]]:
        """Fetch ordered events for an incident, optionally after a sequence ID."""
        with self._get_connection() as conn:
            if after_sequence_id is not None:
                rows = conn.execute(
                    """
                    SELECT * FROM pipeline_events
                    WHERE incident_id = ? AND sequence_id > ?
                    ORDER BY sequence_id ASC LIMIT ?
                    """,
                    (incident_id, after_sequence_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM pipeline_events
                    WHERE incident_id = ?
                    ORDER BY sequence_id ASC LIMIT ?
                    """,
                    (incident_id, limit),
                ).fetchall()

            events = []
            for r in rows:
                try:
                    payload = json.loads(r["payload"])
                except Exception:
                    payload = {}
                events.append(
                    {
                        "sequence_id": r["sequence_id"],
                        "incident_id": r["incident_id"],
                        "job_id": r["job_id"],
                        "event_type": r["event_type"],
                        "stage_id": r["stage_id"],
                        "payload": payload,
                        "created_at": r["created_at"],
                    }
                )
            return events

    def get_latest_sequence_id(self, incident_id: str) -> int:
        """Get the highest sequence ID emitted for this incident."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT MAX(sequence_id) as max_seq FROM pipeline_events WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
            if row and row["max_seq"] is not None:
                return int(row["max_seq"])
        return 0

    def reset_stage_for_retry(self, incident_id: str, stage_id: str) -> bool:
        """Safely reset a failed or blocked stage for retry."""
        stage = self.get_stage(incident_id, stage_id)
        if not stage or not stage.retryability:
            return False

        stage.status = "QUEUED"
        stage.error = None
        stage.error_code = None
        stage.attempt_count += 1
        stage.started_at = None
        stage.completed_at = None
        stage.duration_ms = None
        self.update_stage(stage)
        return True

    def cancel_incident_stages(self, incident_id: str, reason: str = "Investigation cancelled by operator") -> None:
        """Mark active stages cancelled and downstream stages blocked."""
        stages = self.get_stages(incident_id)
        now = datetime.now(timezone.utc).isoformat()

        for s in stages:
            if s.status in ("RUNNING", "QUEUED"):
                s.status = "CANCELLED"
                s.error = reason
                s.completed_at = now
                self.update_stage(s)
            elif s.status in ("NOT_STARTED", "PENDING"):
                s.status = "BLOCKED"
                s.error = "Cancelled prior to execution"
                self.update_stage(s)

        self.record_event(
            incident_id=incident_id,
            event_type="PIPELINE_CANCELLED",
            stage_id=None,
            payload={"reason": reason, "cancelled_at": now},
        )

    def _row_to_record(self, row: sqlite3.Row) -> PipelineStageRecord:
        try:
            depends_on = json.loads(row["depends_on"])
        except Exception:
            depends_on = []
        try:
            input_references = json.loads(row["input_references"])
        except Exception:
            input_references = []
        try:
            output_references = json.loads(row["output_references"])
        except Exception:
            output_references = []
        try:
            warnings = json.loads(row["warnings"])
        except Exception:
            warnings = []
        try:
            details = json.loads(row["details"])
        except Exception:
            details = {}

        return PipelineStageRecord(
            incident_id=row["incident_id"],
            stage_id=row["stage_id"],
            job_id=row["job_id"],
            name=row["name"],
            status=row["status"],
            required=bool(row["required"]),
            depends_on=depends_on,
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            duration_ms=row["duration_ms"],
            input_references=input_references,
            output_references=output_references,
            warnings=warnings,
            error_code=row["error_code"],
            error=row["error"],
            retryability=bool(row["retryability"]),
            attempt_count=int(row["attempt_count"] or 0),
            details=details,
            updated_at=row["updated_at"],
        )
