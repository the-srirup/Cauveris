"""
Session-package storage: a metadata index plus on-disk archives.

The store mirrors the proven ``cauveris/packaging/storage.py`` discipline —
an atomically-written JSON index, archives named from sanitized identifiers,
and no caller-supplied path ever reaching the filesystem.

Layout::

    <sessions_root>/
        index.json          # metadata index (atomic write)
        work/
            <incident_id>__<session_id>__b<n>/   # per-build staging dirs
        archives/
            <incident_id>__<session_id>__b<n>.zip
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from cauveris.config import get_settings
from cauveris.sessions.models import SessionRecord

logger = logging.getLogger(__name__)


_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _safe_name(value: str) -> str:
    """A filesystem-safe component for an incident or session id."""
    text = str(value).strip().replace("/", "_").replace("\\", "_")
    if not _SAFE_NAME_RE.match(text):
        text = re.sub(r"[^A-Za-z0-9._-]", "_", text)
        if not text:
            text = "unknown"
    return text[:128]


class SessionStore:
    """
    Persistent store for session-package metadata and archive files.

    Isolation is enforced by construction: every archive path is derived from
    the incident id and session id (both sanitized), and the index is queried
    by ``(incident_id, session_id)`` — never by a caller-supplied path.
    """

    INDEX_NAME = "index.json"
    WORK_SUBDIR = "work"
    ARCHIVE_SUBDIR = "archives"

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        root = Path(self.settings.report_store_path) / "sessions"
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        (self._root / self.WORK_SUBDIR).mkdir(parents=True, exist_ok=True)
        (self._root / self.ARCHIVE_SUBDIR).mkdir(parents=True, exist_ok=True)
        self._index_path = self._root / self.INDEX_NAME
        self._index = self._load_index()

    # ------------------------------------------------------------------ index

    def _load_index(self) -> Dict[str, Any]:
        if self._index_path.exists():
            try:
                data = json.loads(self._index_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "sessions" in data:
                    return data
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(f"Could not parse session index, starting fresh: {exc}")
        return {"version": 1, "sessions": {}}

    def _save_index(self) -> None:
        """Atomically write the index (temp + rename)."""
        data = json.dumps(self._index, indent=2, default=str)
        tmp = self._index_path.with_suffix(".tmp")
        tmp.write_text(data, encoding="utf-8")
        os.replace(tmp, self._index_path)

    @property
    def index(self) -> Dict[str, Any]:
        return self._index

    @property
    def root(self) -> Path:
        return self._root

    def _safe(self, value: str) -> str:
        return _safe_name(value)

    def _key(self, incident_id: str, session_id: str) -> str:
        return f"{self._safe(incident_id)}::{self._safe(session_id)}"

    # ------------------------------------------------------------ archive paths

    def archive_path(self, incident_id: str, session_id: str, build_number: int) -> Path:
        name = f"{self._safe(incident_id)}__{self._safe(session_id)}__b{build_number}.zip"
        return self._root / self.ARCHIVE_SUBDIR / name

    def staging_dir(self, incident_id: str, session_id: str, build_number: int) -> Path:
        name = f"{self._safe(incident_id)}__{self._safe(session_id)}__b{build_number}"
        directory = self._root / self.WORK_SUBDIR / name
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    # ------------------------------------------------------------ record ops

    def create_record(
        self,
        incident_id: str,
        session_id: str,
        user_id: str,
        org_id: str,
        *,
        manifest: Optional[Dict[str, Any]] = None,
        source_incident_id: str = "",
    ) -> SessionRecord:
        """Allocate a new build number for ``(incident, session)`` and record it."""
        key = self._key(incident_id, session_id)
        bucket = self._index["sessions"].setdefault(
            key, {"history": [], "latest": None}
        )

        prior = bucket.get("history", [])
        build_number = 1
        if prior:
            build_number = max(p.get("build_number", 0) for p in prior) + 1

        safe_inc = self._safe(incident_id)
        safe_ses = self._safe(session_id)
        now_iso = datetime.now(timezone.utc).isoformat()

        record = SessionRecord(
            incident_id=incident_id,
            session_id=session_id,
            build_number=build_number,
            status="BUILDING",
            safe_filename=f"cauveris-session-{safe_inc[:16]}-{safe_ses[:16]}.zip",
            manifest=manifest or {},
            created_at=now_iso,
            updated_at=now_iso,
            built_by_user_id=user_id,
            built_by_org_id=org_id,
            source_incident_id=source_incident_id or incident_id,
        )

        bucket["history"].append(record.to_dict())
        bucket["latest"] = record.to_dict()
        self._save_index()
        return record

    def update_record(self, record: SessionRecord) -> SessionRecord:
        """Persist an updated record (status, locator, checksum, manifest)."""
        key = self._key(record.incident_id, record.session_id)
        bucket = self._index["sessions"].setdefault(
            key, {"history": [], "latest": None}
        )
        history = bucket["history"]
        updated = False
        for i, entry in enumerate(history):
            if entry.get("build_number") == record.build_number:
                history[i] = record.to_dict()
                updated = True
                break
        if not updated:
            history.append(record.to_dict())
        bucket["latest"] = record.to_dict()
        self._save_index()
        return record

    def set_status(
        self,
        incident_id: str,
        session_id: str,
        build_number: int,
        status: str,
        *,
        error: Optional[str] = None,
        failure_code: Optional[str] = None,
        zip_path: Optional[str] = None,
        checksum: Optional[str] = None,
        size_bytes: Optional[int] = None,
        manifest: Optional[Dict[str, Any]] = None,
    ) -> Optional[SessionRecord]:
        """Transition one build to a new status."""
        key = self._key(incident_id, session_id)
        bucket = self._index["sessions"].get(key)
        if bucket is None:
            return None
        for entry in bucket["history"]:
            if entry.get("build_number") == build_number:
                entry["status"] = status
                entry["updated_at"] = datetime.now(timezone.utc).isoformat()
                if error is not None:
                    entry["failure_message"] = error
                if failure_code is not None:
                    entry["failure_code"] = failure_code
                if zip_path is not None:
                    entry["storage_locator"] = zip_path
                if checksum is not None:
                    entry["session_sha256"] = checksum
                if size_bytes is not None:
                    entry["size"] = size_bytes
                if manifest is not None:
                    entry["manifest"] = manifest
                bucket["latest"] = dict(entry)
                self._save_index()
                return SessionRecord.from_dict(entry)
        return None

    def mark_deleted(self, incident_id: str, session_id: str, build_number: int) -> bool:
        """Mark a build as DELETED and remove its archive."""
        record = self.set_status(incident_id, session_id, build_number, "DELETED")
        if record is None:
            return False
        path = self.archive_path(incident_id, session_id, build_number)
        if path.exists():
            try:
                path.unlink()
            except OSError as exc:
                logger.warning(f"Could not delete session archive {path}: {exc}")
        return True

    # ------------------------------------------------------------- lookups

    def list_for_incident(self, incident_id: str) -> List[SessionRecord]:
        """Every session build recorded for an incident, newest first."""
        incident_key = self._safe(incident_id)
        records: List[SessionRecord] = []
        for key, bucket in self._index.get("sessions", {}).items():
            if not key.startswith(f"{incident_key}::"):
                continue
            for entry in bucket.get("history", []):
                records.append(SessionRecord.from_dict(entry))
        records.sort(key=lambda r: (r.build_number, r.created_at), reverse=True)
        return records

    def get_build(
        self, incident_id: str, session_id: str, build_number: int
    ) -> Optional[SessionRecord]:
        bucket = self._index["sessions"].get(self._key(incident_id, session_id))
        if bucket is None:
            return None
        for entry in bucket.get("history", []):
            if entry.get("build_number") == build_number:
                return SessionRecord.from_dict(entry)
        return None

    def latest_ready(self, incident_id: str) -> Optional[SessionRecord]:
        """The newest READY session package for an incident."""
        candidates = [
            record
            for record in self.list_for_incident(incident_id)
            if record.status == "READY" and record.is_downloadable
        ]
        return candidates[0] if candidates else None

    def latest_any(self, incident_id: str) -> Optional[SessionRecord]:
        """The newest session build for an incident, whatever its status."""
        records = self.list_for_incident(incident_id)
        return records[0] if records else None

    def get_by_session_id(self, session_id: str) -> Optional[SessionRecord]:
        """Look up a session across all incidents by its session id."""
        for bucket in self._index.get("sessions", {}).values():
            for entry in bucket.get("history", []):
                if entry.get("session_id") == session_id:
                    return SessionRecord.from_dict(entry)
        return None

    # --------------------------------------------------------------- helpers

    @staticmethod
    def sha256_path(path: Path) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    # ----------------------------------------------------------- atomic write

    def write_archive_atomic(
        self,
        incident_id: str,
        session_id: str,
        build_number: int,
        zip_bytes: bytes,
    ) -> Path:
        """
        Write the session archive atomically.

        Writes to a temp file first, validates it is a real zip, then renames
        it into place.  Returns the final archive path.
        """
        dest = self.archive_path(incident_id, session_id, build_number)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        try:
            tmp.write_bytes(zip_bytes)
            with zipfile.ZipFile(tmp, "r") as zf:
                bad = zf.testzip()
                if bad is not None:
                    raise ValueError(f"Corrupt zip member: {bad}")
            os.replace(tmp, dest)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        return dest

    def archive_exists(self, record: SessionRecord) -> bool:
        """Whether the record's archive is still on disk."""
        if not record.storage_locator:
            return False
        return Path(record.storage_locator).exists()
