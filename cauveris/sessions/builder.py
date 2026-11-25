"""
Assemble a ``cauveris-session/v1`` archive from live investigation state.

The builder captures four things at once, because a session is only useful if
it rehydrates into the same workspace the operator left:

1. the **evidence bundle** (every file under the incident's bundle directory),
2. the **pipeline history** (the stage records and the whole event log),
3. the **incident report**, if one was produced,
4. the **repair packages** already built for this incident.

What is *not* in the bundle is recorded in the manifest as missing.  The
builder never synthesizes a report, an event, or a stage that did not exist —
a session that captures an unfinished investigation is a session that comes
back unfinished, and says so.
"""

from __future__ import annotations

import io
import json
import logging
import re
import zipfile
from pathlib import Path
from typing import Any, List, Optional, Tuple

from cauveris.config import get_settings
from cauveris.sessions.manifest import (
    build_session_manifest,
    checksum_blob,
    manifest_to_yaml,
)
from cauveris.sessions.models import (
    SESSION_ARTIFACTS_DIR,
    SESSION_CHECKSUMS_PATH,
    SESSION_EVENTS_PATH,
    SESSION_MANIFEST_PATH,
    SESSION_PACKAGES_DIR,
    SESSION_REPORT_PATH,
    SESSION_STAGES_PATH,
    SessionBuildOutcome,
    SessionManifest,
    SessionRecord,
    random_session_id,
)

logger = logging.getLogger(__name__)


#: Files that live inside an evidence bundle but are never part of a session's
#: evidence — they describe the *store*, not the investigation.
_BUNDLE_EXCLUDED_NAMES = frozenset(
    {
        ".cauveris-owner.json",
        ".cauveris-incident.json",
    }
)

#: Guard against a runaway bundle being archived into one enormous zip.
_MAX_EVIDENCE_BYTES = 512 * 1024 * 1024


def _safe_component(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]", "_", str(value or "unknown"))
    return text[:128] or "unknown"


