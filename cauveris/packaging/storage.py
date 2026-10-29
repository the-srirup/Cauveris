"""
Package storage abstraction: persisted metadata index + on-disk archives.

The store is the single source of truth for package state.  It persists its
metadata index as JSON (temp-write + atomic rename), keeps archives in a
canonical layout under ``report_store_path/packaging``, and enforces
cross-incident and cross-user isolation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cauveris.config import get_settings
from cauveris.packaging.models import (
    PackageStatus,
    RepairPackageRecord,
    VerificationLevel,
)

logger = logging.getLogger(__name__)


_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _safe_name(value: str) -> str:
    """A filesystem-safe component for an incident or repair id."""
    text = str(value).strip().replace("/", "_").replace("\\", "_")
    if not _SAFE_NAME_RE.match(text):
        # Replace any remaining unsafe characters.
        text = re.sub(r"[^A-Za-z0-9._-]", "_", text)
        if not text:
            text = "unknown"
    return text[:128]


class PackageStore:
    """
    Persistent store for repair-package metadata and archive files.

    Layout::

        <packaging_root>/
            index.json          # metadata index (atomic write)
            work/
                <incident_id>__<repair_id>/   # per-package staging dirs
            archives/
                <incident_id>__<repair_id>__<build>.zip
                <incident_id>__<repair_id>__<build>.zip.sha256

    Isolation is enforced by construction: every archive path is derived from
    the incident_id and repair_id (both sanitized), and the metadata index is
    queried by (incident_id, repair_id) — never by a caller-supplied path.
    """

    MANIFEST_NAME = "manifest.json"
    INDEX_NAME = "index.json"
    WORK_SUBDIR = "work"
    ARCHIVE_SUBDIR = "archives"

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        root = Path(self.settings.report_store_path) / "packaging"
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
                if isinstance(data, dict) and "packages" in data:
                    return data
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(f"Could not parse package index, starting fresh: {exc}")
        return {"version": 1, "packages": {}}

    def _save_index(self) -> None:
        """Atomically write the index (temp + rename)."""
        data = json.dumps(self._index, indent=2, default=str)
        tmp = self._index_path.with_suffix(".tmp")
        tmp.write_text(data, encoding="utf-8")
        os.replace(tmp, self._index_path)

    @property
    def index(self) -> Dict[str, Any]:
        return self._index

    def _key(self, incident_id: str, repair_id: str) -> str:
        return f"{(self._safe(incident_id))}::{(self._safe(repair_id))}"

    def _safe(self, value: str) -> str:
        return _safe_name(value)

    # ---------------------------------------------------------- archive paths

    def archive_path(
        self, incident_id: str, repair_id: str, build_number: int
    ) -> Path:
        name = f"{self._safe(incident_id)}__{self._safe(repair_id)}__b{build_number}.zip"
        return self._root / self.ARCHIVE_SUBDIR / name

    def staging_dir(
        self, incident_id: str, repair_id: str, build_number: int
    ) -> Path:
        name = f"{self._safe(incident_id)}__{self._safe(repair_id)}__b{build_number}"
        d = self._root / self.WORK_SUBDIR / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ----------------------------------------------------------- record ops

    def create_record(
        self,
        incident_id: str,
        repair_id: str,
        user_id: str,
        org_id: str,
        candidate_snapshot: Optional[Dict[str, Any]] = None,
        checks_snapshot: Optional[Dict[str, bool]] = None,
        verification_level: str = VerificationLevel.GENERATED.value,
        source_bundle_id: str = "",
        verification_run_id: Optional[str] = None,
        report_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        source_tree_hash: str = "",
    ) -> RepairPackageRecord:
        """Allocate a new build_number for (incident, repair) and a QUEUED record."""
        key = self._key(incident_id, repair_id)
        existing = self._index["packages"].get(key, {})

        # Determine the next build number. We never reuse a build number:
        # each build produces a new archive, and the old one is marked STALE.
        prior = existing.get("history", [])
        build_number = 1
        if prior:
            build_number = max(p.get("build_number", 0) for p in prior) + 1

        # Mark any prior READY record STALE.
        for entry in prior:
            if entry.get("status") == PackageStatus.READY.value:
                entry["status"] = PackageStatus.STALE.value

        safe_inc = self._safe(incident_id)
        safe_rep = self._safe(repair_id)
        package_id = f"pkg_{safe_inc}_{safe_rep}_{build_number}"
        safe_filename = f"cauveris-repair-{safe_inc[:12]}-{safe_rep[:12]}.zip"
        now_iso = datetime.now(timezone.utc).isoformat()

        record = RepairPackageRecord(
            incident_id=incident_id,
            repair_candidate_id=repair_id,
            build_number=build_number,
            status=PackageStatus.QUEUED,
            package_id=package_id,
            safe_filename=safe_filename,
            built_by_user_id=user_id,
            built_by_org_id=org_id,
            created_at=now_iso,
            updated_at=now_iso,
            candidate_snapshot=candidate_snapshot or {},
            checks_snapshot=checks_snapshot or {},
            verification_level=verification_level,
            source_bundle_id=source_bundle_id,
            source_tree_hash=source_tree_hash,
            verification_run_id=verification_run_id,
            report_id=report_id,
            workspace_id=workspace_id,
        )

        if key not in self._index["packages"]:
            self._index["packages"][key] = {"history": [], "latest": None}
        self._index["packages"][key]["history"].append(record.to_dict())
        self._index["packages"][key]["latest"] = record.to_dict()
        self._save_index()
        return record

    def update_record(self, record: RepairPackageRecord) -> RepairPackageRecord:
        """Persist an updated record (status, zip_path, checksum, etc.)."""
        key = self._key(record.incident_id, record.repair_id)
        bucket = self._index["packages"].get(key)
        if bucket is None:
            bucket = {"history": [], "latest": None}
            self._index["packages"][key] = bucket

        history = bucket["history"]
        updated = False
        for i, entry in enumerate(history):
            if entry.get("package_id") == record.package_id:
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
        repair_id: str,
        build_number: int,
        status: PackageStatus,
        *,
        error: Optional[str] = None,
        zip_path: Optional[str] = None,
        checksum: Optional[str] = None,
        size_bytes: Optional[int] = None,
    ) -> Optional[RepairPackageRecord]:
        """Transition a specific build to a new status."""
        key = self._key(incident_id, repair_id)
        bucket = self._index["packages"].get(key)
        if bucket is None:
            return None
        for entry in bucket["history"]:
            if entry.get("build_number") == build_number:
                if status == PackageStatus.READY:
                    entry["status"] = status.value
                    entry["ready_at"] = datetime.now(timezone.utc).isoformat()
                    if error is not None:
                        entry["error"] = error
                        entry["failure_message"] = error
                else:
                    entry["status"] = status.value
                    if error is not None:
                        entry["error"] = error
                        entry["failure_message"] = error
                if zip_path is not None:
                    entry["zip_path"] = zip_path
                    entry["storage_locator"] = zip_path
                if checksum is not None:
                    entry["checksum_sha256"] = checksum
                    entry["package_sha256"] = checksum
                if size_bytes is not None:
                    entry["size_bytes"] = size_bytes
                    entry["size"] = size_bytes
                bucket["latest"] = dict(entry)
                self._save_index()
                return RepairPackageRecord.from_dict(entry)
        return None

    def mark_deleted(self, incident_id: str, repair_id: str, build_number: int) -> bool:
        """Mark a build as DELETED and remove its archive."""
        record = self.set_status(
            incident_id, repair_id, build_number, PackageStatus.DELETED
        )
        if record is None:
            return False
        path = self.archive_path(incident_id, repair_id, build_number)
        if path.exists():
            try:
                path.unlink()
            except OSError as exc:
                logger.warning(f"Could not delete archive {path}: {exc}")
        return True

    # ------------------------------------------------------------- lookups

    def get_by_package_id(self, package_id: str) -> Optional[RepairPackageRecord]:
        """Look up a package across all incidents by its unique package_id."""
        for bucket in self._index.get("packages", {}).values():
            for entry in bucket.get("history", []):
                if entry.get("package_id") == package_id:
                    return RepairPackageRecord.from_dict(entry)
        return None

    def list_for_incident(self, incident_id: str) -> List[RepairPackageRecord]:
        """List all packages across all repair candidates for an incident."""
        incident_key = self._safe(incident_id)
        records: List[RepairPackageRecord] = []
        for key, bucket in self._index.get("packages", {}).items():
            if not key.startswith(f"{incident_key}::"):
                continue
            for entry in bucket.get("history", []):
                records.append(RepairPackageRecord.from_dict(entry))
        return records

    def get_latest(
        self, incident_id: str, repair_id: str
    ) -> Optional[RepairPackageRecord]:
        key = self._key(incident_id, repair_id)
        bucket = self._index["packages"].get(key)
        if bucket is None:
            return None
        latest = bucket.get("latest")
        if latest is None:
            return None
        return RepairPackageRecord.from_dict(latest)

    def get_build(
        self, incident_id: str, repair_id: str, build_number: int
    ) -> Optional[RepairPackageRecord]:
        key = self._key(incident_id, repair_id)
        bucket = self._index["packages"].get(key)
        if bucket is None:
            return None
        for entry in bucket["history"]:
            if entry.get("build_number") == build_number:
                return RepairPackageRecord.from_dict(entry)
        return None

    def latest_ready(
        self, incident_id: str, repair_id: Optional[str] = None
    ) -> Optional[RepairPackageRecord]:
        """The newest READY package for an incident (optionally scoped to a repair)."""
        key_prefix = self._key(incident_id, "") if repair_id is None else None
        results: List[Tuple[int, RepairPackageRecord]] = []
        for key, bucket in self._index["packages"].items():
            if key_prefix is not None:
                if not key.startswith(key_prefix.rstrip(":")) and key != key_prefix.rstrip(":"):
                    # Match either exact or incident-scoped.
                    incident_key = self._safe(incident_id)
                    if not key.startswith(f"{incident_key}::"):
                        continue
            elif repair_id is not None:
                if key != self._key(incident_id, repair_id):
                    continue
            for entry in bucket.get("history", []):
                rec = RepairPackageRecord.from_dict(entry)
                if rec.status == PackageStatus.READY and rec.is_downloadable:
                    results.append((rec.build_number, rec))
        if not results:
            return None
        results.sort(key=lambda x: x[0], reverse=True)
        return results[0][1]

    # ----------------------------------------------------------- retention

    def retire_stale_for_incident(self, incident_id: str) -> int:
        """Delete archives of STALE builds belonging to an incident."""
        incident_key = self._safe(incident_id)
        count = 0
        for key, bucket in self._index["packages"].items():
            if not key.startswith(f"{incident_key}::"):
                continue
            for entry in bucket.get("history", []):
                if entry.get("status") == PackageStatus.STALE.value:
                    path = self.archive_path(
                        incident_id, entry.get("repair_id", ""), entry.get("build_number", 0)
                    )
                    if path.exists():
                        try:
                            path.unlink()
                            count += 1
                        except OSError:
                            pass
        return count

    # ----------------------------------------------------------- helpers

    @staticmethod
    def sha256_path(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def file_sha256(path: Path) -> str:
        return PackageStore.sha256_path(path)

    def _ensure_archive_parent(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------- atomic write

    def write_archive_atomic(
        self,
        incident_id: str,
        repair_id: str,
        build_number: int,
        zip_bytes: bytes,
    ) -> Path:
        """
        Write the package archive atomically.

        Writes to a temp file first, validates it is a real zip, then renames
        into place.  Returns the final archive path.
        """
        dest = self.archive_path(incident_id, repair_id, build_number)
        self._ensure_archive_parent(dest)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        try:
            tmp.write_bytes(zip_bytes)
            # Validate it is a real zip.
            import zipfile

            with zipfile.ZipFile(tmp, "r") as zf:
                bad = zf.testzip()
                if bad is not None:
                    raise ValueError(f"Corrupt zip member: {bad}")
            os.replace(tmp, dest)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        return dest
