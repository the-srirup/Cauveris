"""
HTTP surface for session packages.

Four endpoints:

* ``POST   /api/v1/sessions/{incident_id}``            build a session package (202)
* ``GET    /api/v1/sessions/{incident_id}``            list the incident's session packages
* ``GET    /api/v1/sessions/{incident_id}/download``   download the newest ready archive
* ``POST   /api/v1/sessions/import``                   import a session ``.zip``

Access is owner-scoped exactly like a repair package: a session archive
contains the whole investigation, so it must not leak across users or
organisations.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse

from cauveris.api.deps import get_current_user
from cauveris.auth import AuditLogEntry, get_auth_store
from cauveris.sessions.builder import SessionBuilder
from cauveris.sessions.models import (
    SessionChecksumError,
    SessionError,
    SessionFormatError,
)
from cauveris.sessions.restore import SessionRestorer
from cauveris.sessions.storage import SessionStore

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/sessions",
    tags=["sessions"],
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _ensure_incident(incident_id: str) -> Any:
    """Resolve an incident by id, hydrating it from the store if needed."""
    from cauveris.api.main import _ensure_incident as _resolve  # local import to avoid a cycle

    incident = _resolve(incident_id)
    if incident is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "incident_not_found", "incident_id": incident_id},
        )
    return incident


async def _audit(
    request: Request,
    auth_store,
    user,
    org_id: str,
    action: str,
    resource_id: str,
    decision: str,
    reason: str = "",
    resource_owner_id: Optional[str] = None,
) -> None:
    """Write one audit-log entry.  Never fails the request."""
    try:
        await auth_store.write_audit_log(
            AuditLogEntry(
                user_id=user.id,
                org_id=org_id,
                action=action,
                resource_type="session",
                resource_id=resource_id,
                resource_owner_id=resource_owner_id,
                decision=decision,
                reason=reason,
                ip_address=(
                    request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                    or (request.client.host if request.client else "unknown")
                ),
                user_agent=request.headers.get("User-Agent", ""),
                request_id=getattr(request.state, "request_id", None),
            )
        )
    except Exception as exc:  # pragma: no cover - auditing must not break the flow
        logger.warning(f"Could not write session audit log entry: {exc}")


async def _authorize(
    request: Request,
    incident: Any,
    user_data: tuple,
    action: str,
    required_permission: str,
) -> tuple:
    """
    Enforce permission and ownership for a session operation.

    Returns the ``(user, auth_store)`` pair on success.  Raises 403 otherwise.
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail={"error": "auth_store_unavailable"})

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=401, detail={"error": "user_not_found"})

    is_admin = getattr(user, "is_superuser", False) or user.has_permission("*")

    if not is_admin and not user.has_permission(required_permission):
        await _audit(
            request,
            auth_store,
            user,
            org_id,
            action,
            str(getattr(incident, "id", "")),
            "deny",
            f"Missing permission: {required_permission}",
        )
        raise HTTPException(
            status_code=403,
            detail={"error": "insufficient_permissions", "required": required_permission},
        )

    owner_user = getattr(incident, "_owner_user_id", None)
    owner_org = getattr(incident, "_owner_org_id", None)

    if not is_admin:
        if owner_org and owner_org != org_id:
            await _audit(
                request,
                auth_store,
                user,
                org_id,
                action,
                str(getattr(incident, "id", "")),
                "deny",
                "Cross-organization session access denied",
                owner_user,
            )
            raise HTTPException(
                status_code=403,
                detail={"error": "access_denied", "incident_id": str(getattr(incident, "id", ""))},
            )
        if owner_user and owner_user != user_id:
            await _audit(
                request,
                auth_store,
                user,
                org_id,
                action,
                str(getattr(incident, "id", "")),
                "deny",
                "Not authorized to access this incident's session package",
                owner_user,
            )
            raise HTTPException(
                status_code=403,
                detail={"error": "access_denied", "incident_id": str(getattr(incident, "id", ""))},
            )

    return user, auth_store


# ---------------------------------------------------------------------------
# import
#
# NOTE: this route is declared *before* the ``{incident_id}`` routes on
# purpose.  FastAPI matches routes in declaration order, so a static
# ``/import`` declared afterwards would be shadowed by ``POST /{incident_id}``
# and the import would try to resolve an incident literally called "import".
# ---------------------------------------------------------------------------


