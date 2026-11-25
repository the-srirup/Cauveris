"""
Restore a ``cauveris-session/v1`` archive into a fresh, resumable workspace.

The import path is the mirror image of the builder: it verifies the archive,
materializes the evidence bundle into the evidence store, restores the
pipeline history, and re-registers the incident so the operator lands on a
dashboard that looks like the one they left.

The honesty rule governs this module.  The restore reports what the archive
*contained*.  A session with no report comes back with no report and says so
in the summary — it is never presented as an incident that was investigated
and found clean.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from cauveris.config import get_settings
from cauveris.schemas.base import StatusLabel
from cauveris.schemas.incident import Incident
from cauveris.sessions.manifest import parse_manifest
from cauveris.sessions.models import (
    SESSION_ARTIFACTS_DIR,
    SESSION_EVENTS_PATH,
    SESSION_MANIFEST_FORMAT,
    SESSION_MANIFEST_PATH,
    SESSION_PACKAGES_DIR,
    SESSION_REPORT_PATH,
    SESSION_STAGES_PATH,
    SessionChecksumError,
    SessionFormatError,
    SessionImportSummary,
    verify_checksum,
)

logger = logging.getLogger(__name__)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_tree(source: Path, destination: Path) -> int:
    """Copy every file under ``source`` into ``destination``; return the count."""
    if not source.exists():
        return 0
    count = 0
    for file_path in sorted(source.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(source)
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, target)
        count += 1
    return count


def _safe_bundle_component(value: str) -> str:
    """A filesystem-safe incident id component."""
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(value))[:64] or "imported"


class SessionRestorer:
    """Restores a session archive into the evidence and report stores."""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()

    # ------------------------------------------------------------- internals

    def _verify_checksums(self, staging: Path, manifest) -> None:
        """
        Verify every file the manifest declares.

        The manifest's ``files`` table is authoritative.  A missing member or a
        digest mismatch is fatal: a session that claims to carry evidence it
        does not carry is worse than no session at all.
        """
        for entry in manifest.files:
            member = staging / entry.path
            if not member.is_file():
                raise SessionChecksumError(
                    f"Session archive is missing a declared member: {entry.path}"
                )
            actual = _sha256_file(member)
            if not verify_checksum(entry.sha256, actual):
                raise SessionChecksumError(
                    f"Checksum mismatch for {entry.path}: "
                    f"expected {entry.sha256}, got {actual}"
                )

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Could not read session member {path}: {exc}")
            return {}
        return data if isinstance(data, dict) else {}

    # --------------------------------------------------------------- restore

    def restore(
        self,
        archive_path: Path,
        staging_dir: Path,
        *,
        user_id: str = "",
        org_id: str = "",
        incident_id: Optional[str] = None,
    ) -> SessionImportSummary:
        """
        Restore a session archive.

        Args:
            archive_path: The uploaded ``.zip`` on disk.
            staging_dir: A scratch directory the archive is expanded into.
            user_id: The operator importing the session; becomes the owner.
            org_id: The operator's organisation.
            incident_id: An explicit id for the restored incident; a fresh one
                is minted otherwise.  The original id is preserved in the
                manifest and the summary.

        Returns:
            A :class:`SessionImportSummary` describing exactly what came back.
        """
        from cauveris.ingestion.controller import extract_zip_safely

        staging_dir.mkdir(parents=True, exist_ok=True)
        # The extraction helper enforces the archive policy (path traversal,
        # symlinks, member count, size caps) — the same policy an evidence
        # upload goes through.  No second extractor is written here.
        extract_zip_safely(archive_path, staging_dir, self.settings)

        manifest_file = staging_dir / SESSION_MANIFEST_PATH
        if not manifest_file.is_file():
            raise SessionFormatError(
                f"Archive is not a {SESSION_MANIFEST_FORMAT} package "
                f"({SESSION_MANIFEST_PATH} is missing)"
            )

        manifest = parse_manifest(manifest_file.read_bytes())
        if manifest.format != SESSION_MANIFEST_FORMAT:
            raise SessionFormatError(
                f"Archive declares format {manifest.format!r}; "
                f"expected {SESSION_MANIFEST_FORMAT!r}"
            )

        self._verify_checksums(staging_dir, manifest)

        source_incident_id = manifest.incident_id or "unknown"
        new_incident_id = incident_id or f"CAU-{uuid.uuid4().hex[:8].upper()}"

        restored: List[str] = []
        missing: List[str] = []
        warnings: List[str] = []

        # --- evidence bundle ---------------------------------------------
        bundle_root = Path(self.settings.evidence_store_path) / new_incident_id
        artifacts_dir = staging_dir / SESSION_ARTIFACTS_DIR
        evidence_count = _copy_tree(artifacts_dir, bundle_root)
        if evidence_count:
            restored.append("evidence")
        else:
            missing.append("evidence")
            if artifacts_dir.exists():
                warnings.append("The session carried an evidence directory with no files.")

        # --- report --------------------------------------------------------
        report_source = staging_dir / SESSION_REPORT_PATH
        report_present = report_source.is_file()
        if report_present:
            report_dir = Path(self.settings.report_store_path) / new_incident_id
            report_dir.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(report_source, report_dir / "incident_report.json")
                restored.append("report")
            except OSError as exc:
                warnings.append(f"Could not restore the incident report: {exc}")
                report_present = False
                missing.append("report")
        else:
            missing.append("report")

        # --- repair packages ----------------------------------------------
        packages_dir = staging_dir / SESSION_PACKAGES_DIR
        package_count = 0
        if packages_dir.is_dir():
            archives_dir = Path(self.settings.report_store_path) / "packaging" / "archives"
            archives_dir.mkdir(parents=True, exist_ok=True)
            for package in sorted(packages_dir.glob("*.zip")):
                try:
                    shutil.copy2(package, archives_dir / package.name)
                    package_count += 1
                except OSError as exc:
                    warnings.append(f"Could not restore repair package {package.name}: {exc}")
            if package_count:
                restored.append("repair_packages")
            else:
                missing.append("repair_packages")
        else:
            missing.append("repair_packages")

        # --- incident + manifest -------------------------------------------
        bundle_manifest = self._bundle_manifest(manifest, new_incident_id)
        try:
            (bundle_root / "manifest.yaml").write_text(
                yaml.safe_dump(bundle_manifest, sort_keys=False, default_flow_style=False),
                encoding="utf-8",
            )
        except OSError as exc:
            warnings.append(f"Could not write the restored bundle manifest: {exc}")

        if user_id or org_id:
            try:
                (bundle_root / ".cauveris-owner.json").write_text(
                    json.dumps(
                        {
                            k: v
                            for k, v in (
                                ("owner_user_id", user_id or None),
                                ("owner_org_id", org_id or None),
                            )
                            if v
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except OSError as exc:
                warnings.append(f"Could not persist the owner sidecar: {exc}")

        metadata = {
            key: manifest_value
            for key, manifest_value in {
                "severity": manifest.severity,
                "category": manifest.category,
                "environment": manifest.environment,
                "tags": manifest.tags,
                "intake_method": manifest.intake_method,
                "approximate_time": manifest.approximate_time,
            }.items()
            if manifest_value not in (None, [], "")
        }
        if metadata:
            try:
                (bundle_root / ".cauveris-incident.json").write_text(
                    json.dumps(metadata, indent=2, default=str), encoding="utf-8"
                )
            except OSError as exc:
                warnings.append(f"Could not persist the incident metadata sidecar: {exc}")

        incident = Incident(
            id=new_incident_id,
            title=manifest.title or f"Incident {new_incident_id}",
            description=manifest.description or "Restored from a saved session package",
            system_name=manifest.system_name or "unknown-system",
            approximate_time=manifest.approximate_time,
            manifest=bundle_manifest,
            bundle_path=str(bundle_root),
            status=StatusLabel.OBSERVED,
            is_demonstration=bool(manifest.is_demonstration),
        )
        incident.apply_metadata_snapshot(metadata)
        incident.apply_metadata_to_manifest()
        incident._owner_user_id = user_id or None
        incident._owner_org_id = org_id or None

        # --- pipeline history -----------------------------------------------
        stage_count = 0
        event_count = 0
        stages_doc = self._read_json(staging_dir / SESSION_STAGES_PATH)
        events_doc = self._read_json(staging_dir / SESSION_EVENTS_PATH)
        stage_records = stages_doc.get("stages") or []
        event_records = events_doc.get("events") or []
        try:
            from cauveris.state_machine.persistence import PipelinePersistenceStore

            store = PipelinePersistenceStore.get_instance()
            # The canonical 18-stage skeleton is created without logging a
            # PIPELINE_INITIALIZED event: the archive's own event log is the
            # record of what happened, and a synthetic event would make a
            # restored investigation look different from the original.
            store.initialize_incident_stages(
                new_incident_id, overwrite=True, record_event=False
            )
            stage_count = store.import_stages(new_incident_id, stage_records)
            event_count = store.import_events(new_incident_id, event_records)
            restored.append("pipeline_history")
        except Exception as exc:
            logger.warning(f"Could not restore pipeline history: {exc}")
            warnings.append(f"Pipeline history could not be restored: {exc}")
            missing.append("pipeline_history")

        # --- register in the console ------------------------------------------
        self._register(incident, manifest)

        return SessionImportSummary(
            incident_id=new_incident_id,
            title=incident.title,
            restored=restored,
            missing=missing,
            pipeline_state=manifest.pipeline_state,
            active_stage_id=manifest.active_stage_id,
            report_present=report_present,
            stage_count=stage_count,
            event_count=event_count,
            repair_package_count=package_count,
            evidence_file_count=evidence_count,
            source_incident_id=source_incident_id,
            warnings=warnings,
        )

    # -------------------------------------------------------------- helpers

    @staticmethod
    def _bundle_manifest(manifest, new_incident_id: str) -> Dict[str, Any]:
        """The canonical ``manifest.yaml`` written into the restored bundle."""
        return {
            "incident_id": new_incident_id,
            "title": manifest.title,
            "description": manifest.description,
            "system_name": manifest.system_name,
            "approximate_time": manifest.approximate_time,
            "severity": manifest.severity,
            "category": manifest.category,
            "environment": manifest.environment,
            "tags": list(manifest.tags or []),
            "intake_method": manifest.intake_method,
            "is_demonstration": manifest.is_demonstration,
            "source_session_id": manifest.session_id,
            "source_incident_id": manifest.incident_id,
            "source_pipeline_state": manifest.pipeline_state,
            "source_active_stage_id": manifest.active_stage_id,
            "restored_at": datetime.now(timezone.utc).isoformat(),
            "session_format": manifest.format,
        }

    @staticmethod
    def _register(incident: Incident, manifest) -> None:
        """Put the restored incident into the console's live registries."""
        try:
            from cauveris.api.main import incidents, pipeline_progress, pipeline_tasks
            from cauveris.state_machine.orchestrator import (
                PipelineContext,
                PipelineOrchestrator,
                WorkflowStatus,
            )

            incidents[incident.id] = incident

            orch = PipelineOrchestrator()
            orch.context = PipelineContext(incident=incident)
            orch.current_state = manifest.pipeline_state or "IDLE"
            orch.active_stage_id = manifest.active_stage_id
            try:
                orch.workflow_status = WorkflowStatus(manifest.pipeline_state)
            except (ValueError, TypeError):
                # A captured state that is not a member of the enum (or is a
                # pipeline state rather than a workflow status) is preserved
                # verbatim in ``current_state`` and simply not mirrored into
                # ``workflow_status``.
                pass
            pipeline_tasks[incident.id] = orch
            pipeline_progress[incident.id] = orch.get_pipeline_summary()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"Could not register the restored incident: {exc}")


def restore_session(
    archive_path: Path,
    staging_dir: Path,
    *,
    user_id: str = "",
    org_id: str = "",
    incident_id: Optional[str] = None,
    settings=None,
) -> SessionImportSummary:
    """Convenience wrapper around :class:`SessionRestorer`."""
    restorer = SessionRestorer(settings)
    return restorer.restore(
        archive_path,
        staging_dir,
        user_id=user_id,
        org_id=org_id,
        incident_id=incident_id,
    )
