"""
FastAPI router for repair-package generation and download.

This router replaces the in-line ``download-patch-package`` endpoint logic with
a strict, store-backed implementation.  The old endpoint is kept as a thin
backward-compatible shim that delegates here.

Endpoint summary:

* ``GET /api/v1/incidents/{incident_id}/repair-packages``
    List package states for an incident (requires ownership / admin).
* ``POST /api/v1/incidents/{incident_id}/repair-packages``
    Request a new package build (requires ownership / admin).
* ``GET /api/v1/incidents/{incident_id}/repair-packages/{repair_id}``
    Get the status of a single package.
* ``GET /api/v1/incidents/{incident_id}/repair-packages/{repair_id}/download``
    Download the validated package archive (streamed, with checksums).

All endpoints enforce:
* Authentication (Bearer / Cookie / Query token).
* Incident access (404 / 403 + audit log on denial).
* Explicit candidate selection (no implicit fallback).
* Verification gate (422 for unverified candidates).
* Capibility refusal gate (422 when honest repair is refused).
* Package readiness (409 building, 500 failed, 404 not ready).
* Tamper-evident download (X-Checksum-SHA256 validated against archive).
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
)

from cauveris.api.deps import get_current_user
from cauveris.auth import get_auth_store, AuditLogEntry
from cauveris.packaging import PackageBuilder, PackageStore
from cauveris.packaging.models import (
    PACKAGE_ERRORS,
    PackageError,
    PackageStatus,
    RepairPackageRecord,
    VerificationLevel,
    compute_verification_level,
)
from cauveris.packaging.validation import validate_package_archive
from cauveris.state_machine.orchestrator import WorkflowStatus, pipeline_contexts, pipeline_tasks
from cauveris.schemas.patch import PatchCandidate, VerificationReport

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["repair-packages"],
)

_SAFE_NAME_RE = re.compile(r"^([A-Za-z0-9._-]+)$")


def _safe_name(value: str) -> str:
    text = str(value).strip().replace("/", "_").replace("\\", "_")
    text = re.sub(r"[^A-Za-z0-9._-]", "_", text)
    return text[:128] or "unknown"


def _ensure_incident(request: Request, incident_id: str) -> Any:
    """Resolve an incident by id, raising 404 if absent."""
    from cauveris.api.main import _ensure_incident as _resolve  # local import to avoid cycle

    try:
        return _resolve(incident_id)
    except AttributeError:
        # Fallback if the helper signature differs.
        from cauveris.api.main import incidents

        return incidents.get(incident_id)


# ---------------------------------------------------------------------------
# Incident-level package queries
# ---------------------------------------------------------------------------


@router.get(
    "/{incident_id}/repair-packages",
    response_model=None,
    name="list_repair_packages",
)
async def list_repair_packages(
    request: Request,
    incident_id: str,
    user_data: tuple = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    List all package builds for an incident.

    Returns the latest build per repair_id, with status, checksum, and
    verification level.  Requires ownership or admin.
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail={"error": "auth_store_unavailable"})

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail={"error": "user_not_found"})

    incident = _ensure_incident(request, incident_id)
    if not incident:
        raise HTTPException(
            status_code=404,
            detail={"error": "incident_not_found", "incident_id": incident_id},
        )

    # Access control.
    owner_user = getattr(incident, "_owner_user_id", None)
    owner_org = getattr(incident, "_owner_org_id", None)
    is_admin = getattr(user, "is_superuser", False) or user.has_permission("*")
    if not is_admin:
        if owner_org and owner_org != org_id:
            await auth_store.write_audit_log(
                AuditLogEntry(
                    user_id=user.id,
                    org_id=org_id,
                    action="repair_package.list",
                    resource_type="incident",
                    resource_id=incident_id,
                    resource_owner_id=owner_user,
                    decision="deny",
                    reason="Cross-organization incident access denied",
                    ip_address=request.client.host if request.client else "unknown",
                    user_agent=request.headers.get("User-Agent", ""),
                )
            )
            raise HTTPException(
                status_code=403,
                detail={"error": "access_denied", "incident_id": incident_id},
            )
        if owner_user and owner_user != user_id and not user.has_permission("patch:read"):
            await auth_store.write_audit_log(
                AuditLogEntry(
                    user_id=user.id,
                    org_id=org_id,
                    action="repair_package.list",
                    resource_type="incident",
                    resource_id=incident_id,
                    resource_owner_id=owner_user,
                    decision="deny",
                    reason="Not authorized to list repair packages",
                    ip_address=request.client.host if request.client else "unknown",
                    user_agent=request.headers.get("User-Agent", ""),
                )
            )
            raise HTTPException(
                status_code=403,
                detail={"error": "access_denied", "incident_id": incident_id},
            )

    # Audit allow.
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=org_id,
            action="repair_package.list",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            reason=f"Listed repair packages for incident {incident_id}",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
        )
    )

    store = PackageStore()
    return _build_package_summary(store, str(incident.id))


def _build_package_summary(
    store: PackageStore, incident_id: str
) -> Dict[str, Any]:
    """Build a per-repair-id summary of package builds for an incident."""
    incident_key = _safe_name(incident_id)
    summary: Dict[str, Any] = {"incident_id": incident_id, "packages": []}
    seen_repair_ids: Dict[str, RepairPackageRecord] = {}

    for key, bucket in store.index["packages"].items():
        if not key.startswith(f"{incident_key}::"):
            continue
        for entry in bucket.get("history", []):
            rec = RepairPackageRecord.from_dict(entry)
            prev = seen_repair_ids.get(rec.repair_id)
            if prev is None or rec.build_number > prev.build_number:
                seen_repair_ids[rec.repair_id] = rec

    for repair_id, rec in sorted(seen_repair_ids.items()):
        summary["packages"].append(
            {
                "repair_id": repair_id,
                "build_number": rec.build_number,
                "package_id": rec.package_id,
                "status": rec.status.value,
                "verification_level": rec.verification_level,
                "checksum_sha256": rec.checksum_sha256,
                "size_bytes": rec.size_bytes,
                "created_at": rec.created_at,
                "ready_at": rec.ready_at,
                "error": rec.error,
                "is_downloadable": rec.is_downloadable,
            }
        )

    return summary


# ---------------------------------------------------------------------------
# Build a single repair package
# ---------------------------------------------------------------------------


@router.post(
    "/{incident_id}/repair-packages",
    response_model=None,
    name="request_repair_package",
)
async def request_repair_package(
    request: Request,
    incident_id: str,
    repair_id: str = Query(..., description="The repair candidate ID to package"),
    user_data: tuple = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Build a verified repair package for an explicit repair candidate.

    Requires ownership or admin.  Returns the package record's status.
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail={"error": "auth_store_unavailable"})

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail={"error": "user_not_found"})

    incident = _ensure_incident(request, incident_id)
    if not incident:
        raise HTTPException(
            status_code=404,
            detail={"error": "incident_not_found", "incident_id": incident_id},
        )

    # Access control (same as list).
    owner_user = getattr(incident, "_owner_user_id", None)
    owner_org = getattr(incident, "_owner_org_id", None)
    is_admin = getattr(user, "is_superuser", False) or user.has_permission("*")
    if not is_admin:
        if owner_org and owner_org != org_id:
            raise HTTPException(
                status_code=403,
                detail={"error": "access_denied", "incident_id": incident_id},
            )
        if owner_user and owner_user != user_id and not user.has_permission("patch:read"):
            raise HTTPException(
                status_code=403,
                detail={"error": "access_denied", "incident_id": incident_id},
            )

    # Check for capability refusal.
    cap_report = getattr(incident, "capability_report", None)
    if cap_report and cap_report.get("honest_repair_decision") == "REFUSE":
        raise HTTPException(
            status_code=422,
            detail={
                "error": "repair_refused",
                "message": "Automatic repair is unsupported for this incident bundle",
                "incident_id": incident_id,
                "limitations": cap_report.get("limitations", []),
            },
        )

    # Resolve candidates.
    ctx = pipeline_contexts.get(incident_id)
    candidates: List[PatchCandidate] = (
        getattr(ctx, "patch_candidates", None) if ctx else None
    ) or getattr(incident, "patch_candidates", []) or []

    target = None
    for c in candidates:
        if getattr(c, "candidate_id", None) == repair_id:
            target = c
            break

    if not target:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "repair_candidate_not_found",
                "message": f"Repair candidate '{repair_id}' not found for incident '{incident_id}'",
                "incident_id": incident_id,
                "repair_id": repair_id,
            },
        )

    # Verification gate.
    if not getattr(target, "verified", False):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unverified_repair_candidate",
                "message": (
                    f"Repair candidate '{repair_id}' has not passed invariant verification. "
                    "Only verified repairs can be packaged."
                ),
                "incident_id": incident_id,
                "repair_id": repair_id,
            },
        )

    # Check if a build is already in progress.
    store = PackageStore()
    latest = store.get_latest(incident_id, repair_id)
    if latest and latest.status == PackageStatus.BUILDING:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "package_building",
                "message": "A package build is already in progress for this repair candidate",
                "incident_id": incident_id,
                "repair_id": repair_id,
            },
        )

    # Check pipeline state.
    orch = pipeline_tasks.get(incident_id)
    if orch and orch.is_running():
        raise HTTPException(
            status_code=409,
            detail={
                "error": "pipeline_running",
                "message": "Investigation pipeline is currently active",
                "incident_id": incident_id,
                "workflow_status": getattr(orch, "workflow_status", "RUNNING"),
            },
        )

    if ctx and getattr(ctx, "workflow_status", None) == WorkflowStatus.PACKAGE_FAILED:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "package_failed",
                "message": f"Package creation failed: {ctx.package_error or 'Unknown error'}",
                "incident_id": incident_id,
                "repair_id": repair_id,
            },
        )

    # Build the package.
    builder = PackageBuilder(settings=store.settings)
    experiment = _experiment_for_patch(target, getattr(ctx, "experiments", None) if ctx else None)
    system_model = getattr(ctx, "_system_model_cache", None) or getattr(ctx, "system_model", None)
    if system_model is None and ctx:
        try:
            from cauveris.analysis.system_model import get_system_model

            bundle = builder._resolve_bundle(incident)
            if bundle is not None:
                system_model = get_system_model(str(incident.id), bundle)
        except Exception:
            system_model = None

    try:
        outcome = await builder.build(
            incident=incident,
            patch=target,
            user_id=user_id,
            org_id=org_id,
            experiment=experiment,
            hypotheses=getattr(ctx, "hypotheses", []) if ctx else [],
            verification_reports=getattr(ctx, "verification_reports", []) if ctx else [],
            system_model=system_model,
        )
    except PackageError as exc:
        # Re-raise known package errors.
        await auth_store.write_audit_log(
            AuditLogEntry(
                user_id=user.id,
                org_id=org_id,
                action="repair_package.build",
                resource_type="incident",
                resource_id=incident_id,
                resource_owner_id=owner_user,
                decision="deny",
                reason=f"Package build failed: {exc.error_code}",
                ip_address=request.client.host if request.client else "unknown",
                user_agent=request.headers.get("User-Agent", ""),
            )
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": exc.error_code,
                "message": exc.detail,
                "incident_id": incident_id,
                "repair_id": repair_id,
            },
        )

    # Audit success.
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=org_id,
            action="repair_package.build",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            reason=(
                f"Built package build#{outcome.build_number} for {repair_id} "
                f"(sha256:{outcome.package_checksum[:12]})"
            ),
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
        )
    )

    return {
        "incident_id": incident_id,
        "repair_id": repair_id,
        "build_number": outcome.build_number,
        "package_id": f"pkg_{incident_id}_{repair_id}_{outcome.build_number}",
        "status": PackageStatus.READY.value,
        "verification_level": outcome.manifest.get("verification_level"),
        "checksum_sha256": outcome.package_checksum,
        "size_bytes": outcome.size_bytes,
        "download_url": f"/api/v1/incidents/{incident_id}/repair-packages/{repair_id}/download",
    }


def _experiment_for_patch(
    patch: PatchCandidate, experiments: Optional[List[Any]]
) -> Optional[Any]:
    """Find the experiment a patch was generated from."""
    if not experiments:
        return None
    exp_id = patch.candidate_id
    if exp_id.startswith("patch-"):
        exp_id = exp_id[len("patch-"):]
    for e in experiments:
        if getattr(e, "experiment_id", None) == exp_id:
            return e
    return None


# ---------------------------------------------------------------------------
# Get single package status
# ---------------------------------------------------------------------------


@router.get(
    "/{incident_id}/repair-packages/{repair_id}",
    response_model=None,
    name="get_repair_package",
)
async def get_repair_package(
    request: Request,
    incident_id: str,
    repair_id: str,
    user_data: tuple = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get the status of the latest package for a repair candidate."""
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail={"error": "auth_store_unavailable"})

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail={"error": "user_not_found"})

    incident = _ensure_incident(request, incident_id)
    if not incident:
        raise HTTPException(
            status_code=404,
            detail={"error": "incident_not_found", "incident_id": incident_id},
        )

    _check_access(request, incident, user_id, org_id, user, "repair_package.get", incident_id)

    store = PackageStore()
    record = store.get_latest(incident_id, repair_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "package_not_found",
                "message": f"No package found for repair candidate '{repair_id}'",
                "incident_id": incident_id,
                "repair_id": repair_id,
            },
        )

    return _record_to_response(record)