@router.post("/import", name="import_session_package")
async def import_session_package(
    request: Request,
    file: UploadFile = File(...),
    user_data: tuple = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Import a session package and return what it restored.

    The response is an honest account of the archive: ``restored`` names the
    parts that came back and ``missing`` names the parts that were not in the
    archive.  A session with no report comes back with no report — it is
    never presented as an incident that was investigated and found clean.
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail={"error": "auth_store_unavailable"})

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=401, detail={"error": "user_not_found"})

    if not user.has_permission("incident:create") and not user.has_permission("*"):
        await _audit(
            request, auth_store, user, org_id, "session.import", "unknown", "deny",
            "Missing permission: incident:create",
        )
        raise HTTPException(
            status_code=403,
            detail={"error": "insufficient_permissions", "required": "incident:create"},
        )

    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=422, detail={"error": "session_import_requires_a_zip_archive"}
        )

    staging_root = Path(tempfile.mkdtemp(prefix="cauveris-session-import-"))
    archive_path = staging_root / "session.zip"
    try:
        with open(archive_path, "wb") as handle:
            # shutil.copyfileobj streams the upload to disk in chunks.
            shutil.copyfileobj(file.file, handle, length=1024 * 1024)

        restorer = SessionRestorer()
        summary = restorer.restore(
            archive_path,
            staging_root / "extracted",
            user_id=user_id,
            org_id=org_id,
        )
    except SessionFormatError as exc:
        await _audit(
            request, auth_store, user, org_id, "session.import", "unknown", "deny", exc.message
        )
        raise HTTPException(status_code=422, detail={"error": exc.code, "message": exc.message})
    except SessionChecksumError as exc:
        await _audit(
            request, auth_store, user, org_id, "session.import", "unknown", "deny", exc.message
        )
        raise HTTPException(status_code=422, detail={"error": exc.code, "message": exc.message})
    except ValueError as exc:
        # The archive policy helper raises ValueError for traversal attempts,
        # corrupt archives and size-cap violations.
        await _audit(
            request, auth_store, user, org_id, "session.import", "unknown", "deny", str(exc)
        )
        raise HTTPException(status_code=422, detail={"error": "session_archive_rejected", "message": str(exc)})
    except SessionError as exc:
        logger.exception("Session import failed")
        await _audit(
            request, auth_store, user, org_id, "session.import", "unknown", "deny", exc.message
        )
        raise HTTPException(status_code=500, detail={"error": "session_import_failed"})
    except Exception as exc:
        logger.exception("Session import failed")
        await _audit(
            request, auth_store, user, org_id, "session.import", "unknown", "deny", str(exc)
        )
        raise HTTPException(status_code=500, detail={"error": "session_import_failed"})
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)

    await _audit(
        request,
        auth_store,
        user,
        org_id,
        "session.import",
        summary.incident_id,
        "allow",
        f"Session imported as {summary.incident_id}",
    )

    return {"status": "IMPORTED", **summary.to_dict()}


# ---------------------------------------------------------------------------
# build / list / download
# ---------------------------------------------------------------------------


@router.post(
    "/{incident_id}",
    status_code=202,
    name="build_session_package",
)
async def build_session_package(
    request: Request,
    incident_id: str,
    user_data: tuple = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Build a session package capturing the incident's live state.

    The archive carries the evidence bundle, the pipeline stage history and
    event log, the incident report when one exists, and the repair packages
    already built for the incident.  Anything the incident does not have is
    listed under ``missing`` — nothing is synthesized.
    """
    incident = _ensure_incident(incident_id)
    user, auth_store = await _authorize(
        request, incident, user_data, "session.build", "evidence:read"
    )

    builder = SessionBuilder()
    try:
        outcome = builder.build(
            incident_id,
            incident,
            user_id=user_data[0],
            org_id=user_data[1],
        )
    except Exception as exc:
        logger.exception(f"Session build failed for incident {incident_id}")
        await _audit(
            request, auth_store, user, user_data[1], "session.build", incident_id, "deny", str(exc)
        )
        raise HTTPException(status_code=500, detail={"error": "session_build_failed"})

    store = SessionStore()
    record = store.create_record(
        incident_id,
        outcome.record.session_id,
        user_data[0],
        user_data[1],
        manifest=outcome.manifest.to_dict(),
        source_incident_id=incident_id,
    )
    try:
        archive_path = store.write_archive_atomic(
            incident_id, record.session_id, record.build_number, outcome.zip_bytes
        )
    except Exception as exc:
        store.set_status(
            incident_id,
            record.session_id,
            record.build_number,
            "FAILED",
            error=str(exc),
            failure_code="archive_write_failed",
        )
        logger.exception(f"Could not write the session archive for {incident_id}")
        raise HTTPException(status_code=500, detail={"error": "session_archive_write_failed"})

    record.storage_locator = str(archive_path)
    record.session_sha256 = SessionStore.sha256_path(archive_path)
    record.size = archive_path.stat().st_size
    record.status = "READY"
    record.manifest = outcome.manifest.to_dict()
    store.update_record(record)

    await _audit(
        request,
        auth_store,
        user,
        user_data[1],
        "session.build",
        incident_id,
        "allow",
        f"Session {record.session_id} built",
    )

    return {
        "status": "READY",
        "incident_id": incident_id,
        "session_id": record.session_id,
        "build_number": record.build_number,
        "session_sha256": record.session_sha256,
        "size": record.size,
        "safe_filename": record.safe_filename,
        "manifest": record.manifest,
        "missing": outcome.missing,
        "warnings": outcome.warnings,
        "created_at": record.created_at,
    }


@router.get("/{incident_id}", name="list_session_packages")
async def list_session_packages(
    request: Request,
    incident_id: str,
    user_data: tuple = Depends(get_current_user),
) -> Dict[str, Any]:
    """List the session packages recorded for an incident, newest first."""
    incident = _ensure_incident(incident_id)
    await _authorize(request, incident, user_data, "session.list", "incident:read")

    store = SessionStore()
    records = store.list_for_incident(incident_id)
    return {
        "incident_id": incident_id,
        "count": len(records),
        "sessions": [record.to_dict() for record in records],
    }


@router.get("/{incident_id}/download", name="download_session_package")
async def download_session_package(
    request: Request,
    incident_id: str,
    user_data: tuple = Depends(get_current_user),
) -> FileResponse:
    """Download the newest ready session package for an incident."""
    incident = _ensure_incident(incident_id)
    await _authorize(request, incident, user_data, "session.download", "evidence:read")

    store = SessionStore()
    record = store.latest_ready(incident_id)
    if record is None or not record.storage_locator:
        raise HTTPException(
            status_code=404,
            detail={"error": "session_not_found", "incident_id": incident_id},
        )

    archive_path = Path(record.storage_locator)
    if not archive_path.exists():
        raise HTTPException(
            status_code=410,
            detail={"error": "session_archive_missing", "incident_id": incident_id},
        )

    filename = record.safe_filename or archive_path.name
    return FileResponse(
        path=archive_path,
        media_type="application/zip",
        filename=filename,
        headers={"X-Session-SHA256": record.session_sha256},
    )