class SessionBuilder:
    """
    Builds session archives from the live state of an incident.

    The builder is deliberately free of HTTP concerns: it takes an incident id
    and produces bytes plus a manifest.  ``cauveris/sessions/api_router.py``
    owns the request/response shape and the ownership checks.
    """

    def __init__(self, settings=None):
        self.settings = settings or get_settings()

    # ------------------------------------------------------------- internals

    def _bundle_dir(self, incident_id: str, incident: Any) -> Optional[Path]:
        """The directory holding the incident's evidence files."""
        bundle_path = getattr(incident, "bundle_path", None)
        if bundle_path:
            candidate = Path(bundle_path)
            if candidate.exists() and candidate.is_dir():
                return candidate

        store_root = Path(self.settings.evidence_store_path)
        candidate = store_root / incident_id
        if candidate.exists() and candidate.is_dir():
            return candidate
        return None

    def _collect_evidence(
        self, bundle_dir: Optional[Path]
    ) -> Tuple[List[Tuple[str, bytes]], int]:
        """Read every evidence file into memory as ``(archive_path, bytes)``."""
        artifacts: List[Tuple[str, bytes]] = []
        total = 0
        if bundle_dir is None:
            return artifacts, total

        for file_path in sorted(bundle_dir.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.name in _BUNDLE_EXCLUDED_NAMES:
                continue
            if file_path.name in ("manifest.yaml", "manifest.yml", "manifest.json"):
                # The bundle's own manifest is superseded by the session
                # manifest; carrying both would invite confusion about which
                # one is authoritative.
                continue
            try:
                data = file_path.read_bytes()
            except OSError as exc:
                logger.warning(f"Skipping unreadable evidence file {file_path}: {exc}")
                continue
            total += len(data)
            if total > _MAX_EVIDENCE_BYTES:
                logger.warning(
                    f"Evidence bundle at {bundle_dir} exceeds the session cap; "
                    "truncating the archive."
                )
                break
            rel = str(file_path.relative_to(bundle_dir)).replace("\\", "/")
            artifacts.append((f"{SESSION_ARTIFACTS_DIR}/{rel}", data))
        return artifacts, total

    def _report_bytes(self, incident_id: str) -> Optional[bytes]:
        """The incident report, if one was written to disk."""
        report_file = Path(self.settings.report_store_path) / incident_id / "incident_report.json"
        if not report_file.exists():
            return None
        try:
            return report_file.read_bytes()
        except OSError as exc:
            logger.warning(f"Could not read report for incident {incident_id}: {exc}")
            return None

    def _repair_package_files(self, incident_id: str) -> List[Tuple[str, bytes]]:
        """The repair packages already built for this incident."""
        archives_dir = Path(self.settings.report_store_path) / "packaging" / "archives"
        if not archives_dir.exists():
            return []

        prefix = f"{_safe_component(incident_id)}__"
        packages: List[Tuple[str, bytes]] = []
        for archive in sorted(archives_dir.glob(f"{prefix}*.zip")):
            try:
                data = archive.read_bytes()
            except OSError as exc:
                logger.warning(f"Could not read repair package {archive}: {exc}")
                continue
            packages.append((f"{SESSION_PACKAGES_DIR}/{archive.name}", data))
        return packages

    def _pipeline_state(self, incident_id: str) -> Tuple[str, Optional[str]]:
        """The pipeline state and active stage the session was captured in."""
        try:
            from cauveris.api.main import pipeline_progress, pipeline_tasks

            orch = pipeline_tasks.get(incident_id)
            if orch is not None:
                summary = orch.get_pipeline_summary()
                state = str(summary.get("state") or "IDLE")
                active = summary.get("active_stage_id")
                return state, active

            progress = pipeline_progress.get(incident_id) or {}
            state = str(progress.get("state") or progress.get("workflow_status") or "IDLE")
            active = progress.get("active_stage_id")
            return state, active
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"Could not resolve pipeline state for {incident_id}: {exc}")
            return "IDLE", None

    # ------------------------------------------------------------------ build

    def build(
        self,
        incident_id: str,
        incident: Any,
        *,
        user_id: str = "",
        org_id: str = "",
        session_id: Optional[str] = None,
    ) -> SessionBuildOutcome:
        """
        Build the session archive for an incident.

        Args:
            incident_id: The incident being captured.
            incident: The live :class:`~cauveris.schemas.incident.Incident`.
            user_id: The operator building the session.
            org_id: The operator's organisation.
            session_id: An explicit session id; a fresh one is minted otherwise.

        Returns:
            A :class:`SessionBuildOutcome` carrying the archive bytes, the
            manifest and an honest list of what the archive does *not* contain.
        """
        session_id = session_id or random_session_id()
        missing: List[str] = []
        warnings: List[str] = []

        # --- pipeline history -------------------------------------------
        try:
            from cauveris.state_machine.persistence import PipelinePersistenceStore

            store = PipelinePersistenceStore.get_instance()
            stages = store.export_stages(incident_id)
            events = store.export_events(incident_id)
        except Exception as exc:
            logger.warning(f"Could not export pipeline history for {incident_id}: {exc}")
            stages, events = [], []
            missing.append("pipeline_history")
            warnings.append(f"Pipeline history could not be exported: {exc}")

        artifacts: List[Tuple[str, bytes]] = []
        artifacts.append(
            (
                SESSION_STAGES_PATH,
                json.dumps(
                    {"incident_id": incident_id, "stages": stages}, indent=2, default=str
                ).encode("utf-8"),
            )
        )
        artifacts.append(
            (
                SESSION_EVENTS_PATH,
                json.dumps(
                    {"incident_id": incident_id, "events": events}, indent=2, default=str
                ).encode("utf-8"),
            )
        )

        # --- evidence ----------------------------------------------------
        bundle_dir = self._bundle_dir(incident_id, incident)
        evidence_artifacts, _ = self._collect_evidence(bundle_dir)
        artifacts.extend(evidence_artifacts)
        if not evidence_artifacts:
            missing.append("evidence")
            if bundle_dir is None:
                warnings.append(
                    "No evidence bundle directory was found for this incident; "
                    "the session captures pipeline state only."
                )

        # --- report ------------------------------------------------------
        report_bytes = self._report_bytes(incident_id)
        if report_bytes is not None:
            artifacts.append((SESSION_REPORT_PATH, report_bytes))
        else:
            missing.append("report")

        # --- repair packages ---------------------------------------------
        package_artifacts = self._repair_package_files(incident_id)
        artifacts.extend(package_artifacts)
        if not package_artifacts:
            missing.append("repair_packages")

        # --- manifest ------------------------------------------------------
        pipeline_state, active_stage_id = self._pipeline_state(incident_id)
        metadata = getattr(incident, "metadata_snapshot", None)
        snapshot = metadata() if callable(metadata) else {}

        manifest = build_session_manifest(
            incident_id=incident_id,
            artifacts=artifacts,
            title=getattr(incident, "title", "") or "",
            description=getattr(incident, "description", "") or "",
            system_name=getattr(incident, "system_name", None),
            severity=snapshot.get("severity"),
            category=snapshot.get("category"),
            environment=snapshot.get("environment"),
            tags=snapshot.get("tags"),
            intake_method=snapshot.get("intake_method"),
            approximate_time=snapshot.get("approximate_time"),
            is_demonstration=bool(getattr(incident, "is_demonstration", False)),
            pipeline_state=pipeline_state,
            active_stage_id=active_stage_id,
            report_present=report_bytes is not None,
            repair_package_count=len(package_artifacts),
            evidence_file_count=len(evidence_artifacts),
            stage_count=len(stages),
            event_count=len(events),
            session_id=session_id,
        )

        zip_bytes = self._write_archive(manifest, artifacts)
        record = SessionRecord(
            incident_id=incident_id,
            session_id=session_id,
            status="READY",
            session_sha256="",
            size=len(zip_bytes),
            safe_filename=f"cauveris-session-{_safe_component(incident_id)[:16]}-{_safe_component(session_id)[:16]}.zip",
            manifest=manifest.to_dict(),
            built_by_user_id=user_id,
            built_by_org_id=org_id,
            source_incident_id=incident_id,
        )
        return SessionBuildOutcome(
            record=record,
            manifest=manifest,
            zip_bytes=zip_bytes,
            warnings=warnings,
            missing=missing,
        )

    # -------------------------------------------------------------- archive

    @staticmethod
    def _write_archive(manifest: SessionManifest, artifacts: List[Tuple[str, bytes]]) -> bytes:
        """
        Assemble the zip.

        The manifest is written last and is *not* checksummed inside itself
        (a self-referential checksum could never verify); every other member
        appears both in the manifest's ``files`` table and in
        ``checksums.sha256``.
        """
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path, data in artifacts:
                zf.writestr(path, data)
            zf.writestr(SESSION_CHECKSUMS_PATH, checksum_blob(manifest.checksum_lines))
            zf.writestr(SESSION_MANIFEST_PATH, manifest_to_yaml(manifest))
        return buffer.getvalue()