def _record_to_response(rec: RepairPackageRecord) -> Dict[str, Any]:
    return {
        "incident_id": rec.incident_id,
        "repair_id": rec.repair_id,
        "build_number": rec.build_number,
        "package_id": rec.package_id,
        "status": rec.status.value,
        "verification_level": rec.verification_level,
        "checksum_sha256": rec.checksum_sha256,
        "size_bytes": rec.size_bytes,
        "created_at": rec.created_at,
        "ready_at": rec.ready_at,
        "error": rec.error,
        "is_downloadable": rec.is_downloadable,
        "download_url": (
            f"/api/v1/incidents/{rec.incident_id}/repair-packages/{rec.repair_id}/download"
            if rec.is_downloadable
            else None
        ),
    }


def _check_access(
    request: Request,
    incident: Any,
    user_id: str,
    org_id: str,
    user: Any,
    action: str,
    incident_id: str,
) -> None:
    """Enforce ownership / admin / permission access. Raises HTTPException on denial."""
    auth_store = get_auth_store()
    owner_user = getattr(incident, "_owner_user_id", None)
    owner_org = getattr(incident, "_owner_org_id", None)
    is_admin = getattr(user, "is_superuser", False) or user.has_permission("*")

    if not is_admin:
        if owner_org and owner_org != org_id:
            _deny(auth_store, user, org_id, action, incident_id, owner_user,
                  request, "Cross-organization incident access denied")
            raise HTTPException(status_code=403, detail={"error": "access_denied", "incident_id": incident_id})
        if owner_user and owner_user != user_id and not user.has_permission("patch:read"):
            _deny(auth_store, user, org_id, action, incident_id, owner_user,
                  request, "Not authorized to access repair package")
            raise HTTPException(status_code=403, detail={"error": "access_denied", "incident_id": incident_id})


async def _deny(auth_store, user, org_id, action, incident_id, owner_user, request, reason):
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=org_id,
            action=action,
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="deny",
            reason=reason,
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
        )
    )


# ---------------------------------------------------------------------------
# Download a validated package
# ---------------------------------------------------------------------------


@router.get(
    "/{incident_id}/repair-packages/{repair_id}/download",
    response_model=None,
    name="download_repair_package",
)
async def download_repair_package(
    request: Request,
    incident_id: str,
    repair_id: str,
    user_data: tuple = Depends(get_current_user),
) -> Response:
    """
    Download a validated, tamper-evident repair package archive.

    The archive is re-validated on every download.  If the on-disk bytes have
    been modified since the record was written, the download is refused with
    500.
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail={"error": "auth_store_unavailable"})

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail={"error": "user_not_found"})

    incident = _ensure_incident(request, incident_id)
    if not incident:
        raise HTTPException(
            status_code=404,
            detail={"error": "incident_not_found", "incident_id": incident_id},
        )

    _check_access(request, incident, user_id, org_id, user, "patch.download", incident_id)

    # Check pipeline state for 409/500.
    _check_pipeline_state(request, incident_id, auth_store, user, user_id, org_id, repair_id)

    store = PackageStore()
    record = store.get_latest(incident_id, repair_id)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "package_not_found",
                "message": f"No package found for repair candidate '{repair_id}'",
                "incident_id": incident_id,
                "repair_id": repair_id,
            },
        )

    if record.status == PackageStatus.BUILDING:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "package_building",
                "message": "Repair package is currently being built",
                "incident_id": incident_id,
                "repair_id": repair_id,
            },
        )

    if record.status == PackageStatus.FAILED:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "package_failed",
                "message": f"Package build failed: {record.error or 'Unknown error'}",
                "incident_id": incident_id,
                "repair_id": repair_id,
            },
        )

    if record.status == PackageStatus.STALE:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "package_stale",
                "message": "A newer repair package exists for this incident",
                "incident_id": incident_id,
                "repair_id": repair_id,
            },
        )

    if not record.is_downloadable:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "package_not_ready",
                "message": "No ready repair package is available for download",
                "incident_id": incident_id,
                "repair_id": repair_id,
            },
        )

    # Re-validate on download: the archive must not have been tampered with.
    zip_path = Path(record.zip_path) if record.zip_path else None
    if not zip_path or not zip_path.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "error": "package_archive_missing",
                "message": "Package archive file is missing from disk",
                "incident_id": incident_id,
                "repair_id": repair_id,
            },
        )

    zip_bytes = zip_path.read_bytes()

    # Re-check the checksum matches what the record claims.
    actual_sha256 = hashlib.sha256(zip_bytes).hexdigest()
    if actual_sha256 != record.checksum_sha256:
        await auth_store.write_audit_log(
            AuditLogEntry(
                user_id=user.id,
                org_id=user.org_id,
                action="patch.download",
                resource_type="incident",
                resource_id=incident_id,
                resource_owner_id=getattr(incident, "_owner_user_id", None),
                decision="deny",
                reason=f"Tamper detected: archive checksum {actual_sha256[:12]} != record {record.checksum_sha256[:12]}",
                ip_address=request.client.host if request.client else "unknown",
                user_agent=request.headers.get("User-Agent", ""),
            )
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "package_tampered",
                "message": "Package archive failed integrity check (checksum mismatch)",
                "incident_id": incident_id,
                "repair_id": repair_id,
            },
        )

    # Validate the archive's internal structure.
    vreport = validate_package_archive(zip_bytes)
    if not vreport.ok:
        raises = "; ".join(
            f"{f.code}({f.member}): {f.detail}" for f in vreport.failures
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "package_corrupt",
                "message": f"Package archive failed validation: {raises}",
                "incident_id": incident_id,
                "repair_id": repair_id,
            },
        )

    # Audit the successful download.
    owner_user = getattr(incident, "_owner_user_id", None)
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="patch.download",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            reason=(
                f"Downloaded verified repair package build#{record.build_number} "
                f"for candidate {repair_id} (sha256:{actual_sha256[:12]})"
            ),
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
        )
    )

    safe_incident = _safe_name(incident_id)
    safe_repair = _safe_name(repair_id)
    download_name = f"cauveris-repair-package-{safe_incident}-{safe_repair}.zip"

    headers = {
        "Content-Length": str(len(zip_bytes)),
        "X-Checksum-SHA256": actual_sha256,
        "X-Repair-ID": str(repair_id),
        "X-Incident-ID": str(incident_id),
        "X-Build-Number": str(record.build_number),
        "X-Verification-Level": record.verification_level,
        "Content-Disposition": f'attachment; filename="{download_name}"',
    }

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers=headers,
    )


def _check_pipeline_state(
    request: Request,
    incident_id: str,
    auth_store,
    user,
    user_id: str,
    org_id: str,
    repair_id: str,
) -> None:
    """Check the pipeline's current state and raise 409/500 if appropriate."""
    ctx = pipeline_contexts.get(incident_id)
    orch = pipeline_tasks.get(incident_id)

    if ctx and getattr(ctx, "workflow_status", None) == WorkflowStatus.PACKAGE_BUILDING:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "package_building",
                "message": "Repair package is currently being built",
                "incident_id": incident_id,
                "repair_id": repair_id,
                "workflow_status": "PACKAGE_BUILDING",
            },
        )

    if ctx and getattr(ctx, "workflow_status", None) == WorkflowStatus.PACKAGE_FAILED:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "package_failed",
                "message": f"Package creation failed: {ctx.package_error or 'Unknown error'}",
                "incident_id": incident_id,
                "repair_id": repair_id,
            },
        )
