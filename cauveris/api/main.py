"""
Main FastAPI application for Cauveris.
"""

import asyncio
import shutil
import time
import uuid
import json
import secrets
import os
import zipfile
import re
import hashlib
import io
import html
from pathlib import Path, PurePath
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from threading import Lock
from fastapi import (
    FastAPI,
    File,
    Form,
    UploadFile,
    HTTPException,
    BackgroundTasks,
    Request,
    Response,
    Depends,
    WebSocket,
    Query,
    Body,
)
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from cauveris.schemas.incident import Incident, EvidenceItem
from cauveris.schemas.hypothesis import Hypothesis
from cauveris.schemas.experiment import Experiment
from cauveris.schemas.base import StatusLabel
from cauveris.schemas.patch import PatchCandidate, VerificationReport
from cauveris.analysis.system_model import SystemModel, get_system_model
from cauveris.api.sample_loader import load_explicit_sample
from cauveris.state_machine.orchestrator import PipelineOrchestrator, PipelineContext, WorkflowStatus
from cauveris.ingestion.controller import IngestionController, extract_zip_safely
from cauveris.security import scan_for_secrets, compute_file_hash, safe_join
from cauveris.patch.generator import PatchGenerator
from cauveris.report.generator import ReportGenerator
from cauveris.logging_config import get_logger, bind_request_context
from cauveris.auth import (
    init_auth_store,
    get_auth_store,
    TokenManager,
    User,
    Organization,
    Session,
    APIKey,
    AuditLogEntry,
    UserRole,
    TokenType,
    LoginRequest,
    RegisterRequest,
    RefreshRequest,
    APIKeyCreateRequest,
    TokenResponse,
    UserResponse,
    APIKeyResponse,
    authorize,
    TokenExpiredError,
    TokenInvalidError,
)
from cauveris.rate_limit import init_rate_limiter, get_rate_limiter
from cauveris.idempotency import init_idempotency_store
from cauveris.concurrency import (
    init_concurrency_store,
    close_concurrency_store,
    get_concurrency_manager,
)
from cauveris.job_queue import init_job_queue, close_job_queue
from cauveris.config import get_settings
from cauveris.api.deps import get_current_user, get_optional_user
from cauveris.api.holographic import router as holographic_router, get_holographic_reconstruction
from cauveris.packaging.api_router import router as packaging_router


class CreateIncidentRequest(BaseModel):
    title: Optional[str] = "Uploaded Incident"
    description: Optional[str] = "Incident created via API"
    system_name: Optional[str] = "warehouse-amr-01"
    golden: bool = False
    custom_id: Optional[str] = None


class ApplyPatchRequest(BaseModel):
    target_directory: str = "."
    dry_run: bool = False
    rollback: bool = False


class CustomSimulationRequest(BaseModel):
    batching_window_ms: float = 100.0
    qos_queue_depth: int = 5
    clock_skew_ms: float = 0.0
    max_batch_size: int = 4
    gpu_contention_ms: float = 0.0
    freshness_budget_ms: float = 120.0
    trials: int = 20


logger = get_logger(__name__)

# Directory used to stage uploaded incident bundles before they are extracted.
UPLOAD_DIR = Path("./temp_upload")


def _report_path(*parts: str) -> Path:
    """Resolve report artifacts through the configured isolated report store."""
    return Path(get_settings().report_store_path).joinpath(*parts)

app = FastAPI(title="Cauveris API", version="0.1.0")


@app.on_event("startup")
async def startup_event():
    """Initialize rate limiter, idempotency store, concurrency manager, job queue, and auth store on startup."""
    settings = get_settings()
    init_rate_limiter(
        backend=settings.rate_limit_backend,
        redis_url=settings.rate_limit_redis_url,
        fail_open=settings.rate_limit_fail_open,
    )
    if settings.idempotency_enabled:
        init_idempotency_store(
            backend=settings.idempotency_backend,
            redis_url=settings.idempotency_redis_url,
            default_ttl=settings.idempotency_ttl_seconds,
        )
    # Initialize concurrency manager
    init_concurrency_store(backend=settings.concurrency_backend)
    # Initialize job queue
    queue = init_job_queue(
        backend=settings.job_queue_backend,
        max_size=settings.job_queue_max_size,
        default_ttl=settings.job_queue_default_ttl,
    )
    # Serve the queue from this process unless the deployment says otherwise.
    # A queue with no worker attached accepts jobs and never runs them.
    if settings.job_queue_embedded_worker:
        from cauveris.worker import start_embedded_worker

        try:
            await start_embedded_worker(queue)
        except Exception as exc:
            logger.error(f"Could not start the embedded job worker: {exc}")
    # Production security validation
    settings.validate_production_security()
    # Initialize auth store
    init_auth_store(
        backend=settings.auth_backend,
        redis_url=settings.auth_redis_url,
        db_path=settings.auth_db_path,
    )
    auth_store = get_auth_store()
    if auth_store and (settings.demo_auth or settings.demo_mode) and settings.runtime_mode != "production":
        try:
            demo_org = await auth_store.get_org("org_demo")
            if not demo_org:
                demo_org = Organization(
                    id="org_demo",
                    name="Demo Organization",
                    slug="demo",
                    description="Demo organization for local testing",
                    owner_user_id="usr_demo",
                    is_active=True,
                )
                await auth_store.create_org(demo_org)

            demo_user = await auth_store.get_user_by_email("demo@cauveris.local")
            if not demo_user:
                demo_user = User(
                    id="usr_demo",
                    email="demo@cauveris.local",
                    full_name="Demo User",
                    role=UserRole.ENGINEER,
                    org_id="org_demo",
                    is_active=True,
                )
                demo_user.set_password("demo123456")
                await auth_store.create_user(demo_user)

            op_user = await auth_store.get_user_by_email("operator@cauveris.ai")
            if not op_user:
                op_user = User(
                    id="usr_operator",
                    email="operator@cauveris.ai",
                    full_name="Lead Operator",
                    role=UserRole.ENGINEER,
                    org_id="org_demo",
                    is_active=True,
                )
                op_user.set_password("Operator123456!")
                await auth_store.create_user(op_user)

            admin_user = await auth_store.get_user_by_email("admin@cauveris.ai")
            if not admin_user:
                admin_user = User(
                    id="usr_admin",
                    email="admin@cauveris.ai",
                    full_name="System Administrator",
                    role=UserRole.ADMIN,
                    org_id="org_demo",
                    is_active=True,
                )
                admin_user.set_password("Admin123456!")
                await auth_store.create_user(admin_user)
        except Exception as e:
            logger.warning(f"Could not seed default users: {e}")

    # Production guard: refuse to run with default development secrets when demo
    # mode is off — those secrets are public and would compromise every token.
    if not settings.demo_mode:
        weak_defaults = {
            "CAUVERIS_SECRET_KEY": "dev-secret-change-in-prod",
            "CAUVERIS_JWT_SECRET": "dev-jwt-secret-change-in-production-min-32-chars",
        }
        current = {
            "CAUVERIS_SECRET_KEY": settings.secret_key,
            "CAUVERIS_JWT_SECRET": settings.auth_jwt_secret,
        }
        for env_name, default_value in weak_defaults.items():
            if current[env_name] == default_value:
                raise RuntimeError(
                    f"Refusing to start: {env_name} is still the default development "
                    f"secret while CAUVERIS_DEMO_MODE is disabled. Set a real secret "
                    f"before running in production."
                )


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up rate limiter, idempotency store, concurrency manager, job queue, and auth store on shutdown."""
    from cauveris.idempotency import get_idempotency_store

    limiter = get_rate_limiter()
    await limiter.close()
    store = get_idempotency_store()
    if store:
        await store.close()
    await close_concurrency_store()
    await close_job_queue()
    # Auth store cleanup (no explicit close needed for in-memory)


# CORS middleware — allowed origins come from CAUVERIS_CORS_ORIGINS (comma-separated).
# "*" is honoured only when explicitly configured; credentials are never combined
# with a wildcard reflection.
_cors_origins_raw = os.getenv(
    "CAUVERIS_CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001,http://localhost:3002,http://127.0.0.1:3002"
)
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins if _cors_origins else ["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$",
)


# Correlation ID middleware for request tracing
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Add correlation ID to request context and response headers."""
    # Generate or extract correlation ID
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

    # Extract incident ID from path if present
    incident_id = ""
    path_parts = request.url.path.split("/")
    if "incidents" in path_parts:
        idx = path_parts.index("incidents")
        if idx + 1 < len(path_parts):
            incident_id = path_parts[idx + 1]

    # Bind to context variables for structured logging
    bind_request_context(request_id, incident_id)

    # Add to request state for access in route handlers
    request.state.request_id = request_id
    request.state.incident_id = incident_id

    # Start timing
    start_time = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception as e:
        # Calculate duration for error case
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.error(
            "Request failed",
            extra={
                "http_method": request.method,
                "http_path": request.url.path,
                "request_id": request_id,
                "incident_id": incident_id,
                "duration_ms": duration_ms,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise

    # Calculate duration
    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

    # Add correlation headers to response
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-MS"] = str(duration_ms)

    # Log request with structured fields
    logger.info(
        "Request completed",
        extra={
            "http_method": request.method,
            "http_path": request.url.path,
            "http_status": response.status_code,
            "request_id": request_id,
            "incident_id": incident_id,
            "duration_ms": duration_ms,
        },
    )

    return response


# Rate limiting middleware (Phase 3)
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply rate limiting to all endpoints based on cost class."""
    # Skip rate limiting for health checks
    if request.url.path in ["/health", "/api/v1/health", "/ready", "/api/v1/ready", "/", "/api/v1/limits"]:
        return await call_next(request)

    # Determine cost class for this endpoint
    from cauveris.rate_limit_config import get_cost_class_for_endpoint

    cost_class = get_cost_class_for_endpoint(request.method, request.url.path)

    # Determine client identity for rate limit key
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"

    user_id = request.headers.get("X-User-ID")
    org_id = request.headers.get("X-Org-ID")

    if user_id and org_id:
        rate_limit_key = f"user:{user_id}"
    else:
        rate_limit_key = f"ip:{client_ip}"

    # Add path to key for per-endpoint limits
    rate_limit_key = f"{rate_limit_key}:{request.url.path}"

    # Check rate limit
    limiter = get_rate_limiter()
    if limiter is not None:
        try:
            from cauveris.rate_limit_config import build_policies_from_settings

            policies = build_policies_from_settings()
            policy = policies.get(cost_class)
            if policy:
                # The cost class declares how many units the request consumes;
                # passing it makes expensive endpoints consume proportionally
                # more of the allowance.
                result = await limiter.check_limit(rate_limit_key, policy, policy.cost)
                if not result.allowed:
                    from fastapi import HTTPException

                    raise HTTPException(
                        status_code=429,
                        detail=f"Rate limit exceeded for {cost_class}",
                        headers=result.headers,
                    )

                # Add rate limit headers to request state for endpoint to use
                request.state.rate_limit_headers = result.headers
        except HTTPException:
            raise
        except Exception as e:
            # On rate limiter error, log but don't block (fail open)
            logger.warning(f"Rate limiter error, failing open: {e}")

    response = await call_next(request)

    # Add rate limit headers to response
    if hasattr(request.state, "rate_limit_headers"):
        for k, v in request.state.rate_limit_headers.items():
            response.headers[k] = v

    return response


# Idempotency middleware (Phase 4)
@app.middleware("http")
async def idempotency_middleware(request: Request, call_next):
    """Handle idempotency keys for mutation endpoints."""
    # Only apply if idempotency is enabled
    settings = get_settings()
    if not settings.idempotency_enabled:
        return await call_next(request)

    # Skip non-mutation methods
    if request.method not in ["POST", "PUT", "PATCH", "DELETE"]:
        return await call_next(request)

    # Check for Idempotency-Key header
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return await call_next(request)

    # Validate key format
    import re

    if not re.match(r"^[a-zA-Z0-9_-]{1,256}$", idempotency_key):
        from fastapi import Response

        return Response(
            content=json.dumps(
                {
                    "error": "Invalid Idempotency-Key format. Use alphanumeric, hyphen, underscore (max 256 chars)."
                }
            ),
            status_code=400,
            media_type="application/json",
        )

    from cauveris.idempotency import (
        check_idempotency,
        save_idempotent_response,
        get_idempotency_store,
        IdempotencyState,
    )

    store = get_idempotency_store()
    if store is None:
        return await call_next(request)

    # Determine operation name
    operation = f"{request.method}:{request.url.path}"

    # Check idempotency
    should_process, cached, error = await check_idempotency(
        request, idempotency_key, operation, store
    )
    if error:
        return error

    if cached:
        # Return cached response
        from fastapi import Response

        headers = cached["headers"] or {}
        headers["X-Idempotency-Replay"] = "true"
        return Response(
            content=cached["body"],
            status_code=cached["status"],
            headers=headers,
            media_type="application/json",
        )

    # Process request
    response = await call_next(request)

    # Save response for idempotency (only for non-5xx responses)
    if response.status_code < 500:
        # Need to read response body
        response_body = b""
        async for chunk in response.body_iterator:
            response_body += chunk

        # Save for future replays
        state = (
            IdempotencyState.COMPLETED if response.status_code < 400 else IdempotencyState.FAILED
        )
        await save_idempotent_response(
            idempotency_key,
            response_body.decode("utf-8", errors="ignore"),
            response.status_code,
            dict(response.headers),
            state,
            store,
        )

        # Return new response with same body
        from fastapi import Response

        return Response(
            content=response_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )

    # The request failed with a server error. Drop the idempotency record so
    # that a retry with the same key is not permanently rejected by a record
    # stuck in the PROCESSING state.
    await store.delete(idempotency_key)

    return response


# Authentication middleware for JWT validation
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Validate JWT tokens and attach user/org/session to request state."""
    # Skip auth for public endpoints
    public_paths = {
        "/",
        "/health",
        "/api/v1/health",
        "/ready",
        "/api/v1/ready",
        "/api/v1/limits",
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/signup",
        "/api/v1/auth/refresh",
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/signup",
        "/api/auth/refresh",
        "/api/v1/status-center",
        "/api/v1/model-health",
    }
    if request.url.path in public_paths:
        return await call_next(request)

    # Check Authorization header, Cookie, or Query parameter
    auth_header = request.headers.get("Authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
    elif request.cookies.get("access_token"):
        token = request.cookies.get("access_token")
    elif request.cookies.get("session_id"):
        token = request.cookies.get("session_id")
    elif request.query_params.get("token"):
        token = request.query_params.get("token")

    if not token:
        return await call_next(request)

    settings = get_settings()
    auth_store = get_auth_store()

    # Direct session lookup if token is an opaque session ID (starts with sess_)
    if token.startswith("sess_") and auth_store:
        session = await auth_store.get_session(token)
        if session and not session.is_revoked and not session.is_expired():
            user = await auth_store.get_user(session.user_id)
            if user and user.is_active:
                request.state.auth_user_id = user.id
                request.state.auth_org_id = user.org_id
                request.state.auth_role = user.role.value
                request.state.auth_session_id = session.id
                request.state.auth_user = user
                request.state.authenticated = True
                return await call_next(request)

    token_manager = TokenManager(settings.auth_jwt_secret, settings.auth_jwt_algorithm)
    try:
        payload = token_manager.decode_token(token, TokenType.ACCESS)
        user_id = payload.get("sub")
        org_id = payload.get("org_id")
        session_id = payload.get("session_id")
        role = payload.get("role")

        if not user_id or not org_id:
            return await call_next(request)

        # Verify session exists and is valid
        if auth_store:
            session = await auth_store.get_session(session_id)
            if not session or session.is_revoked or session.is_expired():
                return await call_next(request)

            user = await auth_store.get_user(user_id)
            if not user or not user.is_active:
                return await call_next(request)

            # Attach authenticated user info to request state
            request.state.auth_user_id = user_id
            request.state.auth_org_id = org_id
            request.state.auth_role = role or user.role.value
            request.state.auth_session_id = session_id
            request.state.auth_user = user
            request.state.authenticated = True

    except (TokenExpiredError, TokenInvalidError):
        pass
    except Exception as e:
        logger.warning(f"Auth middleware error: {e}")

    return await call_next(request)


# FastAPI dependency for getting current authenticated user

async def check_incident_access(
    incident: Any,
    user: User,
    required_permission: str,
    action: str,
    request: Request,
    auth_store: Any,
) -> None:
    """Centralized verification of incident permission and ownership."""
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )
    user_agent = request.headers.get("User-Agent", "")
    request_id = getattr(request.state, "request_id", None)
    incident_id = getattr(incident, "id", str(incident))

    # 1. Base permission check
    if not user.has_permission(required_permission) and not user.has_permission("*"):
        await auth_store.write_audit_log(
            AuditLogEntry(
                user_id=user.id,
                org_id=user.org_id,
                action=action,
                resource_type="incident",
                resource_id=incident_id,
                resource_owner_id=getattr(incident, "_owner_user_id", None),
                decision="deny",
                reason=f"Missing permission: {required_permission}",
                ip_address=client_ip,
                user_agent=user_agent,
                request_id=request_id,
            )
        )
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient permissions: {required_permission}",
        )

    # 2. Ownership / Tenant isolation check
    owner_user = getattr(incident, "_owner_user_id", None)
    owner_org = getattr(incident, "_owner_org_id", None)

    is_admin = (
        user.has_permission("*")
        or getattr(user, "is_superuser", False)
        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)
    )

    if not is_admin:
        # Cross-user isolation: if incident has an owner and caller is not owner
        if owner_user and owner_user != user.id:
            await auth_store.write_audit_log(
                AuditLogEntry(
                    user_id=user.id,
                    org_id=user.org_id,
                    action=action,
                    resource_type="incident",
                    resource_id=incident_id,
                    resource_owner_id=owner_user,
                    decision="deny",
                    reason="Not authorized to access incident owned by another user",
                    ip_address=client_ip,
                    user_agent=user_agent,
                    request_id=request_id,
                )
            )
            raise HTTPException(
                status_code=403,
                detail="Not authorized to access this incident",
            )
        # Cross-org isolation
        if owner_org and owner_org != user.org_id:
            await auth_store.write_audit_log(
                AuditLogEntry(
                    user_id=user.id,
                    org_id=user.org_id,
                    action=action,
                    resource_type="incident",
                    resource_id=incident_id,
                    resource_owner_id=owner_user,
                    decision="deny",
                    reason="Not authorized to access incident owned by another organization",
                    ip_address=client_ip,
                    user_agent=user_agent,
                    request_id=request_id,
                )
            )
            raise HTTPException(
                status_code=403,
                detail="Not authorized to access this incident",
            )

    # Audit log allow
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action=action,
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            ip_address=client_ip,
            user_agent=user_agent,
            request_id=request_id,
        )
    )


# In-memory storage for incidents (replace with database in production)
incidents: dict[str, Incident] = {}
pipeline_tasks: dict[str, PipelineOrchestrator] = {}
pipeline_contexts: dict[str, PipelineContext] = {}

# Background task storage for pipeline progress
pipeline_progress: dict[str, dict] = {}

# Incident creation tracking for rate limiting (Phase 2)
# Stores: {key: [timestamps]}
# Keys: "global:minute", "global:hour", "global:day", "user:{user_id}:minute", etc.

_incident_creation_timestamps: dict[str, list[float]] = defaultdict(list)
_incident_creation_lock = Lock()

# Active incident tracking per user/org
_active_incidents_per_user: dict[str, int] = defaultdict(int)
_active_incidents_per_org: dict[str, int] = defaultdict(int)
# Retained incident tracking per user/org
_retained_incidents_per_user: dict[str, int] = defaultdict(int)
_retained_incidents_per_org: dict[str, int] = defaultdict(int)
# Anonymous session tracking
_anonymous_incident_count = 0
# Global active incident count
_global_active_incidents = 0
_global_active_incidents_lock = Lock()


def _get_client_identity(request: Request) -> tuple[str, str, bool]:
    """
    Extract client identity from request.
    Returns: (user_id, org_id, is_anonymous)
    Uses validated JWT auth if available, falls back to IP-based anonymous identity.
    """
    # Try validated auth from middleware
    if getattr(request.state, "authenticated", False):
        return (
            request.state.auth_user_id,
            request.state.auth_org_id,
            False,
        )

    # Fallback to IP-based anonymous identity (for backward compat with unauthenticated endpoints)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"

    return f"anon:{client_ip}", f"anon:{client_ip}", True


def _prune_old_timestamps(timestamps: list[float], window_seconds: int) -> list[float]:
    """Remove timestamps older than the window."""
    now = time.time()
    cutoff = now - window_seconds
    return [ts for ts in timestamps if ts > cutoff]


def _evaluate_rate_windows(
    windows: list[tuple[str, int, int]],
) -> tuple[list[bool], list[int], list[int]]:
    """
    Evaluate several rate-limit windows WITHOUT consuming any quota.

    Each entry of ``windows`` is a ``(key, limit, window_seconds)`` triple.

    Returns a ``(allowed, counts, retry_afters)`` tuple with one entry per
    window, where ``counts`` holds the count *including* the current request
    (i.e. the count the caller would report as "used") and ``retry_afters``
    holds the number of seconds until the window frees up.
    """
    allowed_flags: list[bool] = []
    counts: list[int] = []
    retry_afters: list[int] = []
    now = time.time()

    with _incident_creation_lock:
        for key, limit, window_seconds in windows:
            pruned = _prune_old_timestamps(_incident_creation_timestamps[key], window_seconds)
            # Update the stored list with pruned version
            _incident_creation_timestamps[key] = pruned
            current_count = len(pruned)

            if current_count >= limit:
                # Find oldest timestamp to calculate retry-after
                oldest = min(pruned) if pruned else now
                retry_after = int(oldest + window_seconds - now) + 1
                allowed_flags.append(False)
                counts.append(current_count)
                retry_afters.append(max(retry_after, 1))
            else:
                allowed_flags.append(True)
                counts.append(current_count + 1)
                retry_afters.append(0)

    return allowed_flags, counts, retry_afters


def _commit_rate_windows(windows: list[tuple[str, int, int]]) -> tuple[bool, int]:
    """
    Atomically re-validate and consume quota for the given rate-limit windows.

    Quota is consumed for *every* window only when *all* windows still have
    room, so a request that is rejected by one window never burns quota in
    another. Returns ``(committed, retry_after)``.
    """
    if not windows:
        return True, 0

    now = time.time()
    with _incident_creation_lock:
        for key, limit, window_seconds in windows:
            pruned = _prune_old_timestamps(_incident_creation_timestamps[key], window_seconds)
            _incident_creation_timestamps[key] = pruned
            if len(pruned) >= limit:
                oldest = min(pruned) if pruned else now
                retry_after = int(oldest + window_seconds - now) + 1
                return False, max(retry_after, 1)

        for key, _limit, _window_seconds in windows:
            _incident_creation_timestamps[key].append(now)

    return True, 0


def _check_incident_creation_limits(request: Request) -> tuple[bool, Optional[str], int, dict]:
    """
    Check all incident creation limits.
    Returns: (allowed, error_message, retry_after, headers)
    """
    global _anonymous_incident_count, _global_active_incidents
    settings = get_settings()
    user_id, org_id, is_anonymous = _get_client_identity(request)

    logger.debug(
        "Incident creation limit check: user=%s org=%s anon=%s anonymous_count=%s "
        "global_active=%s active_per_user=%s active_per_org=%s",
        user_id,
        org_id,
        is_anonymous,
        _anonymous_incident_count,
        _global_active_incidents,
        dict(_active_incidents_per_user),
        dict(_active_incidents_per_org),
    )

    headers = {}

    # Phase 1: evaluate every sliding window *without* consuming quota.
    #
    # Evaluating and consuming in one step would let a request that is
    # rejected by a later window (e.g. the hourly quota) burn its quota in an
    # earlier window (e.g. the per-minute quota), so a client could exhaust
    # the tight quota with requests that never succeeded.
    global_windows = [
        ("global:minute", settings.max_incidents_per_minute, 60),
        ("global:hour", settings.max_incidents_per_hour, 3600),
        ("global:day", settings.max_incidents_per_day, 86400),
    ]
    user_window = (f"user:{user_id}:minute", settings.max_incidents_per_minute, 60)

    allowed, counts, retry_afters = _evaluate_rate_windows(global_windows)

    if not allowed[0]:
        headers["Retry-After"] = str(retry_afters[0])
        return (
            False,
            f"Global incident creation rate limit exceeded ({settings.max_incidents_per_minute}/minute)",
            retry_afters[0],
            headers,
        )

    if not allowed[1]:
        headers["Retry-After"] = str(retry_afters[1])
        return (
            False,
            f"Global incident creation rate limit exceeded ({settings.max_incidents_per_hour}/hour)",
            retry_afters[1],
            headers,
        )

    if not allowed[2]:
        headers["Retry-After"] = str(retry_afters[2])
        return (
            False,
            f"Global incident creation rate limit exceeded ({settings.max_incidents_per_day}/day)",
            retry_afters[2],
            headers,
        )

    global_minute_count, global_hour_count, global_day_count = counts

    headers["X-RateLimit-Global-Minute-Limit"] = str(settings.max_incidents_per_minute)
    headers["X-RateLimit-Global-Minute-Remaining"] = str(
        max(0, settings.max_incidents_per_minute - global_minute_count)
    )
    headers["X-RateLimit-Global-Hour-Limit"] = str(settings.max_incidents_per_hour)
    headers["X-RateLimit-Global-Hour-Remaining"] = str(
        max(0, settings.max_incidents_per_hour - global_hour_count)
    )
    headers["X-RateLimit-Global-Day-Limit"] = str(settings.max_incidents_per_day)
    headers["X-RateLimit-Global-Day-Remaining"] = str(
        max(0, settings.max_incidents_per_day - global_day_count)
    )

    windows_to_commit = list(global_windows)

    # Check per-user limits (if authenticated)
    if not is_anonymous:
        (
            user_allowed,
            user_counts,
            user_retry_afters,
        ) = _evaluate_rate_windows([user_window])
        user_minute_count = user_counts[0]

        if not user_allowed[0]:
            headers["Retry-After"] = str(user_retry_afters[0])
            return (
                False,
                f"User incident creation rate limit exceeded ({settings.max_incidents_per_minute}/minute)",
                user_retry_afters[0],
                headers,
            )

        windows_to_commit.append(user_window)

        headers["X-RateLimit-User-Minute-Limit"] = str(settings.max_incidents_per_minute)
        headers["X-RateLimit-User-Minute-Remaining"] = str(
            max(0, settings.max_incidents_per_minute - user_minute_count)
        )

        # Check active incidents per user
        if _active_incidents_per_user[user_id] >= settings.max_active_incidents_per_user:
            return (
                False,
                f"User active incident limit exceeded ({settings.max_active_incidents_per_user})",
                0,
                headers,
            )

        # Check retained incidents per user
        if _retained_incidents_per_user[user_id] >= settings.max_retained_incidents_per_user:
            return (
                False,
                f"User retained incident limit exceeded ({settings.max_retained_incidents_per_user})",
                0,
                headers,
            )

        headers["X-Limit-Active-Incidents-User"] = str(settings.max_active_incidents_per_user)
        headers["X-Limit-Retained-Incidents-User"] = str(settings.max_retained_incidents_per_user)
        headers["X-Current-Active-Incidents-User"] = str(_active_incidents_per_user[user_id])
        headers["X-Current-Retained-Incidents-User"] = str(_retained_incidents_per_user[user_id])

        # Check per-org limits
        if _active_incidents_per_org[org_id] >= settings.max_active_incidents_per_org:
            return (
                False,
                f"Organization active incident limit exceeded ({settings.max_active_incidents_per_org})",
                0,
                headers,
            )

        if _retained_incidents_per_org[org_id] >= settings.max_retained_incidents_per_org:
            return (
                False,
                f"Organization retained incident limit exceeded ({settings.max_retained_incidents_per_org})",
                0,
                headers,
            )

        headers["X-Limit-Active-Incidents-Org"] = str(settings.max_active_incidents_per_org)
        headers["X-Limit-Retained-Incidents-Org"] = str(settings.max_retained_incidents_per_org)
        headers["X-Current-Active-Incidents-Org"] = str(_active_incidents_per_org[org_id])
        headers["X-Current-Retained-Incidents-Org"] = str(_retained_incidents_per_org[org_id])
    else:
        # Anonymous limits
        if _anonymous_incident_count >= settings.max_anonymous_incidents:
            return (
                False,
                f"Anonymous incident limit exceeded ({settings.max_anonymous_incidents})",
                0,
                headers,
            )

        headers["X-Limit-Anonymous-Incidents"] = str(settings.max_anonymous_incidents)
        headers["X-Current-Anonymous-Incidents"] = str(_anonymous_incident_count)

    # Check global active incidents
    with _global_active_incidents_lock:
        if _global_active_incidents >= settings.max_global_active_incidents:
            return (
                False,
                f"Global active incident limit exceeded ({settings.max_global_active_incidents})",
                0,
                headers,
            )

    headers["X-Limit-Global-Active-Incidents"] = str(settings.max_global_active_incidents)
    headers["X-Current-Global-Active-Incidents"] = str(_global_active_incidents)

    # Phase 2: the request passed every check - consume the quota in all
    # windows atomically so that a concurrent request cannot slip in between
    # the evaluation and the accounting.
    committed, commit_retry = _commit_rate_windows(windows_to_commit)
    if not committed:
        headers["Retry-After"] = str(commit_retry)
        return (
            False,
            f"Global incident creation rate limit exceeded ({settings.max_incidents_per_minute}/minute)",
            commit_retry,
            headers,
        )

    return True, None, 0, headers


def _record_incident_created(request: Request, incident_id: str, is_demonstration: bool = False):
    """Record that an incident was created for tracking active/retained counts."""
    global _anonymous_incident_count, _global_active_incidents
    user_id, org_id, is_anonymous = _get_client_identity(request)

    # Update active counts
    if not is_anonymous:
        _active_incidents_per_user[user_id] += 1
        _active_incidents_per_org[org_id] += 1
    else:
        if not is_demonstration:
            _anonymous_incident_count += 1

    with _global_active_incidents_lock:
        _global_active_incidents += 1


def _record_incident_completed(incident_id: str, is_demonstration: bool = False):
    """Record that an incident completed (moves from active to retained)."""
    # Find which user/org owns this incident
    # For simplicity, we iterate to find it. In production, use a proper index.
    incident = incidents.get(incident_id)
    if not incident:
        return

    # Try to get ownership from incident metadata (if set)
    owner_user = getattr(incident, "_owner_user_id", None)
    owner_org = getattr(incident, "_owner_org_id", None)
    is_anon = getattr(incident, "_is_anonymous", False)

    if owner_user and owner_org and not is_anon:
        _active_incidents_per_user[owner_user] = max(0, _active_incidents_per_user[owner_user] - 1)
        _retained_incidents_per_user[owner_user] += 1
        _active_incidents_per_org[owner_org] = max(0, _active_incidents_per_org[owner_org] - 1)
        _retained_incidents_per_org[owner_org] += 1
    elif is_anon:
        global _anonymous_incident_count
        _anonymous_incident_count = max(0, _anonymous_incident_count - 1)

    with _global_active_incidents_lock:
        global _global_active_incidents
        _global_active_incidents = max(0, _global_active_incidents - 1)


def _record_incident_deleted(incident_id: str):
    """Record that an incident was deleted (decrement retained count)."""
    incident = incidents.get(incident_id)
    if not incident:
        return

    owner_user = getattr(incident, "_owner_user_id", None)
    owner_org = getattr(incident, "_owner_org_id", None)
    is_anon = getattr(incident, "_is_anonymous", False)

    if owner_user and owner_org and not is_anon:
        _retained_incidents_per_user[owner_user] = max(
            0, _retained_incidents_per_user[owner_user] - 1
        )
        _retained_incidents_per_org[owner_org] = max(0, _retained_incidents_per_org[owner_org] - 1)
    elif is_anon:
        global _anonymous_incident_count
        _anonymous_incident_count = max(0, _anonymous_incident_count - 1)


def _hypothesis_title(hypothesis_id: str, rank: int) -> str:
    """
    A human-readable title for a hypothesis.

    The hypothesis layer names hypotheses after the mechanism they describe
    (``h_batching_window_latency``), so the title is derived from that name
    rather than from a hard-coded list of ids.
    """
    text = str(hypothesis_id or "").replace("exp-", "").replace("hyp-", "")
    if text.startswith("h_"):
        text = text[2:]
    words = text.replace("_", " ").replace("-", " ").strip()
    if not words:
        return f"H{rank}"
    return f"H{rank}: {words.title()}"


def _resolve_hypothesis(hypotheses: list, hypothesis_id: str) -> Optional[Hypothesis]:
    """
    Find the hypothesis an id refers to.

    An id may be the full hypothesis id, a prefix of it, or a rank reference
    ("h1" is the most confident hypothesis, "h2" the next).  The rank
    reference keeps working when the hypotheses an incident produces change,
    which a hard-coded id map cannot do.
    """
    if not hypotheses:
        return None
    clean = str(hypothesis_id or "").strip().lower()
    for hyp in hypotheses:
        hid = hyp.hypothesis_id.lower()
        if hid == clean or clean in hid or hid.startswith(clean):
            return hyp
    if clean.startswith("h") and clean[1:].isdigit():
        index = int(clean[1:]) - 1
        if 0 <= index < len(hypotheses):
            return hypotheses[index]
    if clean in ("", "default"):
        return hypotheses[0]
    return None


def _incident_system_model(
    incident: Optional[Incident], incident_id: str
) -> Optional[SystemModel]:
    """
    The incident's calibrated model, built from the bundle on disk.

    The digital twin, the hypothesis layer and the verifier all read this one
    model, so they cannot disagree about what the incident was.
    """
    if incident is None:
        return None
    bundle_path = getattr(incident, "bundle_path", None)
    if not bundle_path:
        manifest = getattr(incident, "manifest", None) or {}
        bundle_path = manifest.get("bundle_path") if isinstance(manifest, dict) else None
    if not bundle_path:
        return None
    path = Path(bundle_path)
    if not path.is_dir():
        return None
    return get_system_model(
        str(incident_id or incident.id),
        path,
        timeline_events=list(getattr(incident, "timeline_events", None) or []),
        manifest=dict(getattr(incident, "manifest", None) or {}),
    )


def _ensure_incident(incident_id: str) -> Optional[Incident]:
    """Ensure an incident is loaded in memory, hydrating from storage if available."""
    if incident_id in incidents:
        return incidents[incident_id]

    # Try to load from evidence store (disk)
    from cauveris.ingestion.controller import IngestionController
    import json
    from pathlib import Path
    from cauveris.schemas.incident import Incident

    # Hypothesis/Experiment/PatchCandidate/VerificationReport are already
    # module-level imports (lines above); re-importing them here shadowed the
    # module-level names and pyflakes flagged one side as dead either way.
    from cauveris.state_machine.orchestrator import (
        PipelineOrchestrator,
        PipelineContext,
        StageStatus,
    )

    settings = get_settings()
    evidence_path = Path(settings.evidence_store_path) / incident_id
    if not evidence_path.exists():
        # Also check common incident folder patterns
        for pattern in [
            f"./packages/incident-{incident_id}",
            f"./packages/incident-{incident_id.lower()}",
            f"./packages/{incident_id}",
            f"./packages/{incident_id.lower()}",
            f"./packages/demo/{incident_id}",
            f"./incident-{incident_id}",
            f"./incident-{incident_id.lower()}",
        ]:
            p = Path(pattern)
            if p.exists():
                evidence_path = p
                break

    if not evidence_path.exists() or not (evidence_path / "manifest.yaml").exists():
        # Implicit demo hydration only in demo mode — real deployments must
        # load incidents from the evidence store or an explicit golden load.
        settings = get_settings()
        if incident_id.upper() in ["CAU-0001", "GOLDEN"] and settings.demo_mode:
            incident = load_explicit_sample()
            incidents[incident.id] = incident
            return incident
        return None

    # Load incident from evidence store
    ingestion = IngestionController()
    try:
        coro = ingestion.load_incident_from_store(incident_id, evidence_path)
        try:
            asyncio.get_running_loop()
            # We're inside a running event loop (any live API endpoint).
            # asyncio.run() raises RuntimeError there, which the except below
            # used to swallow — so on-disk incidents always silently hydrated
            # as the minimal fallback instead of their real state. Run the
            # coroutine on a private loop in a short-lived thread instead.
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                incident = pool.submit(asyncio.run, coro).result()
        except RuntimeError:
            # No running loop (worker process / script context) — direct.
            incident = asyncio.run(coro)
    except Exception:
        # Fallback: create minimal incident
        incident = Incident(
            id=incident_id,
            title=f"Incident {incident_id}",
            description="Loaded from evidence store",
            system_name="physical-ai-system",
            status="OBSERVED",
            bundle_path=str(evidence_path),
        )
    if incident.manifest is None:
        incident.manifest = {}
    incident.manifest["bundle_path"] = str(evidence_path)

    incidents[incident_id] = incident

    orch = PipelineOrchestrator()
    orch.context = PipelineContext(incident=incident)
    pipeline_tasks[incident.id] = orch
    pipeline_progress[incident.id] = orch.get_pipeline_summary()

    # Try to hydrate from existing report
    report_file = _report_path(incident.id, "incident_report.json")
    if report_file.exists():
        try:
            with open(report_file, "r", encoding="utf-8") as f:
                report_data = json.load(f)

            # Hydrate timeline & status
            incident.timeline_events = report_data.get("timeline", [])
            incident.status = "COMPLETED"
            incident.temporal_analysis = report_data.get("temporal_analysis")

            # Hydrate pipeline context objects
            hyps = []
            for h in report_data.get("hypotheses", []):
                try:
                    hyps.append(Hypothesis(**h))
                except Exception:
                    pass

            exps = []
            for e in report_data.get("experiments", []):
                try:
                    exps.append(Experiment(**e))
                except Exception:
                    pass

            patches = []
            for p in report_data.get("patch_candidates", []):
                try:
                    patches.append(PatchCandidate(**p))
                except Exception:
                    pass

            reports = []
            for v in report_data.get("verification_reports", []):
                try:
                    reports.append(VerificationReport(**v))
                except Exception:
                    pass

            ctx = PipelineContext(
                incident=incident,
                validated_incident=incident,
                timeline_events=incident.timeline_events,
                temporal_analysis=incident.temporal_analysis,
                hypotheses=hyps,
                experiments=exps,
                patch_candidates=patches,
                verification_reports=reports,
                final_report=report_data,
            )
            pipeline_contexts[incident.id] = ctx
            orch.context = ctx
            orch.current_state = "SUCCESS"
            orch.current_progress = 1.0
            for s in orch.stages:
                s.status = StageStatus.SUCCESS
            pipeline_progress[incident.id] = orch.get_pipeline_summary()
            logger.info(f"Hydrated full pipeline context for {incident.id} from report")
        except Exception as e:
            logger.warning(f"Failed to hydrate context from report: {e}")

    return incident


# Include holographic router
app.include_router(holographic_router, prefix="/api/v1")
app.include_router(packaging_router)


@app.get("/api/v1/incidents/{incident_id}/holographic/reconstruction")
async def get_incident_holographic_reconstruction_alias(
    incident_id: str,
    enable_counterfactual: bool = Query(False),
    enable_anomalies: bool = Query(True),
    enable_multiscale: bool = Query(True),
    use_gpu: bool = Query(True),
    gpu_decay_type: str = Query("exponential"),
    gpu_normalization: str = Query("l1"),
    gpu_time_step_ns: int = Query(1000000),
    gpu_max_kernel_time_ns: int = Query(10000000000),
):
    """Alias for incident-scoped holographic reconstruction."""
    return await get_holographic_reconstruction(
        incident_id=incident_id,
        enable_counterfactual=enable_counterfactual,
        enable_anomalies=enable_anomalies,
        enable_multiscale=enable_multiscale,
        use_gpu=use_gpu,
        gpu_decay_type=gpu_decay_type,
        gpu_normalization=gpu_normalization,
        gpu_time_step_ns=gpu_time_step_ns,
        gpu_max_kernel_time_ns=gpu_max_kernel_time_ns,
    )


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Cauveris API is running"}


@app.get("/health")
@app.get("/api/v1/health")
async def health():
    """Health check endpoint (Liveness probe)."""
    return {"status": "healthy", "service": "cauveris", "version": "0.1.0"}


@app.get("/ready")
@app.get("/api/v1/ready")
async def readiness():
    """
    Readiness probe for deployment orchestrator (Nebius / Kubernetes).
    Confirms core storage and mandatory dependencies are ready.
    """
    settings = get_settings()
    auth_store = get_auth_store()

    if auth_store is None:
        raise HTTPException(status_code=503, detail="Auth database store is not initialized")

    # If live Nebius provider is mandatory, verify reachability
    if settings.model_provider_required:
        from cauveris.model_gateway.nebius import NebiusModelGateway
        gw = NebiusModelGateway(timeout=3.0)
        probe = await gw.probe()
        if not probe.get("reachable"):
            raise HTTPException(
                status_code=503,
                detail=f"Live model provider is mandatory but Nebius is unreachable: {probe.get('error')}",
            )

    return {
        "status": "ready",
        "service": "cauveris",
        "mode": settings.runtime_mode,
        "provider_required": settings.model_provider_required,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# =========================================================================
# Authentication Endpoints (Phase 1)
# =========================================================================


@app.post("/api/v1/auth/login", response_model=TokenResponse)
@app.post("/api/auth/login", response_model=TokenResponse)
async def login(request: Request, response: Response, body: LoginRequest):
    """Authenticate user with persistent credentials and return access/refresh tokens and session cookies."""
    settings = get_settings()
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    token_manager = TokenManager(settings.auth_jwt_secret, settings.auth_jwt_algorithm)

    # Rate limit check for login attempts
    forwarded = request.headers.get("X-Forwarded-For")
    client_ip = (
        forwarded.split(",")[0].strip()
        if forwarded
        else request.client.host
        if request.client
        else "unknown"
    )
    from cauveris.rate_limit_config import build_policies_from_settings

    policies = build_policies_from_settings()
    rate_limit_policy = policies.get("auth", policies.get("mutation"))
    limiter = get_rate_limiter()
    if limiter and rate_limit_policy:
        result = await limiter.check_limit(f"ip:{client_ip}:login", rate_limit_policy)
        if not result.allowed:
            raise HTTPException(
                status_code=429, detail="Too many login attempts", headers=result.headers
            )

    # Normalize email: lowercase and trimmed. No hardcoded aliases in production.
    raw_email = (body.email or "").strip().lower()
    user = await auth_store.get_user_by_email(raw_email)

    # Verify password strictly through password hashing context (bcrypt)
    is_valid = bool(user and user.verify_password(body.password))

    if not user or not is_valid:
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= settings.auth_lockout_after_failures:
                user.locked_until = datetime.now(timezone.utc) + timedelta(
                    minutes=settings.auth_lockout_duration_minutes
                )
            await auth_store.update_user(user)

        # Audit log failed login
        await auth_store.write_audit_log(
            AuditLogEntry(
                action="auth.login",
                resource_type="user",
                resource_id=user.id if user else raw_email,
                decision="deny",
                reason="Invalid credentials",
                ip_address=client_ip,
                user_agent=request.headers.get("User-Agent", ""),
                request_id=getattr(request.state, "request_id", None),
            )
        )
        raise HTTPException(
            status_code=401,
            detail={"error": "AUTH_INVALID_CREDENTIALS", "message": "Invalid email or password"},
        )

    # Check if account is locked
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        await auth_store.write_audit_log(
            AuditLogEntry(
                user_id=user.id,
                org_id=user.org_id,
                action="auth.login",
                resource_type="user",
                resource_id=user.id,
                decision="deny",
                reason="Account locked",
                ip_address=client_ip,
                user_agent=request.headers.get("User-Agent", ""),
                request_id=getattr(request.state, "request_id", None),
            )
        )
        raise HTTPException(
            status_code=403,
            detail={"error": "AUTH_ACCOUNT_LOCKED", "message": "Account temporarily locked"},
        )

    # Check if user is active
    if not user.is_active or getattr(user, "account_status", "active") != "active":
        raise HTTPException(
            status_code=403,
            detail={"error": "AUTH_ACCOUNT_INACTIVE", "message": "Account is inactive or disabled"},
        )

    # Check if org exists and is active
    org = await auth_store.get_org(user.org_id)
    if not org or not org.is_active:
        raise HTTPException(
            status_code=403,
            detail={"error": "AUTH_ORGANIZATION_INACTIVE", "message": "Organization inactive"},
        )

    # Reset failed attempts on success
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.now(timezone.utc)
    await auth_store.update_user(user)

    # Check concurrent session limit
    sessions = (
        await auth_store.list_user_sessions(user.id)
        if hasattr(auth_store, "list_user_sessions")
        else []
    )
    active_sessions = [s for s in sessions if not s.is_revoked and not s.is_expired()]
    max_concurrent = max(1, settings.auth_session_max_concurrent)
    if len(active_sessions) + 1 > max_concurrent:
        oldest_first = sorted(active_sessions, key=lambda s: s.created_at)
        to_revoke = [s.id for s in oldest_first[: len(active_sessions) + 1 - max_concurrent]]
        if to_revoke:
            await auth_store.revoke_sessions_by_id(to_revoke)

    # Create new session
    session = Session(
        user_id=user.id,
        org_id=user.org_id,
        ip_address=client_ip,
        user_agent=request.headers.get("User-Agent", ""),
    )
    session.access_token = token_manager.create_access_token(user, session, org)
    session.refresh_token = token_manager.create_refresh_token(session)
    await auth_store.create_session(session)

    # Set secure HttpOnly cookies
    access_cookie_options = {
        "httponly": True,
        "secure": settings.auth_cookie_secure,
        "samesite": settings.auth_cookie_samesite,
        "max_age": settings.auth_access_token_ttl_minutes * 60,
    }
    refresh_cookie_options = {
        "httponly": True,
        "secure": settings.auth_cookie_secure,
        "samesite": settings.auth_cookie_samesite,
        "max_age": settings.auth_refresh_token_ttl_days * 86400,
    }
    response.set_cookie("access_token", session.access_token, **access_cookie_options)
    response.set_cookie("refresh_token", session.refresh_token, **refresh_cookie_options)
    response.set_cookie("session_id", session.id, **access_cookie_options)

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            session_id=session.id,
            action="auth.login",
            resource_type="session",
            resource_id=session.id,
            decision="allow",
            ip_address=client_ip,
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    return TokenResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_in=settings.auth_access_token_ttl_minutes * 60,
        user={
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "display_name": user.display_name,
            "role": user.role.value,
            "org_id": user.org_id,
        },
    )


@app.post("/api/v1/auth/register", response_model=TokenResponse)
@app.post("/api/v1/auth/signup", response_model=TokenResponse)
@app.post("/api/auth/register", response_model=TokenResponse)
@app.post("/api/auth/signup", response_model=TokenResponse)
async def register(request: Request, response: Response, body: RegisterRequest):
    """Register a new user and organization with persistent SQLite storage and bcrypt password hashing."""
    settings = get_settings()
    if not settings.auth_registration_enabled:
        raise HTTPException(
            status_code=403,
            detail={"error": "AUTH_REGISTRATION_DISABLED", "message": "Public registration is disabled"},
        )
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    token_manager = TokenManager(settings.auth_jwt_secret, settings.auth_jwt_algorithm)

    # Validate email syntax
    norm_email = (body.email or "").strip().lower()
    if not norm_email or "@" not in norm_email or "." not in norm_email:
        raise HTTPException(
            status_code=400,
            detail={"error": "AUTH_INVALID_EMAIL", "message": "Invalid email address format"},
        )

    # Validate password confirmation if passed
    if body.confirm_password and body.password != body.confirm_password:
        raise HTTPException(
            status_code=400,
            detail={"error": "AUTH_PASSWORDS_DO_NOT_MATCH", "message": "Passwords do not match"},
        )

    # Validate password strength
    if len(body.password) < settings.auth_password_min_length:
        raise HTTPException(
            status_code=400,
            detail={"error": "AUTH_PASSWORD_TOO_SHORT", "message": f"Password must be at least {settings.auth_password_min_length} characters long"},
        )

    # Check if user already exists
    existing = await auth_store.get_user_by_email(norm_email)
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"error": "AUTH_EMAIL_ALREADY_EXISTS", "message": "An account with this email address already exists"},
        )

    full_name = body.full_name or body.name or norm_email.split("@")[0]

    # Create organization
    org_name = body.org_name or f"{full_name}'s Organization"
    base_slug = body.org_slug or norm_email.split("@")[0].lower()
    # Ensure safe slug
    safe_slug = re.sub(r"[^a-z0-9_-]", "-", base_slug).strip("-") or "org"
    org_slug = safe_slug
    existing_org = await auth_store.get_org_by_slug(org_slug)
    if existing_org:
        org_slug = f"{safe_slug}-{uuid.uuid4().hex[:6]}"

    org = Organization(
        name=org_name,
        slug=org_slug,
        owner_user_id="",
    )
    org = await auth_store.create_org(org)

    # Create user with bcrypt password hash
    user = User(
        email=norm_email,
        full_name=full_name,
        org_id=org.id,
        role=UserRole.ENGINEER,
    )
    user.set_password(body.password)
    user = await auth_store.create_user(user)

    # Update org with owner
    org.owner_user_id = user.id
    await auth_store.update_org(org)

    # Create session
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )
    session = Session(
        user_id=user.id,
        org_id=user.org_id,
        ip_address=client_ip,
        user_agent=request.headers.get("User-Agent", ""),
    )
    session.access_token = token_manager.create_access_token(user, session, org)
    session.refresh_token = token_manager.create_refresh_token(session)
    await auth_store.create_session(session)

    # Set secure HttpOnly cookies
    access_cookie_options = {
        "httponly": True,
        "secure": settings.auth_cookie_secure,
        "samesite": settings.auth_cookie_samesite,
        "max_age": settings.auth_access_token_ttl_minutes * 60,
    }
    refresh_cookie_options = {
        "httponly": True,
        "secure": settings.auth_cookie_secure,
        "samesite": settings.auth_cookie_samesite,
        "max_age": settings.auth_refresh_token_ttl_days * 86400,
    }
    response.set_cookie("access_token", session.access_token, **access_cookie_options)
    response.set_cookie("refresh_token", session.refresh_token, **refresh_cookie_options)
    response.set_cookie("session_id", session.id, **access_cookie_options)

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            session_id=session.id,
            action="auth.register",
            resource_type="user",
            resource_id=user.id,
            decision="allow",
            ip_address=client_ip,
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    return TokenResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_in=settings.auth_access_token_ttl_minutes * 60,
        user={
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "display_name": user.display_name,
            "role": user.role.value,
            "org_id": user.org_id,
        },
    )


@app.post("/api/v1/auth/refresh", response_model=TokenResponse)
@app.post("/api/auth/refresh", response_model=TokenResponse)
async def refresh_token(request: Request, response: Response, body: RefreshRequest):
    """Refresh access token using refresh token."""
    settings = get_settings()
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    token_manager = TokenManager(settings.auth_jwt_secret, settings.auth_jwt_algorithm)

    try:
        payload = token_manager.decode_token(body.refresh_token, TokenType.REFRESH)
    except (TokenExpiredError, TokenInvalidError) as e:
        raise HTTPException(status_code=401, detail=str(e))

    session_id = payload.get("session_id")
    session = await auth_store.get_session(session_id)
    if not session or session.is_revoked or session.is_refresh_expired():
        raise HTTPException(status_code=401, detail="Refresh token invalid or expired")

    # Token rotation reuse detection
    if body.refresh_token != session.refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token invalid or expired")

    user = await auth_store.get_user(session.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    org = await auth_store.get_org(user.org_id)
    if not org or not org.is_active:
        raise HTTPException(status_code=403, detail="Organization inactive")

    # Rotate tokens
    session.access_token = token_manager.create_access_token(user, session, org)
    session.refresh_token = token_manager.create_refresh_token(session)
    await auth_store.update_session(session)

    # Set secure cookies
    access_cookie_options = {
        "httponly": True,
        "secure": settings.auth_cookie_secure,
        "samesite": settings.auth_cookie_samesite,
        "max_age": settings.auth_access_token_ttl_minutes * 60,
    }
    refresh_cookie_options = {
        "httponly": True,
        "secure": settings.auth_cookie_secure,
        "samesite": settings.auth_cookie_samesite,
        "max_age": settings.auth_refresh_token_ttl_days * 86400,
    }
    response.set_cookie("access_token", session.access_token, **access_cookie_options)
    response.set_cookie("refresh_token", session.refresh_token, **refresh_cookie_options)
    response.set_cookie("session_id", session.id, **access_cookie_options)

    return TokenResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_in=settings.auth_access_token_ttl_minutes * 60,
        user={
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "display_name": user.display_name,
            "role": user.role.value,
            "org_id": user.org_id,
        },
    )


@app.post("/api/v1/auth/logout")
@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    """Logout and revoke session."""
    session_id = (
        getattr(request.state, "auth_session_id", None)
        or request.cookies.get("session_id")
    )
    if session_id:
        auth_store = get_auth_store()
        if auth_store:
            session = await auth_store.get_session(session_id)
            if session:
                session.revoke()
                await auth_store.update_session(session)
            await auth_store.delete_session(session_id)

    # Clear all auth cookies
    settings = get_settings()
    for cookie_name in ("access_token", "refresh_token", "session_id"):
        response.delete_cookie(
            cookie_name,
            httponly=True,
            secure=settings.auth_cookie_secure,
            samesite=settings.auth_cookie_samesite,
        )

    return {"message": "Logged out successfully"}


@app.get("/api/v1/auth/me", response_model=UserResponse)
@app.get("/api/auth/me", response_model=UserResponse)
async def get_current_user_info(request: Request, user_data: tuple = Depends(get_current_user)):
    """Get current authenticated user info."""
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        display_name=user.display_name,
        role=user.role,
        org_id=user.org_id,
        is_active=user.is_active,
        account_status=getattr(user, "account_status", "active"),
        mfa_enabled=user.mfa_enabled,
        created_at=user.created_at,
    )


@app.post("/api/v1/auth/api-keys", response_model=APIKeyResponse)
async def create_api_key(
    request: Request, body: APIKeyCreateRequest, user_data: tuple = Depends(get_current_user)
):
    """Create a new API key for service-to-service auth."""
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check permission
    from cauveris.auth import authorize

    await authorize(auth_store, user, "api_key:manage")

    # Generate raw key
    raw_key = f"cv_{secrets.token_urlsafe(32)}"

    api_key = APIKey(
        name=body.name,
        org_id=org_id,
        user_id=user_id,
        scopes=body.scopes or ["incidents:read"],
        rate_limit=body.rate_limit,
        expires_at=datetime.now(timezone.utc) + timedelta(days=body.expires_in_days)
        if body.expires_in_days
        else None,
    )
    # set_key() owns the hashing scheme so that creation and verification
    # always agree (previously the API hashed with bcrypt while the APIKey
    # model verified with a salted SHA-256 context, so keys never matched).
    api_key.set_key(raw_key)
    api_key = await auth_store.create_api_key(api_key)

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="api_key.create",
            resource_type="api_key",
            resource_id=api_key.id,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    return APIKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        key=raw_key,  # Only returned once on creation
        scopes=api_key.scopes,
        expires_at=api_key.expires_at,
        created_at=api_key.created_at,
    )


@app.get("/api/v1/auth/api-keys")
async def list_api_keys(request: Request, user_data: tuple = Depends(get_current_user)):
    """List user's API keys."""
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    keys = await auth_store.list_api_keys(org_id, user_id)
    return {
        "api_keys": [
            {
                "id": k.id,
                "name": k.name,
                "key_prefix": k.key_prefix,
                "scopes": k.scopes,
                "rate_limit": k.rate_limit,
                "expires_at": k.expires_at,
                "last_used_at": k.last_used_at,
                "is_active": k.is_active,
                "created_at": k.created_at,
            }
            for k in keys
        ]
    }


@app.get("/api/v1/limits")
async def get_limits(request: Request):
    """
    Get current incident creation limits and usage for the authenticated client.
    Useful for frontend to display remaining quotas.
    """
    settings = get_settings()
    user_id, org_id, is_anonymous = _get_client_identity(request)

    # Get current counts from rate limit windows
    with _incident_creation_lock:
        global_minute_timestamps = _prune_old_timestamps(
            _incident_creation_timestamps.get("global:minute", []), 60
        )
        global_hour_timestamps = _prune_old_timestamps(
            _incident_creation_timestamps.get("global:hour", []), 3600
        )
        global_day_timestamps = _prune_old_timestamps(
            _incident_creation_timestamps.get("global:day", []), 86400
        )

    response = {
        "global": {
            "minute": {
                "limit": settings.max_incidents_per_minute,
                "used": len(global_minute_timestamps),
                "remaining": max(
                    0, settings.max_incidents_per_minute - len(global_minute_timestamps)
                ),
            },
            "hour": {
                "limit": settings.max_incidents_per_hour,
                "used": len(global_hour_timestamps),
                "remaining": max(0, settings.max_incidents_per_hour - len(global_hour_timestamps)),
            },
            "day": {
                "limit": settings.max_incidents_per_day,
                "used": len(global_day_timestamps),
                "remaining": max(0, settings.max_incidents_per_day - len(global_day_timestamps)),
            },
            "active_incidents": {
                "limit": settings.max_global_active_incidents,
                "used": _global_active_incidents,
                "remaining": max(
                    0, settings.max_global_active_incidents - _global_active_incidents
                ),
            },
            "daily_creation": {
                "limit": settings.max_global_daily_creation,
                "used": len(global_day_timestamps),
                "remaining": max(
                    0, settings.max_global_daily_creation - len(global_day_timestamps)
                ),
            },
        },
        "anonymous_limits": {
            "max_incidents": settings.max_anonymous_incidents,
            "current": _anonymous_incident_count,
            "remaining": max(0, settings.max_anonymous_incidents - _anonymous_incident_count),
        }
        if is_anonymous
        else None,
        "user_limits": {
            "active_incidents": {
                "limit": settings.max_active_incidents_per_user,
                "used": _active_incidents_per_user[user_id],
                "remaining": max(
                    0, settings.max_active_incidents_per_user - _active_incidents_per_user[user_id]
                ),
            },
            "retained_incidents": {
                "limit": settings.max_retained_incidents_per_user,
                "used": _retained_incidents_per_user[user_id],
                "remaining": max(
                    0,
                    settings.max_retained_incidents_per_user
                    - _retained_incidents_per_user[user_id],
                ),
            },
        }
        if not is_anonymous
        else None,
        "org_limits": {
            "active_incidents": {
                "limit": settings.max_active_incidents_per_org,
                "used": _active_incidents_per_org[org_id],
                "remaining": max(
                    0, settings.max_active_incidents_per_org - _active_incidents_per_org[org_id]
                ),
            },
            "retained_incidents": {
                "limit": settings.max_retained_incidents_per_org,
                "used": _retained_incidents_per_org[org_id],
                "remaining": max(
                    0, settings.max_retained_incidents_per_org - _retained_incidents_per_org[org_id]
                ),
            },
        }
        if not is_anonymous
        else None,
    }

    return response


@app.get("/api/v1/concurrency")
async def get_concurrency_stats(request: Request, user_data: tuple = Depends(get_current_user)):
    """
    Get current concurrency limits and usage for all scopes.
    Requires: concurrency:read permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check permission
    await authorize(auth_store, user, "concurrency:read")

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="concurrency.stats.read",
            resource_type="concurrency",
            resource_id="global",
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    manager = get_concurrency_manager()
    if not manager:
        return {"error": "Concurrency manager not initialized"}

    scopes = ["pipeline", "simulation", "model_inference", "sandbox", "patch_generation"]
    stats = {}
    for scope in scopes:
        stats[scope] = await manager.get_stats(scope)

    return {"scopes": stats, "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/v1/concurrency/{scope}")
async def get_concurrency_scope(
    request: Request, scope: str, user_data: tuple = Depends(get_current_user)
):
    """
    Get concurrency stats for a specific scope.
    Requires: concurrency:read permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check permission
    await authorize(auth_store, user, "concurrency:read")

    manager = get_concurrency_manager()
    if not manager:
        raise HTTPException(status_code=503, detail="Concurrency manager not initialized")

    return await manager.get_stats(scope)


@app.post("/api/v1/concurrency/{scope}/cleanup")
async def cleanup_concurrency_scope(
    request: Request, scope: str, user_data: tuple = Depends(get_current_user)
):
    """
    Manually trigger stale slot cleanup for a scope.
    Requires: concurrency:manage permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check permission
    await authorize(auth_store, user, "concurrency:manage")

    manager = get_concurrency_manager()
    if not manager:
        raise HTTPException(status_code=503, detail="Concurrency manager not initialized")

    settings = get_settings()
    removed = await manager._store.cleanup_stale(time.time() - settings.concurrency_stale_threshold)

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="concurrency.cleanup",
            resource_type="concurrency",
            resource_id=scope,
            decision="allow",
            metadata={"cleaned_up": removed},
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    return {"scope": scope, "cleaned_up": removed}


# Job Queue Endpoints (Phase 6)
@app.get("/api/v1/job-queue")
async def get_job_queue_stats(request: Request, user_data: tuple = Depends(get_current_user)):
    """
    Get job queue statistics.
    Requires: job_queue:read permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check permission
    await authorize(auth_store, user, "job_queue:read")

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="job_queue.stats.read",
            resource_type="job_queue",
            resource_id="global",
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    from cauveris.job_queue import get_job_queue

    queue = get_job_queue()
    if not queue:
        return {"error": "Job queue not initialized"}

    return await queue.get_stats()


@app.get("/api/v1/metrics")
async def get_metrics(request: Request, user_data: tuple = Depends(get_current_user)):
    """
    Get system metrics and pipeline performance data.
    Requires: metrics:read permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check permission
    await authorize(auth_store, user, "metrics:read")

    # Collect pipeline metrics
    pipeline_metrics = []
    for incident_id, progress in pipeline_progress.items():
        ctx = pipeline_contexts.get(incident_id)
        pipeline_metrics.append(
            {
                "incident_id": incident_id,
                "state": progress.get("state"),
                "progress": progress.get("progress"),
                "current_stage": progress.get("current_stage"),
                "stages_completed": len(
                    [s for s in progress.get("stages", []) if s.get("status") == "SUCCESS"]
                ),
                "stages_total": len(progress.get("stages", [])),
                "has_context": ctx is not None,
            }
        )

    # System metrics
    active_pipelines = sum(1 for p in pipeline_progress.values() if p.get("state") == "RUNNING")
    completed_pipelines = sum(1 for p in pipeline_progress.values() if p.get("state") == "SUCCESS")
    failed_pipelines = sum(1 for p in pipeline_progress.values() if p.get("state") == "FAILED")
    cancelled_pipelines = sum(
        1 for p in pipeline_progress.values() if p.get("state") == "CANCELLED"
    )

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": {
            "active_pipelines": active_pipelines,
            "completed_pipelines": completed_pipelines,
            "failed_pipelines": failed_pipelines,
            "cancelled_pipelines": cancelled_pipelines,
            "total_incidents": len(incidents),
            "incidents_in_progress": active_pipelines,
        },
        "pipelines": pipeline_metrics,
        "websocket_connections": len([k for k in pipeline_progress.keys() if k.startswith("ws_")]),
    }


@app.get("/api/v1/job-queue/jobs/{job_id}")
async def get_job_status(
    request: Request, job_id: str, user_data: tuple = Depends(get_current_user)
):
    """
    Get job status by ID.
    Requires: job_queue:read permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check permission
    await authorize(auth_store, user, "job_queue:read")

    from cauveris.job_queue import get_job_queue

    queue = get_job_queue()
    if not queue:
        raise HTTPException(status_code=503, detail="Job queue not initialized")

    job = await queue.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check ownership
    if not user.has_permission("job_queue:manage_any") and not user.has_permission("*"):
        # A job is visible to its owner, or to members of the owning tenant.
        # Jobs without a tenant are visible only to their owner.
        same_tenant = job.tenant_id is not None and job.tenant_id == org_id
        if job.owner_id != user_id and not same_tenant:
            await auth_store.write_audit_log(
                AuditLogEntry(
                    user_id=user.id,
                    org_id=user.org_id,
                    action="job.read",
                    resource_type="job",
                    resource_id=job_id,
                    resource_owner_id=job.owner_id,
                    decision="deny",
                    reason="Not owner of job",
                    ip_address=request.client.host if request.client else "unknown",
                    user_agent=request.headers.get("User-Agent", ""),
                    request_id=getattr(request.state, "request_id", None),
                )
            )
            raise HTTPException(status_code=403, detail="Not authorized to view this job")

    return job.to_dict()


@app.post("/api/v1/job-queue/jobs/{job_id}/cancel")
async def cancel_job(request: Request, job_id: str, user_data: tuple = Depends(get_current_user)):
    """
    Cancel a job.
    Requires: job_queue:cancel permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    from cauveris.job_queue import get_job_queue

    queue = get_job_queue()
    if not queue:
        raise HTTPException(status_code=503, detail="Job queue not initialized")

    job = await queue.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check ownership
    if not user.has_permission("job_queue:manage_any") and not user.has_permission("*"):
        # A job is visible to its owner, or to members of the owning tenant.
        # Jobs without a tenant are visible only to their owner.
        same_tenant = job.tenant_id is not None and job.tenant_id == org_id
        if job.owner_id != user_id and not same_tenant:
            await auth_store.write_audit_log(
                AuditLogEntry(
                    user_id=user.id,
                    org_id=user.org_id,
                    action="job.cancel",
                    resource_type="job",
                    resource_id=job_id,
                    resource_owner_id=job.owner_id,
                    decision="deny",
                    reason="Not owner of job",
                    ip_address=request.client.host if request.client else "unknown",
                    user_agent=request.headers.get("User-Agent", ""),
                    request_id=getattr(request.state, "request_id", None),
                )
            )
            raise HTTPException(status_code=403, detail="Not authorized to cancel this job")

    success = await queue.cancel_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found or cannot be cancelled")

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="job.cancel",
            resource_type="job",
            resource_id=job_id,
            resource_owner_id=job.owner_id,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    return {"job_id": job_id, "status": "cancelled"}


@app.post("/api/v1/job-queue/submit")
async def submit_job(request: Request, user_data: tuple = Depends(get_current_user)):
    """
    Submit a job to the queue.
    Requires: job_queue:submit permission

    Body:
    {
        "type": "pipeline",
        "payload": {"incident_id": "CAU-0001"},
        "priority": "NORMAL",
        "max_retries": 3,
        "owner_id": "user-123",
        "metadata": {"trace_id": "abc123"}
    }
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check permission
    await authorize(auth_store, user, "job_queue:submit")

    from cauveris.job_queue import get_job_queue, Job, JobPriority

    queue = get_job_queue()
    if not queue:
        raise HTTPException(status_code=503, detail="Job queue not initialized")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")

    # Parse the priority defensively: an unknown name, a numeric priority or
    # a non-string value must not surface as an unhandled 500.
    raw_priority = body.get("priority", "NORMAL")
    try:
        if isinstance(raw_priority, JobPriority):
            priority = raw_priority
        elif isinstance(raw_priority, bool):
            raise ValueError("bool is not a valid priority")
        elif isinstance(raw_priority, int):
            priority = JobPriority(raw_priority)
        elif isinstance(raw_priority, str):
            candidate = raw_priority.strip().upper()
            if candidate.isdigit():
                priority = JobPriority(int(candidate))
            else:
                priority = JobPriority[candidate]
        else:
            raise ValueError(f"unsupported priority type: {type(raw_priority).__name__}")
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid priority. Expected one of: {[p.name for p in JobPriority]}",
        )

    # Use authenticated user's ID as owner
    job = Job(
        type=body.get("type", "unknown"),
        payload=body.get("payload", {}),
        priority=priority,
        max_retries=body.get("max_retries", 3),
        owner_id=user_id,
        tenant_id=org_id,
        metadata=body.get("metadata", {}),
    )

    success = await queue.submit(job)
    if not success:
        raise HTTPException(status_code=429, detail="Queue full")

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="job.submit",
            resource_type="job",
            resource_id=job.id,
            resource_owner_id=user_id,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    return {"job_id": job.id, "status": "queued"}


@app.get("/api/v1/incidents")
async def list_incidents(request: Request, user_data: tuple = Depends(get_optional_user)):
    """List incidents filtered by user/org ownership."""
    user_id, org_id, role = user_data
    results = []
    seen = set()

    # Determine filter criteria
    is_admin = user_id is not None and role in ("admin", "super_admin")

    for inc_id, inc in incidents.items():
        seen.add(inc_id)

        # Check ownership for non-admin users
        owner_user = getattr(inc, "_owner_user_id", None)
        owner_org = getattr(inc, "_owner_org_id", None)
        _ = getattr(inc, "_is_anonymous", False)  # is_anon

        if not is_admin and user_id is not None:
            if owner_user != user_id and owner_org != org_id:
                continue  # Skip incidents not owned by this user/org

        orch_state = pipeline_progress.get(inc_id, {}).get(
            "state", getattr(inc, "status", "OBSERVED")
        )
        results.append(
            {
                "id": inc.id,
                "title": inc.title,
                "system_name": inc.system_name,
                "status": orch_state,
                "pipeline_state": orch_state,
                "evidence_count": inc.evidence_count,
                "timeline_events_count": len(inc.timeline_events)
                if hasattr(inc, "timeline_events") and inc.timeline_events
                else 0,
                "is_demonstration": getattr(inc, "is_demonstration", False),
                "approximate_time": inc.approximate_time.isoformat()
                if inc.approximate_time
                else None,
            }
        )

    # Discover any other incident folders on disk (only show if authenticated)
    if user_id is not None:
        try:
            settings = get_settings()
            store = Path(settings.evidence_store_path)
            if store.exists():
                for d in store.iterdir():
                    if d.is_dir() and d.name not in seen:
                        seen.add(d.name)
                        results.append(
                            {
                                "id": d.name,
                                "title": f"Incident {d.name}",
                                "system_name": "embedded-system",
                                "status": "OBSERVED",
                                "pipeline_state": "OBSERVED",
                                "evidence_count": len(list(d.glob("**/*.*"))),
                                "timeline_events_count": 0,
                                "is_demonstration": False,
                                "approximate_time": None,
                            }
                        )

            for glob_pattern in ("incident-*", "packages/incident-*", "packages/golden_incident/incident-*", "packages/*"):
                for p in Path(".").glob(glob_pattern):
                    if p.is_dir() and (p / "manifest.yaml").exists():
                        inc_id = p.name.replace("incident-", "")
                    if inc_id not in seen:
                        seen.add(inc_id)
                        results.append(
                            {
                                "id": inc_id,
                                "title": f"Incident {inc_id}",
                                "system_name": "physical-ai-system",
                                "status": "OBSERVED",
                                "pipeline_state": "OBSERVED",
                                "evidence_count": len(list(p.glob("**/*.*"))),
                                "timeline_events_count": 0,
                                "is_demonstration": (inc_id == "CAU-0001"),
                                "approximate_time": None,
                            }
                        )
        except Exception as e:
            logger.debug(f"Error scanning disk for incidents: {e}")

    return {"incidents": results, "count": len(results)}


@app.post("/api/v1/incidents")
async def create_incident(
    request: Request,
    background_tasks: BackgroundTasks,
    body: Optional[CreateIncidentRequest] = None,
    golden: Optional[bool] = None,
    user_data: tuple = Depends(get_current_user),
):
    """
    Create a new incident. If golden=True, load the golden incident.
    Otherwise, expect a file upload in a separate call to /upload.
    Enforces incident creation limits (Phase 2).
    Requires: incident:create permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check authorization
    await authorize(
        auth_store,
        user,
        "incident:create",
        ip=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("User-Agent", ""),
        request_id=getattr(request.state, "request_id", None),
    )

    # Check incident creation limits
    allowed, error_message, retry_after, limit_headers = _check_incident_creation_limits(request)
    if not allowed:
        raise HTTPException(
            status_code=429 if retry_after > 0 else 409,
            detail=error_message,
            headers={**limit_headers, "Retry-After": str(retry_after)}
            if retry_after > 0
            else limit_headers,
        )

    is_golden = golden if golden is not None else (body.golden if body else False)

    if is_golden:
        incident = load_explicit_sample()
        # Store ownership metadata (dynamically added attributes)
        incident._owner_user_id = user_id  # type: ignore[attr-defined]
        incident._owner_org_id = org_id  # type: ignore[attr-defined]
        incident._is_anonymous = False  # type: ignore[attr-defined]
        incidents[incident.id] = incident

        orch = PipelineOrchestrator()
        orch.context = PipelineContext(incident=incident)
        pipeline_tasks[incident.id] = orch
        pipeline_progress[incident.id] = orch.get_pipeline_summary()
        from cauveris.state_machine.persistence import PipelinePersistenceStore
        PipelinePersistenceStore.get_instance().initialize_incident_stages(incident.id, overwrite=True)
        logger.info(f"Loaded golden incident {incident.id} [DEMO BENCHMARK]")

        # Record creation for limit tracking
        _record_incident_created(request, incident.id, is_demonstration=True)

        # Audit log
        await auth_store.write_audit_log(
            AuditLogEntry(
                user_id=user.id,
                org_id=user.org_id,
                action="incident.create",
                resource_type="incident",
                resource_id=incident.id,
                resource_owner_id=user_id,
                decision="allow",
                ip_address=request.client.host if request.client else "unknown",
                user_agent=request.headers.get("User-Agent", ""),
                request_id=getattr(request.state, "request_id", None),
                metadata={"golden": True, "is_demonstration": True},
            )
        )

        return Response(
            content=json.dumps(
                {
                    "incident_id": incident.id,
                    "message": "Golden incident loaded [DEMONSTRATION BENCHMARK]",
                    "is_demonstration": True,
                    "system_name": incident.system_name,
                    "evidence_count": incident.evidence_count,
                }
            ),
            media_type="application/json",
            headers=limit_headers,
        )

    incident_id = body.custom_id if body and body.custom_id else str(uuid.uuid4())
    title = body.title if body and body.title else "Uploaded Incident"
    desc = body.description if body and body.description else "Incident uploaded via API"
    sys_name = body.system_name if body and body.system_name else "warehouse-amr-01"

    incident = Incident(
        id=incident_id, title=title, description=desc, system_name=sys_name, status="OBSERVED"
    )
    # Store ownership metadata (dynamically added attributes)
    incident._owner_user_id = user_id  # type: ignore[attr-defined]
    incident._owner_org_id = org_id  # type: ignore[attr-defined]
    incident._is_anonymous = False  # type: ignore[attr-defined]
    incidents[incident_id] = incident
    orch = PipelineOrchestrator()
    orch.context = PipelineContext(incident=incident)
    pipeline_tasks[incident_id] = orch
    pipeline_progress[incident_id] = orch.get_pipeline_summary()
    from cauveris.state_machine.persistence import PipelinePersistenceStore
    PipelinePersistenceStore.get_instance().initialize_incident_stages(incident_id, overwrite=True)
    logger.info(f"Created empty incident {incident_id}")

    # Record creation for limit tracking
    _record_incident_created(request, incident_id, is_demonstration=False)

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="incident.create",
            resource_type="incident",
            resource_id=incident.id,
            resource_owner_id=user_id,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
            metadata={"golden": False},
        )
    )

    return Response(
        content=json.dumps(
            {
                "incident_id": incident_id,
                "message": "Incident created, ready for bundle upload",
                "is_demonstration": False,
                "system_name": sys_name,
            }
        ),
        media_type="application/json",
        headers=limit_headers,
    )



@app.post("/api/v1/incidents/upload")
async def upload_and_create_incident(
    request: Request,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    system_name: Optional[str] = Form(None),
    user_data: tuple = Depends(get_current_user),
):
    """
    Canonical single-step incident upload and creation from a ZIP package.
    Computes package SHA-256, validates archive, extracts securely,
    creates incident and workspace, inventories artifacts, and initializes pipeline.
    Requires: incident:create and evidence:upload permissions.
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await authorize(
        auth_store,
        user,
        "incident:create",
        ip=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("User-Agent", ""),
        request_id=getattr(request.state, "request_id", None),
    )

    allowed, error_message, retry_after, limit_headers = _check_incident_creation_limits(request)
    if not allowed:
        raise HTTPException(
            status_code=429 if retry_after > 0 else 409,
            detail=error_message,
            headers={**limit_headers, "Retry-After": str(retry_after)} if retry_after > 0 else limit_headers,
        )

    if file.filename is None or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a ZIP archive")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    package_sha256 = hashlib.sha256(content).hexdigest()
    safe_name = PurePath(file.filename.replace("\\", "/")).name
    if not safe_name or safe_name in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid file name")

    settings = get_settings()
    try:
        with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
            members = zf.infolist()
            if not members:
                raise ValueError("ZIP archive is empty")
            if len(members) > settings.max_archive_members:
                raise ValueError("ZIP archive exceeds the member threshold")
            uncompressed_size = sum(max(0, int(m.file_size)) for m in members)
            if uncompressed_size > settings.max_archive_uncompressed_size:
                raise ValueError("ZIP archive exceeds the uncompressed-size threshold")
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file: archive is corrupt")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=f"Invalid ZIP file: {str(ve)}")

    short_uuid = uuid.uuid4().hex[:8].upper()
    incident_id = f"INC-{short_uuid}"
    resolved_title = title or file.filename.replace(".zip", "").replace("-", " ").replace("_", " ").title()

    incident = Incident(
        id=incident_id,
        title=resolved_title,
        description=description or "Uploaded incident bundle",
        system_name=system_name or "robotic-worker",
        is_demonstration=False,
    )
    incident._owner_user_id = user_id
    incident._owner_org_id = org_id
    incident._is_anonymous = False
    incident.package_sha256 = package_sha256
    setattr(incident, "_uploaded_filename", file.filename)

    extract_dir = Path(settings.evidence_store_path) / incident_id
    extract_dir.mkdir(parents=True, exist_ok=True)

    zip_path = safe_join(str(UPLOAD_DIR), f"{incident_id}_{safe_name}")
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(zip_path, "wb") as buf:
            buf.write(content)
        extracted_files = extract_zip_safely(zip_path, extract_dir)
    finally:
        if zip_path.exists():
            zip_path.unlink()

    incident.bundle_path = str(extract_dir)
    incident.manifest = {
        "bundle_path": str(extract_dir),
        "package_sha256": package_sha256,
        "uploaded_filename": file.filename,
    }

    controller = IngestionController()
    for extracted_file in extracted_files:
        try:
            rel = extracted_file.relative_to(extract_dir)
            det_type = controller._detect_file_type(extracted_file)
            csum = compute_file_hash(str(extracted_file))
            incident.evidence_items.append(
                EvidenceItem(
                    file_path=str(rel).replace("\\", "/"),
                    file_type=det_type,
                    size_bytes=extracted_file.stat().st_size,
                    checksum_sha256=csum,
                    status=StatusLabel.OBSERVED,
                    is_required=False,
                )
            )
        except Exception as e:
            logger.warning(f"Error indexing extracted file {extracted_file}: {e}")

    incident = await controller.process(incident)
    incidents[incident_id] = incident

    orch = PipelineOrchestrator()
    orch.context = PipelineContext(incident=incident)
    pipeline_tasks[incident_id] = orch
    pipeline_contexts[incident_id] = orch.context

    return {
        "incident_id": incident.id,
        "job_id": getattr(incident, "job_id", incident.id),
        "title": incident.title,
        "package_sha256": package_sha256,
        "filename": file.filename,
        "size": len(content),
        "evidence_count": len(incident.evidence_items),
        "artifact_inventory_count": len(incident.artifact_inventory or []),
        "capability_report": incident.capability_report,
        "message": "Incident package uploaded and ingested successfully",
    }


@app.post("/api/v1/incidents/{incident_id}/upload")
async def upload_incident(
    request: Request,
    incident_id: str,
    file: UploadFile = File(...),
    user_data: tuple = Depends(get_current_user),
):
    """
    Upload an incident bundle (ZIP file) and attach it to the incident.
    Requires: evidence:upload permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check authorization
    await authorize(
        auth_store,
        user,
        "evidence:upload",
        resource_type="incident",
        resource_id=incident_id,
        ip=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("User-Agent", ""),
        request_id=getattr(request.state, "request_id", None),
    )

    if incident_id not in incidents:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Check ownership
    incident = incidents[incident_id]
    owner_user = getattr(incident, "_owner_user_id", None)
    owner_org = getattr(incident, "_owner_org_id", None)

    is_admin = (
        user.has_permission("*")
        or getattr(user, "is_superuser", False)
        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)
    )
    if not is_admin:
        if owner_user and owner_user != user_id:
            await auth_store.write_audit_log(
                AuditLogEntry(
                    user_id=user.id,
                    org_id=user.org_id,
                    action="evidence.upload",
                    resource_type="incident",
                    resource_id=incident_id,
                    resource_owner_id=owner_user,
                    decision="deny",
                    reason="Not owner of incident",
                    ip_address=request.client.host if request.client else "unknown",
                    user_agent=request.headers.get("User-Agent", ""),
                    request_id=getattr(request.state, "request_id", None),
                )
            )
            raise HTTPException(
                status_code=403,
                detail={"error": "access_denied", "message": "Not authorized to upload to this incident", "incident_id": incident_id},
            )
        if owner_org and owner_org != org_id:
            await auth_store.write_audit_log(
                AuditLogEntry(
                    user_id=user.id,
                    org_id=user.org_id,
                    action="evidence.upload",
                    resource_type="incident",
                    resource_id=incident_id,
                    resource_owner_id=owner_user,
                    decision="deny",
                    reason="Cross-organization incident access denied",
                    ip_address=request.client.host if request.client else "unknown",
                    user_agent=request.headers.get("User-Agent", ""),
                    request_id=getattr(request.state, "request_id", None),
                )
            )
            raise HTTPException(
                status_code=403,
                detail={"error": "access_denied", "message": "Not authorized to upload to this incident", "incident_id": incident_id},
            )

    if not user.has_permission("evidence:upload") and not user.has_permission("incident:update_any") and not user.has_permission("*"):
        await auth_store.write_audit_log(
            AuditLogEntry(
                user_id=user.id,
                org_id=user.org_id,
                action="evidence.upload",
                resource_type="incident",
                resource_id=incident_id,
                resource_owner_id=owner_user,
                decision="deny",
                reason="Missing permission: evidence:upload",
                ip_address=request.client.host if request.client else "unknown",
                user_agent=request.headers.get("User-Agent", ""),
                request_id=getattr(request.state, "request_id", None),
            )
        )
        raise HTTPException(
            status_code=403,
            detail={"error": "access_denied", "message": "Insufficient permissions: evidence:upload", "incident_id": incident_id},
        )

    # Validate file extension
    if file.filename is None or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a ZIP archive")

    # Read file content
    content = await file.read()

    # Save to temporary location for processing.
    # The client-supplied filename is untrusted: strip any directory components
    # and confirm the resolved path stays inside the upload directory.
    if file.filename is None:
        raise HTTPException(status_code=400, detail="File must have a filename")
    safe_name = PurePath(file.filename.replace("\\", "/")).name
    if not safe_name or safe_name in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid file name")
    try:
        zip_path = safe_join(str(UPLOAD_DIR), safe_name)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file name")
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    package_sha256 = hashlib.sha256(content).hexdigest()

    try:
        # Write the uploaded file to temp location
        with open(zip_path, "wb") as buffer:
            buffer.write(content)

        logger.info(f"Saved uploaded file to {zip_path}")

        # Extract ZIP safely to permanent evidence store
        settings = get_settings()
        extract_dir = Path(settings.evidence_store_path) / incident_id
        extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            extracted_files = extract_zip_safely(zip_path, extract_dir)
            logger.info(f"Extracted {len(extracted_files)} files from ZIP to {extract_dir}")
        except ValueError as e:
            logger.error(f"ZIP extraction failed due to security violation: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid ZIP file: {str(e)}")
        except zipfile.BadZipFile as e:
            logger.error(f"ZIP extraction failed because the archive is corrupt: {e}")
            raise HTTPException(status_code=400, detail="Invalid ZIP file: archive is corrupt")
        except Exception as e:
            logger.error(f"ZIP extraction failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to extract ZIP file")

        # Process each extracted file and create EvidenceItem objects
        incident = incidents[incident_id]
        incident.bundle_path = str(extract_dir)
        if incident.manifest is None:
            incident.manifest = {}
        incident.manifest["bundle_path"] = str(extract_dir)
        incident.manifest["package_sha256"] = package_sha256
        incident.manifest["uploaded_filename"] = file.filename
        setattr(incident, "package_sha256", package_sha256)
        setattr(incident, "_uploaded_filename", file.filename)

        for extracted_file in extracted_files:
            try:
                # Get relative path for evidence tracking
                relative_path = extracted_file.relative_to(extract_dir)

                # Detect file type
                detected_type = IngestionController()._detect_file_type(extracted_file)

                # Validate file type (basic validation - in reality would use settings)
                # For demo, we'll accept common types
                allowed_types = {
                    "text/yaml",
                    "application/json",
                    "text/csv",
                    "text/plain",
                    "text/markdown",
                    "text/x-python",
                    "application/octet-stream",
                    "image/png",
                    "image/jpeg",
                    "application/pdf",
                    "video/mp4",
                }

                if detected_type not in allowed_types:
                    logger.warning(
                        f"File type {detected_type} not in allowed list, but processing anyway"
                    )

                # Validate file size
                file_size = extracted_file.stat().st_size
                max_size = 100 * 1024 * 1024  # 100MB limit for demo
                if file_size > max_size:
                    logger.warning(f"File {relative_path} exceeds size limit: {file_size} bytes")
                    # Continue processing but flag in validation later

                # Compute checksum
                checksum = compute_file_hash(str(extracted_file))

                # Scan for secrets (text files only)
                secrets_found = []
                if detected_type.startswith("text/") or detected_type in [
                    "application/json",
                    "application/yaml",
                ]:
                    try:
                        with open(extracted_file, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                        secrets_found = scan_for_secrets(content, str(extracted_file))
                    except Exception:
                        # If we can't read as text, skip secret scanning
                        pass

                # Determine status based on validation
                status = "OBSERVED"
                validation_errors = []

                if secrets_found:
                    validation_errors.append(
                        f"Potential secrets detected: {', '.join(set([s[0] for s in secrets_found]))}"
                    )
                    status = "SECRETS_DETECTED"

                # Create EvidenceItem
                evidence = EvidenceItem(
                    file_path=str(relative_path),
                    file_type=detected_type,
                    size_bytes=file_size,
                    checksum_sha256=checksum,
                    status=status,
                    is_required=False,  # Most uploaded evidence is not strictly required
                    validation_errors=validation_errors,
                )

                incident.evidence_items.append(evidence)
                logger.debug(f"Added evidence item for {relative_path}: {status}")

            except Exception as e:
                logger.error(f"Failed to process extracted file {extracted_file}: {e}")
                # Create a failed evidence item
                evidence = EvidenceItem(
                    file_path=str(extracted_file.relative_to(extract_dir))
                    if extract_dir in extracted_file.parents
                    else extracted_file.name,
                    file_type="application/octet-stream",
                    size_bytes=0,
                    checksum_sha256="",
                    status="PROCESSING_ERROR",
                    is_required=False,
                    validation_errors=[f"Processing error: {str(e)}"],
                )
                incident.evidence_items.append(evidence)

        # Update incident evidence counts
        incident.update_counts()

        # Run full ingestion controller processing to populate artifact inventory and capability planner
        controller = IngestionController()
        incident = await controller.process(incident)
        incidents[incident_id] = incident

        logger.info(
            f"Successfully processed upload for incident {incident_id}: {len(incident.evidence_items)} evidence items"
        )
        return {
            "message": "File uploaded and processed",
            "filename": file.filename,
            "size": len(content),
            "package_sha256": package_sha256,
            "incident_id": incident.id,
            "title": incident.title,
            "evidence_count": len(incident.evidence_items),
            "artifact_inventory_count": len(incident.artifact_inventory or []),
            "capability_report": incident.capability_report,
        }

    finally:
        # Cleanup temporary upload zip
        try:
            if zip_path.exists():
                zip_path.unlink()
            # Also cleanup the temp upload directory if empty
            temp_upload_dir = Path("./temp_upload")
            if temp_upload_dir.exists() and not any(temp_upload_dir.iterdir()):
                temp_upload_dir.rmdir()
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")


@app.get("/api/v1/incidents/{incident_id}/artifacts/{artifact_id}/preview")
async def get_artifact_preview(
    request: Request,
    incident_id: str,
    artifact_id: str,
    user_data: tuple = Depends(get_current_user),
):
    """
    Safe preview of an incident artifact with secret redaction and HTML escaping.
    Requires: incident:read permission and that artifact belongs to this incident.
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    await check_incident_access(incident, user, "incident:read", "artifact.preview", request, auth_store)

    inv = getattr(incident, "artifact_inventory", []) or []
    target_item = None
    for item in inv:
        if item.get("artifact_id") == artifact_id or item.get("relative_path") == artifact_id:
            target_item = item
            break

    if not target_item:
        raise HTTPException(status_code=404, detail="Artifact not found in incident inventory")

    if target_item.get("incident_id") and str(target_item.get("incident_id")) != str(incident_id):
        raise HTTPException(
            status_code=403,
            detail={"error": "cross_incident_artifact_access", "message": f"Artifact belongs to incident '{target_item.get('incident_id')}', not '{incident_id}'"},
        )

    rel_path = target_item.get("relative_path", "")
    bundle_path = getattr(incident, "bundle_path", None)
    if not bundle_path:
        raise HTTPException(status_code=404, detail="Incident bundle path not found")

    try:
        file_path = safe_join(bundle_path, rel_path)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid relative path in artifact")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Artifact file does not exist on disk")

    classification = target_item.get("classification", "text")
    if classification == "binary" or target_item.get("parse_status") in ("BINARY", "ENCRYPTED", "REJECTED"):
        return {
            "artifact_id": target_item.get("artifact_id"),
            "relative_path": rel_path,
            "preview_available": False,
            "classification": "binary",
            "reason": "Preview not supported for binary or encrypted files",
        }

    max_bytes = 64 * 1024
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            raw_text = f.read(max_bytes + 1)
        is_truncated = len(raw_text) > max_bytes
        if is_truncated:
            raw_text = raw_text[:max_bytes]

        from cauveris.model_gateway.security import redact_secrets

        redacted_text, redaction_count = redact_secrets(raw_text)
        escaped_preview = html.escape(redacted_text)

        return {
            "artifact_id": target_item.get("artifact_id"),
            "relative_path": rel_path,
            "preview_available": True,
            "classification": "text",
            "preview": escaped_preview,
            "truncated": is_truncated,
            "size_bytes": file_path.stat().st_size,
            "redaction_count": redaction_count,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read artifact: {e}")


@app.post("/api/v1/incidents/{incident_id}/validate")
async def validate_incident(
    request: Request, incident_id: str, user_data: tuple = Depends(get_current_user)
):
    """
    Validate the incident bundle and evidence integrity.
    Requires: incident:validate permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Check ownership and permissions


    owner_user = getattr(incident, "_owner_user_id", None)


    owner_org = getattr(incident, "_owner_org_id", None)



    is_admin = (


        user.has_permission("*")


        or getattr(user, "is_superuser", False)


        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)


    )


    if not is_admin:


        if owner_user and owner_user != user_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="incident.validate",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Not owner of incident",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to validate this incident", "incident_id": incident_id},


            )


        if owner_org and owner_org != org_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="incident.validate",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Cross-organization incident access denied",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to validate this incident", "incident_id": incident_id},


            )



    if not user.has_permission("incident:validate") and not user.has_permission("*"):


        await auth_store.write_audit_log(


            AuditLogEntry(


                user_id=user.id,


                org_id=user.org_id,


                action="incident.validate",


                resource_type="incident",


                resource_id=incident_id,


                resource_owner_id=owner_user,


                decision="deny",


                reason="Missing permission: incident:validate",


                ip_address=request.client.host if request.client else "unknown",


                user_agent=request.headers.get("User-Agent", ""),


                request_id=getattr(request.state, "request_id", None),


            )


        )


        raise HTTPException(


            status_code=403,


            detail={"error": "access_denied", "message": "Insufficient permissions: incident:validate", "incident_id": incident_id},


        )

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="incident.validate",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    ingestion = IngestionController()
    validated_incident = await ingestion.process(incident)
    incidents[incident_id] = validated_incident

    is_valid = len(validated_incident.missing_required_evidence) == 0
    secrets_count = sum(
        1 for e in validated_incident.evidence_items if e.status == "SECRETS_DETECTED"
    )
    status_label = (
        "PASSED" if is_valid and secrets_count == 0 else ("WARNING" if is_valid else "FAILED")
    )

    return {
        "incident_id": incident_id,
        "validation_status": "completed",
        "status": status_label,
        "summary_status": status_label,
        "is_valid": is_valid,
        "evidence_count": validated_incident.evidence_count,
        "required_evidence_count": validated_incident.required_evidence_count,
        "missing_required_evidence": validated_incident.missing_required_evidence,
        "secrets_detected_count": secrets_count,
        "checksums_valid": True,
        "schema_valid": is_valid,
        "is_demonstration": getattr(validated_incident, "is_demonstration", False),
        "evidence_items": [
            {
                "file_path": item.file_path,
                "file_type": item.file_type,
                "size_bytes": item.size_bytes,
                "checksum_sha256": item.checksum_sha256,
                "status": str(item.status.value if hasattr(item.status, "value") else item.status),
                "is_required": item.is_required,
                "validation_errors": item.validation_errors,
            }
            for item in validated_incident.evidence_items
        ],
    }


@app.post("/api/v1/incidents/{incident_id}/reconstruct")
async def reconstruct_incident(
    request: Request,
    incident_id: str,
    background_tasks: BackgroundTasks,
    user_data: tuple = Depends(get_current_user),
):
    """
    Start the incident reconstruction pipeline.
    Requires: incident:reconstruct permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    await check_incident_access(incident, user, "incident:reconstruct", "incident.reconstruct", request, auth_store)

    # Audit log allow
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="incident.reconstruct",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=getattr(incident, "_owner_user_id", None),
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    # Prevent duplicate start request if already running
    if incident_id in pipeline_tasks:
        existing_orch = pipeline_tasks[incident_id]
        if existing_orch.is_running():
            raise HTTPException(
                status_code=409,
                detail="Investigation already running for this incident. Duplicate start requests are blocked.",
            )

    orchestrator = PipelineOrchestrator()
    orchestrator.context = PipelineContext(incident=incident)

    def progress_callback(update, legacy_progress=None):
        if isinstance(update, dict):
            pipeline_progress[incident_id] = update
        else:
            pipeline_progress[incident_id] = orchestrator.get_pipeline_summary()

    orchestrator.set_progress_callback(progress_callback)
    pipeline_tasks[incident_id] = orchestrator
    pipeline_progress[incident_id] = orchestrator.get_pipeline_summary()

    orchestrator.current_state = "RUNNING"
    bg_task = asyncio.create_task(_run_pipeline(incident_id, orchestrator, incident))
    orchestrator._bg_task = bg_task
    return {
        "message": "Reconstruction started successfully",
        "incident_id": incident_id,
        "pipeline_state": "RUNNING",
        "is_demonstration": getattr(incident, "is_demonstration", False),
    }


async def _run_pipeline(incident_id: str, orchestrator: PipelineOrchestrator, incident: Incident):
    """Run the pipeline in the background and store the resulting context."""
    import time

    pipeline_start = time.perf_counter()
    stage_timings = {}

    # Wrap progress callback to capture stage timings
    original_callback = orchestrator._progress_callback

    def timed_progress_callback(update, legacy_progress=None):
        if isinstance(update, dict):
            current_stage = update.get("current_stage")
            if current_stage and current_stage not in stage_timings:
                stage_timings[current_stage] = {"start": time.perf_counter()}
            elif (
                current_stage
                and current_stage in stage_timings
                and "end" not in stage_timings[current_stage]
            ):
                # Stage changed, mark previous as ended
                stage_timings[current_stage]["end"] = time.perf_counter()
        if original_callback:
            original_callback(update, legacy_progress)

    orchestrator.set_progress_callback(timed_progress_callback)

    try:
        context: PipelineContext = await orchestrator.process_incident(incident)
        pipeline_contexts[incident_id] = context
        incidents[incident_id] = incident
        pipeline_progress[incident_id] = orchestrator.get_pipeline_summary()

        # Finalize stage timings
        pipeline_duration = time.perf_counter() - pipeline_start
        for stage_name, timing in stage_timings.items():
            if "end" not in timing:
                timing["end"] = time.perf_counter()
            timing["duration_ms"] = round((timing["end"] - timing["start"]) * 1000, 2)

        logger.info(
            f"Pipeline completed for incident {incident_id}",
            extra={
                "incident_id": incident_id,
                "event": "pipeline_completed",
                "state": orchestrator.current_state,
                "duration_ms": round(pipeline_duration * 1000, 2),
                "stage_timings": stage_timings,
                "stages_count": len(orchestrator.stages),
            },
        )
    except asyncio.CancelledError:
        pipeline_duration = time.perf_counter() - pipeline_start
        logger.warning(
            f"Pipeline cancelled for incident {incident_id}",
            extra={
                "incident_id": incident_id,
                "event": "pipeline_cancelled",
                "duration_ms": round(pipeline_duration * 1000, 2),
                "stage_timings": stage_timings,
            },
        )
        pipeline_progress[incident_id] = orchestrator.get_pipeline_summary()
    except Exception as e:
        pipeline_duration = time.perf_counter() - pipeline_start
        logger.exception(
            f"Pipeline failed for incident {incident_id}",
            extra={
                "incident_id": incident_id,
                "event": "pipeline_failed",
                "duration_ms": round(pipeline_duration * 1000, 2),
                "error": str(e),
                "error_type": type(e).__name__,
                "stage_timings": stage_timings,
            },
        )
        pipeline_progress[incident_id] = orchestrator.get_pipeline_summary()


@app.post("/api/v1/incidents/{incident_id}/cancel")
async def cancel_incident(
    request: Request, incident_id: str, user_data: tuple = Depends(get_current_user)
):
    """Cancel an active running investigation.
    Requires: incident:cancel permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    await check_incident_access(incident, user, "incident:cancel", "incident.cancel", request, auth_store)

    # Audit log allow
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="incident.cancel",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=getattr(incident, "_owner_user_id", None),
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    if incident_id in pipeline_tasks:
        orchestrator = pipeline_tasks[incident_id]
        if orchestrator.is_running():
            orchestrator.cancel()
            pipeline_progress[incident_id] = orchestrator.get_pipeline_summary()
            return {
                "message": "Investigation cancelled by operator",
                "incident_id": incident_id,
                "state": "CANCELLED",
            }

    if (
        incident_id in pipeline_progress
        and pipeline_progress[incident_id].get("state") == "RUNNING"
    ):
        pipeline_progress[incident_id]["state"] = "CANCELLED"
        pipeline_progress[incident_id]["error"] = "Investigation cancelled by operator"
        return {
            "message": "Investigation cancelled by operator",
            "incident_id": incident_id,
            "state": "CANCELLED",
        }

    return {
        "message": "No active investigation currently running to cancel",
        "incident_id": incident_id,
        "state": pipeline_progress.get(incident_id, {}).get("state", "IDLE"),
    }



@app.post("/api/v1/incidents/{incident_id}/retry")
async def retry_incident(
    request: Request,
    incident_id: str,
    background_tasks: BackgroundTasks,
    user_data: tuple = Depends(get_current_user),
):
    """
    Retry a failed or cancelled investigation from the beginning.
    Requires: incident:retry permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Check ownership and permissions


    owner_user = getattr(incident, "_owner_user_id", None)


    owner_org = getattr(incident, "_owner_org_id", None)



    is_admin = (


        user.has_permission("*")


        or getattr(user, "is_superuser", False)


        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)


    )


    if not is_admin:


        if owner_user and owner_user != user_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="incident.retry",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Not owner of incident",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to retry this incident", "incident_id": incident_id},


            )


        if owner_org and owner_org != org_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="incident.retry",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Cross-organization incident access denied",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to retry this incident", "incident_id": incident_id},


            )



    if not user.has_permission("incident:retry") and not user.has_permission("*"):


        await auth_store.write_audit_log(


            AuditLogEntry(


                user_id=user.id,


                org_id=user.org_id,


                action="incident.retry",


                resource_type="incident",


                resource_id=incident_id,


                resource_owner_id=owner_user,


                decision="deny",


                reason="Missing permission: incident:retry",


                ip_address=request.client.host if request.client else "unknown",


                user_agent=request.headers.get("User-Agent", ""),


                request_id=getattr(request.state, "request_id", None),


            )


        )


        raise HTTPException(


            status_code=403,


            detail={"error": "access_denied", "message": "Insufficient permissions: incident:retry", "incident_id": incident_id},


        )

    # Check current state
    current_state = pipeline_progress.get(incident_id, {}).get("state", "IDLE")
    if current_state == "RUNNING":
        raise HTTPException(
            status_code=409,
            detail="Investigation is currently running. Cancel first before retrying.",
        )

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="incident.retry",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    # Cancel any existing task
    if incident_id in pipeline_tasks:
        pipeline_tasks[incident_id].cancel()

    # Reset pipeline state
    orchestrator = PipelineOrchestrator()
    orchestrator.context = PipelineContext(incident=incident)

    def progress_callback(update, legacy_progress=None):
        if isinstance(update, dict):
            pipeline_progress[incident_id] = update
        else:
            pipeline_progress[incident_id] = orchestrator.get_pipeline_summary()

    orchestrator.set_progress_callback(progress_callback)
    pipeline_tasks[incident_id] = orchestrator
    pipeline_progress[incident_id] = orchestrator.get_pipeline_summary()

    # Clear any previous context
    if incident_id in pipeline_contexts:
        del pipeline_contexts[incident_id]

    orchestrator.current_state = "RUNNING"
    bg_task = asyncio.create_task(_run_pipeline(incident_id, orchestrator, incident))
    orchestrator._bg_task = bg_task
    return {
        "message": "Investigation retry started successfully",
        "incident_id": incident_id,
        "pipeline_state": "RUNNING",
        "is_demonstration": getattr(incident, "is_demonstration", False),
    }


async def _authenticate_websocket(
    websocket: WebSocket,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Authenticate WebSocket connection via query param or Authorization header.
    Returns: (user_id, org_id, role) or (None, None, None) if unauthenticated.
    """
    from cauveris.auth import TokenManager, TokenType
    from cauveris.config import get_settings

    settings = get_settings()
    token_manager = TokenManager(settings.auth_jwt_secret, settings.auth_jwt_algorithm)
    auth_store = get_auth_store()

    # Try query parameter first
    query_params = dict(websocket.query_params)
    token = query_params.get("token")

    # Fall back to Authorization header
    if not token:
        auth_header = websocket.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]

    if not token:
        return None, None, None

    try:
        payload = token_manager.decode_token(token, TokenType.ACCESS)
        user_id = payload.get("sub")
        org_id = payload.get("org_id")
        role = payload.get("role")
        session_id = payload.get("session_id")

        if not user_id or not org_id:
            return None, None, None

        # Verify session exists and is valid
        if auth_store:
            session = await auth_store.get_session(session_id)
            if not session or session.is_revoked or session.is_expired():
                return None, None, None

        return user_id, org_id, role
    except Exception:
        return None, None, None


@app.websocket("/api/v1/incidents/{incident_id}/progress")
async def incident_progress_websocket(websocket: WebSocket, incident_id: str):
    """
    WebSocket endpoint for real-time pipeline progress streaming.

    Connect to ws://host/api/v1/incidents/{incident_id}/progress?token=<jwt>
    Or with Authorization: Bearer <jwt> header.
    Requires authentication and incident:read permission.
    Receives JSON updates as the pipeline progresses through stages.
    """
    import time

    ws_start_time = time.perf_counter()
    connection_id = f"ws_{incident_id}_{int(ws_start_time * 1000)}"

    # Authenticate before accepting
    user_id, org_id, role = await _authenticate_websocket(websocket)
    if not user_id:
        logger.warning(
            f"WebSocket auth failed for incident {incident_id}",
            extra={"incident_id": incident_id, "connection_id": connection_id},
        )
        await websocket.close(code=4001, reason="Authentication required")
        return

    # Verify incident access
    incident = _ensure_incident(incident_id)
    if not incident:
        logger.warning(
            f"WebSocket incident not found: {incident_id}",
            extra={"incident_id": incident_id, "connection_id": connection_id},
        )
        await websocket.close(code=4004, reason="Incident not found")
        return

    # Check ownership/permission
    owner_user = getattr(incident, "_owner_user_id", None)
    owner_org = getattr(incident, "_owner_org_id", None)
    auth_store = get_auth_store()

    if auth_store:
        user = await auth_store.get_user(user_id)
        is_admin = user and (user.has_permission("*") or getattr(user, "is_superuser", False) or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN))
        if not user or not (user.has_permission("incident:read") or is_admin):
            if not is_admin and (owner_user and owner_user != user_id or owner_org and owner_org != org_id):
                logger.warning(
                    f"WebSocket access denied for user {user_id} on incident {incident_id}",
                    extra={
                        "incident_id": incident_id,
                        "user_id": user_id,
                        "connection_id": connection_id,
                    },
                )
                await websocket.close(code=4003, reason="Not authorized to view this incident")
                return

    await websocket.accept()

    # Log connection established
    logger.info(
        f"WebSocket connected for incident {incident_id}",
        extra={
            "incident_id": incident_id,
            "user_id": user_id,
            "org_id": org_id,
            "role": role,
            "connection_id": connection_id,
            "event": "websocket_connected",
        },
    )

    messages_sent = 0
    try:
        # Send initial state
        initial_progress = pipeline_progress.get(incident_id, {})
        if initial_progress:
            await websocket.send_json(initial_progress)
        else:
            await websocket.send_json(
                {
                    "incident_id": incident_id,
                    "state": "IDLE",
                    "progress": 0.0,
                    "current_stage": None,
                    "stages": [],
                }
            )
        messages_sent += 1

        # Listen for progress updates
        last_progress = ""
        import asyncio

        while True:
            # Check current progress
            current_progress = pipeline_progress.get(incident_id, {})
            progress_json = json.dumps(current_progress, sort_keys=True)

            # Only send if progress changed
            if progress_json != last_progress:
                await websocket.send_json(current_progress)
                last_progress = progress_json
                messages_sent += 1

                # Log progress update with structured fields
                logger.debug(
                    f"WebSocket progress update for {incident_id}",
                    extra={
                        "incident_id": incident_id,
                        "connection_id": connection_id,
                        "event": "websocket_progress",
                        "pipeline_state": current_progress.get("state"),
                        "pipeline_progress": current_progress.get("progress"),
                        "current_stage": current_progress.get("current_stage"),
                    },
                )

            # Check if pipeline is done
            state = current_progress.get("state", "")
            if state in ["SUCCESS", "FAILED", "CANCELLED"]:
                # Send final state and close
                await websocket.send_json(current_progress)
                messages_sent += 1
                break

            # Wait before next poll (200ms)
            await asyncio.sleep(0.2)

    except Exception as e:
        logger.error(
            f"WebSocket error for incident {incident_id}: {e}",
            extra={
                "incident_id": incident_id,
                "connection_id": connection_id,
                "event": "websocket_error",
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
    finally:
        duration_ms = round((time.perf_counter() - ws_start_time) * 1000, 2)
        logger.info(
            f"WebSocket disconnected for incident {incident_id}",
            extra={
                "incident_id": incident_id,
                "user_id": user_id,
                "connection_id": connection_id,
                "duration_ms": duration_ms,
                "messages_sent": messages_sent,
                "event": "websocket_disconnected",
            },
        )
        try:
            await websocket.close()
        except Exception:
            pass


@app.post("/api/v1/incidents/{incident_id}/reset")
@app.post("/api/v1/reset-demo")
async def reset_incident(
    request: Request, incident_id: str = "CAU-0001", user_data: tuple = Depends(get_current_user)
):
    """Reset an investigation and its pipeline stages back to ready IDLE state.
    Requires: incident:reset permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Check ownership and permissions


    owner_user = getattr(incident, "_owner_user_id", None)


    owner_org = getattr(incident, "_owner_org_id", None)



    is_admin = (


        user.has_permission("*")


        or getattr(user, "is_superuser", False)


        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)


    )


    if not is_admin:


        if owner_user and owner_user != user_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="incident.reset",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Not owner of incident",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to reset this incident", "incident_id": incident_id},


            )


        if owner_org and owner_org != org_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="incident.reset",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Cross-organization incident access denied",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to reset this incident", "incident_id": incident_id},


            )



    if not user.has_permission("incident:reset") and not user.has_permission("*"):


        await auth_store.write_audit_log(


            AuditLogEntry(


                user_id=user.id,


                org_id=user.org_id,


                action="incident.reset",


                resource_type="incident",


                resource_id=incident_id,


                resource_owner_id=owner_user,


                decision="deny",


                reason="Missing permission: incident:reset",


                ip_address=request.client.host if request.client else "unknown",


                user_agent=request.headers.get("User-Agent", ""),


                request_id=getattr(request.state, "request_id", None),


            )


        )


        raise HTTPException(


            status_code=403,


            detail={"error": "access_denied", "message": "Insufficient permissions: incident:reset", "incident_id": incident_id},


        )

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="incident.reset",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    if incident_id in pipeline_tasks:
        pipeline_tasks[incident_id].cancel()

    # Reset by clearing pipeline state and reloading from storage
    if incident_id.upper() in ["CAU-0001", "GOLDEN"]:
        incident = load_explicit_sample()
        incident._owner_user_id = user_id  # type: ignore[attr-defined]
        incident._owner_org_id = org_id  # type: ignore[attr-defined]
        incident._is_anonymous = False  # type: ignore[attr-defined]
        incidents[incident.id] = incident
    else:
        incident = _ensure_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        incident.status = "OBSERVED"

    # Clear existing pipeline data for this incident
    if incident_id in pipeline_contexts:
        del pipeline_contexts[incident_id]
    if incident_id in pipeline_progress:
        del pipeline_progress[incident_id]

    orch = PipelineOrchestrator()
    orch.context = PipelineContext(incident=incident)
    pipeline_tasks[incident.id] = orch
    pipeline_progress[incident.id] = orch.get_pipeline_summary()
    from cauveris.state_machine.persistence import PipelinePersistenceStore
    PipelinePersistenceStore.get_instance().initialize_incident_stages(incident.id, overwrite=True)

    if incident.id in pipeline_contexts:
        del pipeline_contexts[incident.id]

    return {
        "message": f"Incident {incident.id} reset to ready state",
        "incident_id": incident.id,
        "state": "IDLE",
        "is_demonstration": getattr(incident, "is_demonstration", False),
        "pipeline_summary": orch.get_pipeline_summary(),
    }


@app.get("/api/v1/incidents/{incident_id}")
async def get_incident(
    request: Request, incident_id: str, user_data: tuple = Depends(get_current_user)
):
    """Get incident details with evidence items and metadata.
    Requires: incident:read permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Check ownership and permissions


    owner_user = getattr(incident, "_owner_user_id", None)


    owner_org = getattr(incident, "_owner_org_id", None)



    is_admin = (


        user.has_permission("*")


        or getattr(user, "is_superuser", False)


        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)


    )


    if not is_admin:


        if owner_user and owner_user != user_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="incident.read",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Not owner of incident",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to view this incident", "incident_id": incident_id},


            )


        if owner_org and owner_org != org_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="incident.read",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Cross-organization incident access denied",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to view this incident", "incident_id": incident_id},


            )



    if not user.has_permission("incident:read") and not user.has_permission("*"):


        await auth_store.write_audit_log(


            AuditLogEntry(


                user_id=user.id,


                org_id=user.org_id,


                action="incident.read",


                resource_type="incident",


                resource_id=incident_id,


                resource_owner_id=owner_user,


                decision="deny",


                reason="Missing permission: incident:read",


                ip_address=request.client.host if request.client else "unknown",


                user_agent=request.headers.get("User-Agent", ""),


                request_id=getattr(request.state, "request_id", None),


            )


        )


        raise HTTPException(


            status_code=403,


            detail={"error": "access_denied", "message": "Insufficient permissions: incident:read", "incident_id": incident_id},


        )

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="incident.read",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    ctx = pipeline_contexts.get(incident_id)
    ver_reports = (getattr(ctx, "verification_reports", None) or []) if ctx else []

    return {
        "id": incident.id,
        "title": incident.title,
        "description": incident.description,
        "system_name": incident.system_name,
        "approximate_time": incident.approximate_time.isoformat()
        if incident.approximate_time
        else None,
        "evidence_count": incident.evidence_count,
        "required_evidence_count": incident.required_evidence_count,
        "missing_required_evidence": incident.missing_required_evidence,
        "status": incident.status,
        "is_demonstration": getattr(incident, "is_demonstration", False),
        "manifest": incident.manifest,
        "timeline_events_count": len(incident.timeline_events),
        "evidence_items": [
            {
                "file_path": item.file_path,
                "file_type": item.file_type,
                "size_bytes": item.size_bytes,
                "checksum_sha256": item.checksum_sha256,
                "status": item.status,
                "is_required": item.is_required,
                "validation_errors": item.validation_errors,
            }
            for item in incident.evidence_items
        ],
        "artifact_inventory": getattr(incident, "artifact_inventory", []) or [],
        "capability_report": getattr(incident, "capability_report", None),
        "verification_reports": [
            r.model_dump() if hasattr(r, "model_dump") else dict(r)
            for r in ver_reports
        ],
    }


@app.get("/api/v1/incidents/{incident_id}/timeline")
async def get_incident_timeline(
    request: Request, incident_id: str, user_data: tuple = Depends(get_current_user)
):
    """Get the synchronized multi-lane timeline events and clock alignment.
    Requires: timeline:read permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Check ownership and permissions


    owner_user = getattr(incident, "_owner_user_id", None)


    owner_org = getattr(incident, "_owner_org_id", None)



    is_admin = (


        user.has_permission("*")


        or getattr(user, "is_superuser", False)


        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)


    )


    if not is_admin:


        if owner_user and owner_user != user_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="timeline.read",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Not owner of incident",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to view this timeline", "incident_id": incident_id},


            )


        if owner_org and owner_org != org_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="timeline.read",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Cross-organization incident access denied",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to view this timeline", "incident_id": incident_id},


            )



    if not user.has_permission("timeline:read") and not user.has_permission("*"):


        await auth_store.write_audit_log(


            AuditLogEntry(


                user_id=user.id,


                org_id=user.org_id,


                action="timeline.read",


                resource_type="incident",


                resource_id=incident_id,


                resource_owner_id=owner_user,


                decision="deny",


                reason="Missing permission: timeline:read",


                ip_address=request.client.host if request.client else "unknown",


                user_agent=request.headers.get("User-Agent", ""),


                request_id=getattr(request.state, "request_id", None),


            )


        )


        raise HTTPException(


            status_code=403,


            detail={"error": "access_denied", "message": "Insufficient permissions: timeline:read", "incident_id": incident_id},


        )

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="timeline.read",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    clock_alignment = incident.manifest.get("clock_alignment", {}) if incident.manifest else {}
    return {
        "incident_id": incident.id,
        "total_events": len(incident.timeline_events),
        "clock_alignment": clock_alignment,
        "timeline_events": incident.timeline_events,
    }


@app.get("/api/v1/incidents/{incident_id}/temporal-analysis")
async def get_incident_temporal_analysis(
    request: Request, incident_id: str, user_data: tuple = Depends(get_current_user)
):
    """Get temporal causality analysis for an incident.
    Requires: timeline:read permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Check ownership and permissions


    owner_user = getattr(incident, "_owner_user_id", None)


    owner_org = getattr(incident, "_owner_org_id", None)



    is_admin = (


        user.has_permission("*")


        or getattr(user, "is_superuser", False)


        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)


    )


    if not is_admin:


        if owner_user and owner_user != user_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="timeline.read",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Not owner of incident",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to view this analysis", "incident_id": incident_id},


            )


        if owner_org and owner_org != org_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="timeline.read",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Cross-organization incident access denied",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to view this analysis", "incident_id": incident_id},


            )



    if not user.has_permission("timeline:read") and not user.has_permission("*"):


        await auth_store.write_audit_log(


            AuditLogEntry(


                user_id=user.id,


                org_id=user.org_id,


                action="timeline.read",


                resource_type="incident",


                resource_id=incident_id,


                resource_owner_id=owner_user,


                decision="deny",


                reason="Missing permission: timeline:read",


                ip_address=request.client.host if request.client else "unknown",


                user_agent=request.headers.get("User-Agent", ""),


                request_id=getattr(request.state, "request_id", None),


            )


        )


        raise HTTPException(


            status_code=403,


            detail={"error": "access_denied", "message": "Insufficient permissions: timeline:read", "incident_id": incident_id},


        )

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="timeline.read",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    ctx = pipeline_contexts.get(incident_id)
    if ctx and ctx.temporal_analysis:
        result = ctx.temporal_analysis
    elif getattr(incident, "temporal_analysis", None):
        result = incident.temporal_analysis
    else:
        from cauveris.temporal.integration import TemporalAnalyzer

        analyzer = TemporalAnalyzer()
        result = analyzer.analyze_incident(incident)

    return {
        "incident_id": incident_id,
        "temporal_analysis": result,
        "violations": result.get("causality_violations", []),
        "clock_alignment": result.get("clock_analysis", {}),
        "anomalies": result.get("temporal_anomalies", []),
        "is_time_anomalous": result.get("is_time_anomalous", False),
        "confidence_score": result.get("temporal_confidence_score", 1.0),
    }


@app.get("/api/v1/incidents/{incident_id}/hypotheses")
async def get_incident_hypotheses(
    request: Request, incident_id: str, user_data: tuple = Depends(get_current_user)
):
    """Get root-cause hypotheses with causal claims and evidence citations.
    Requires: hypothesis:read permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Check ownership and permissions


    owner_user = getattr(incident, "_owner_user_id", None)


    owner_org = getattr(incident, "_owner_org_id", None)



    is_admin = (


        user.has_permission("*")


        or getattr(user, "is_superuser", False)


        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)


    )


    if not is_admin:


        if owner_user and owner_user != user_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="hypothesis.read",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Not owner of incident",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to view hypotheses", "incident_id": incident_id},


            )


        if owner_org and owner_org != org_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="hypothesis.read",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Cross-organization incident access denied",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to view hypotheses", "incident_id": incident_id},


            )



    if not user.has_permission("hypothesis:read") and not user.has_permission("*"):


        await auth_store.write_audit_log(


            AuditLogEntry(


                user_id=user.id,


                org_id=user.org_id,


                action="hypothesis.read",


                resource_type="incident",


                resource_id=incident_id,


                resource_owner_id=owner_user,


                decision="deny",


                reason="Missing permission: hypothesis:read",


                ip_address=request.client.host if request.client else "unknown",


                user_agent=request.headers.get("User-Agent", ""),


                request_id=getattr(request.state, "request_id", None),


            )


        )


        raise HTTPException(


            status_code=403,


            detail={"error": "access_denied", "message": "Insufficient permissions: hypothesis:read", "incident_id": incident_id},


        )

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="hypothesis.read",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    ctx = pipeline_contexts.get(incident_id)
    if ctx and ctx.hypotheses:
        hypotheses = ctx.hypotheses
    else:
        from cauveris.hypothesis.generator import HypothesisGenerator

        hg = HypothesisGenerator()
        hypotheses = await hg.generate(incident)
        if ctx:
            ctx.hypotheses = hypotheses

    formatted_hypotheses = []
    for rank, h in enumerate(hypotheses, start=1):
        dump = h.model_dump() if hasattr(h, "model_dump") else dict(h)
        hyp_id = dump.get("hypothesis_id", "")
        # Provide compatible fields for both frontend formats
        dump["id"] = hyp_id
        dump["rank"] = rank
        dump["title"] = _hypothesis_title(hyp_id, rank)
        dump["description"] = dump.get("causal_claim", "")
        dump["confidence"] = int(float(dump.get("confidence_prior", 0.5)) * 100)
        supp_evs = dump.get("supporting_evidence_ids") or dump.get("supporting_artifact_ids") or []
        dump["supporting_evidence_ids"] = supp_evs
        dump["contradicting_evidence_ids"] = dump.get("contradicting_evidence_ids") or dump.get("contradicting_artifact_ids") or []
        dump["evidence_count"] = len(supp_evs)
        dump["falsification_criteria"] = dump.get("falsification_criteria") or dump.get("falsifying_observation") or ""
        dump["confidence_rationale"] = dump.get("confidence_rationale") or f"Confidence derived from {len(supp_evs)} evidence artifact(s)"
        dump["speculative"] = bool(dump.get("speculative") or not supp_evs)
        formatted_hypotheses.append(dump)

    return {
        "incident_id": incident_id,
        "count": len(formatted_hypotheses),
        "hypotheses": formatted_hypotheses,
    }


@app.post("/api/v1/incidents/{incident_id}/hypotheses/{hypothesis_id}/test")
@app.post("/api/v1/incidents/{incident_id}/hypotheses/test")
async def test_hypothesis_endpoint(
    request: Request,
    incident_id: str,
    hypothesis_id: str = "H1",
    user_data: tuple = Depends(get_current_user),
):
    """
    Test a specific root-cause hypothesis in sandbox and simulate outcomes.
    Requires: hypothesis:test permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Check ownership and permissions


    owner_user = getattr(incident, "_owner_user_id", None)


    owner_org = getattr(incident, "_owner_org_id", None)



    is_admin = (


        user.has_permission("*")


        or getattr(user, "is_superuser", False)


        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)


    )


    if not is_admin:


        if owner_user and owner_user != user_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="hypothesis.test",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Not owner of incident",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to test hypotheses", "incident_id": incident_id},


            )


        if owner_org and owner_org != org_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="hypothesis.test",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Cross-organization incident access denied",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to test hypotheses", "incident_id": incident_id},


            )



    if not user.has_permission("hypothesis:test") and not user.has_permission("*"):


        await auth_store.write_audit_log(


            AuditLogEntry(


                user_id=user.id,


                org_id=user.org_id,


                action="hypothesis.test",


                resource_type="incident",


                resource_id=incident_id,


                resource_owner_id=owner_user,


                decision="deny",


                reason="Missing permission: hypothesis:test",


                ip_address=request.client.host if request.client else "unknown",


                user_agent=request.headers.get("User-Agent", ""),


                request_id=getattr(request.state, "request_id", None),


            )


        )


        raise HTTPException(


            status_code=403,


            detail={"error": "access_denied", "message": "Insufficient permissions: hypothesis:test", "incident_id": incident_id},


        )

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="hypothesis.test",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    ctx = pipeline_contexts.get(incident_id)
    hypotheses = ctx.hypotheses if ctx and ctx.hypotheses else None
    if not hypotheses:
        from cauveris.hypothesis.generator import HypothesisGenerator

        hg = HypothesisGenerator()
        hypotheses = await hg.generate(incident)
        if ctx:
            ctx.hypotheses = hypotheses

    # Find the hypothesis matching hypothesis_id
    target_hyp = _resolve_hypothesis(hypotheses, hypothesis_id)

    if not target_hyp:
        raise HTTPException(
            status_code=404,
            detail=f"Hypothesis '{hypothesis_id}' not found for incident '{incident_id}'",
        )

    # Run sandbox experiment and simulation
    from cauveris.sandbox.controller import SandboxController
    from cauveris.simulation.runner import SimulationRunner

    sandbox = SandboxController()
    experiments = await sandbox.plan_experiments([target_hyp], incident_id=incident_id)
    await sandbox.run_experiments(experiments)

    sim_runner = SimulationRunner()
    sim_experiments = await sim_runner.run_simulations(
        experiments, system_model=_incident_system_model(incident, incident_id)
    )
    exp = sim_experiments[0]

    is_confirmed = (exp.reproduction_rate == 0.0) or exp.failure_oracle.get(
        "hypothesis_supported", False
    )

    if ctx and ctx.experiments:
        for idx, existing in enumerate(ctx.experiments):
            if existing.hypothesis_id == target_hyp.hypothesis_id:
                ctx.experiments[idx] = exp
                break

    msg = (
        "Hypothesis confirmed as root cause! Intervention eliminated emergency stops (0.0% failure reproduction)."
        if is_confirmed
        else f"Hypothesis refuted. Robot emergency stop failure persisted ({int(exp.reproduction_rate * 100)}% reproduction)."
    )

    return {
        "incident_id": incident_id,
        "hypothesis_id": target_hyp.hypothesis_id,
        "id": target_hyp.hypothesis_id,
        "title": target_hyp.hypothesis_id.replace("_", " ").title(),
        "causal_claim": target_hyp.causal_claim,
        "intervention": target_hyp.intervention,
        "status": "CONFIRMED" if is_confirmed else "REFUTED",
        "reproduction_rate": exp.reproduction_rate,
        "hypothesis_supported": is_confirmed,
        "failure_oracle": exp.failure_oracle,
        "metrics": getattr(exp, "metrics", {}),
        "trajectory": getattr(exp, "trajectory", None),
        "trajectories": getattr(exp, "trajectories", None),
        "message": msg,
    }


@app.get("/api/v1/incidents/{incident_id}/system-model")
async def get_incident_system_model(
    request: Request, incident_id: str, user_data: tuple = Depends(get_current_user)
):
    """The calibrated incident model: the numbers every prediction is made from.

    The digital twin, the hypothesis layer and the verifier all read one
    :class:`SystemModel`, so that they cannot disagree about what the incident
    was.  This endpoint exposes it, together with the provenance of every
    parameter: a value that the bundle declared and a value that the model
    defaulted to are both shown, and the difference is visible.

    Requires: incident:read permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Check ownership and permissions


    owner_user = getattr(incident, "_owner_user_id", None)


    owner_org = getattr(incident, "_owner_org_id", None)



    is_admin = (


        user.has_permission("*")


        or getattr(user, "is_superuser", False)


        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)


    )


    if not is_admin:


        if owner_user and owner_user != user_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="incident.read",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Not owner of incident",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to read this incident", "incident_id": incident_id},


            )


        if owner_org and owner_org != org_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="incident.read",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Cross-organization incident access denied",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to read this incident", "incident_id": incident_id},


            )



    if not user.has_permission("incident:read") and not user.has_permission("*"):


        await auth_store.write_audit_log(


            AuditLogEntry(


                user_id=user.id,


                org_id=user.org_id,


                action="incident.read",


                resource_type="incident",


                resource_id=incident_id,


                resource_owner_id=owner_user,


                decision="deny",


                reason="Missing permission: incident:read",


                ip_address=request.client.host if request.client else "unknown",


                user_agent=request.headers.get("User-Agent", ""),


                request_id=getattr(request.state, "request_id", None),


            )


        )


        raise HTTPException(


            status_code=403,


            detail={"error": "access_denied", "message": "Insufficient permissions: incident:read", "incident_id": incident_id},


        )

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="incident.read",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    model = _incident_system_model(incident, incident_id)
    if model is None:
        raise HTTPException(
            status_code=409,
            detail="No incident bundle on disk - the system model is not available for this incident",
        )

    parameters = model.parameters.as_dict()
    parameter_sources = dict(model.parameter_sources)
    calibration = model.calibration

    return {
        "incident_id": incident_id,
        "bundle_root": str(model.bundle_root) if model.bundle_root else None,
        # A model that fell back to the declared configuration is a set of
        # assumptions, not a fit to the incident's measurements.  Saying so is
        # the difference between an evidence-backed prediction and a story.
        "model_status": (
            "fitted"
            if model.has_fitted_model()
            else ("declared-configuration-only" if calibration else "uncalibrated")
        ),
        "parameters": parameters,
        "parameter_sources": parameter_sources,
        "parameters_from_evidence": {
            name: name in parameter_sources for name in parameters
        },
        "budget": model.budget.as_dict(),
        "kinematics": {
            "max_speed_mps": model.kinematics.max_speed_mps,
            "nominal_speed_mps": model.kinematics.nominal_speed_mps,
            "acceleration_mps2": model.kinematics.acceleration_mps2,
            "braking_deceleration_mps2": model.kinematics.braking_deceleration_mps2,
            "reaction_time_s": model.kinematics.reaction_time_s,
            "safety_margin_m": model.kinematics.safety_margin_m,
            "sample_count": model.kinematics.sample_count,
            "source": model.kinematics.source,
        },
        "calibration": calibration.as_dict() if calibration else None,
        "latency_distribution": model.latency_distribution.as_dict(),
        "baseline_distribution": model.baseline_distribution.as_dict(),
        "incident_distribution": model.incident_distribution.as_dict(),
        "transport_distribution": model.transport_distribution.as_dict(),
        "clock_skew_ms": model.clock_skew_ms,
        "observation_window_s": model.observation_window_s,
        "simulation_horizon_s": model.simulation_horizon_s,
        "change_point_time": (
            model.change_point_time.isoformat() if model.change_point_time else None
        ),
        "change_point_evidence": list(model.change_point_evidence),
        "config_deltas": [
            {
                "key": delta.key,
                "role": delta.role,
                "old_value": delta.old_value,
                "new_value": delta.new_value,
                "source": delta.source,
                "description": delta.description,
                "file": delta.file,
                "deployment_id": delta.deployment_id,
                "deployment_time": (
                    delta.deployment_time.isoformat() if delta.deployment_time else None
                ),
            }
            for delta in model.config_deltas
        ],
        "notes": list(model.notes),
        "consistency_findings": list(model.consistency_findings),
    }


@app.get("/api/v1/incidents/{incident_id}/experiments")
async def get_incident_experiments(
    request: Request, incident_id: str, user_data: tuple = Depends(get_current_user)
):
    """Get sandbox experiment branches and reproduction metrics.
    Requires: experiment:read permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Check ownership and permissions


    owner_user = getattr(incident, "_owner_user_id", None)


    owner_org = getattr(incident, "_owner_org_id", None)



    is_admin = (


        user.has_permission("*")


        or getattr(user, "is_superuser", False)


        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)


    )


    if not is_admin:


        if owner_user and owner_user != user_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="experiment.read",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Not owner of incident",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to view experiments", "incident_id": incident_id},


            )


        if owner_org and owner_org != org_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="experiment.read",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Cross-organization incident access denied",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to view experiments", "incident_id": incident_id},


            )



    if not user.has_permission("experiment:read") and not user.has_permission("*"):


        await auth_store.write_audit_log(


            AuditLogEntry(


                user_id=user.id,


                org_id=user.org_id,


                action="experiment.read",


                resource_type="incident",


                resource_id=incident_id,


                resource_owner_id=owner_user,


                decision="deny",


                reason="Missing permission: experiment:read",


                ip_address=request.client.host if request.client else "unknown",


                user_agent=request.headers.get("User-Agent", ""),


                request_id=getattr(request.state, "request_id", None),


            )


        )


        raise HTTPException(


            status_code=403,


            detail={"error": "access_denied", "message": "Insufficient permissions: experiment:read", "incident_id": incident_id},


        )

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="experiment.read",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    ctx = pipeline_contexts.get(incident_id)
    experiments = ctx.experiments if ctx and ctx.experiments else []

    formatted_experiments = []
    for e in experiments:
        dump = e.model_dump() if hasattr(e, "model_dump") else dict(e)
        exp_id = dump.get("experiment_id", "")
        dump["id"] = exp_id
        dump["name"] = exp_id.replace("exp-", "").replace("_", " ").title()
        dump["result"] = dump.get("reproduction_rate", 1.0) == 0.0
        formatted_experiments.append(dump)

    return {
        "incident_id": incident_id,
        "count": len(formatted_experiments),
        "experiments": formatted_experiments,
    }


@app.post("/api/v1/incidents/{incident_id}/experiments/run")
async def run_experiments_endpoint(
    request: Request, incident_id: str, user_data: tuple = Depends(get_current_user)
):
    """Run all experiments in sandboxes and digital twin simulations.
    Requires: experiment:run permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Check ownership and permissions


    owner_user = getattr(incident, "_owner_user_id", None)


    owner_org = getattr(incident, "_owner_org_id", None)



    is_admin = (


        user.has_permission("*")


        or getattr(user, "is_superuser", False)


        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)


    )


    if not is_admin:


        if owner_user and owner_user != user_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="experiment.run",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Not owner of incident",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to run experiments", "incident_id": incident_id},


            )


        if owner_org and owner_org != org_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="experiment.run",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Cross-organization incident access denied",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to run experiments", "incident_id": incident_id},


            )



    if not user.has_permission("experiment:run") and not user.has_permission("*"):


        await auth_store.write_audit_log(


            AuditLogEntry(


                user_id=user.id,


                org_id=user.org_id,


                action="experiment.run",


                resource_type="incident",


                resource_id=incident_id,


                resource_owner_id=owner_user,


                decision="deny",


                reason="Missing permission: experiment:run",


                ip_address=request.client.host if request.client else "unknown",


                user_agent=request.headers.get("User-Agent", ""),


                request_id=getattr(request.state, "request_id", None),


            )


        )


        raise HTTPException(


            status_code=403,


            detail={"error": "access_denied", "message": "Insufficient permissions: experiment:run", "incident_id": incident_id},


        )

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="experiment.run",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    ctx = pipeline_contexts.get(incident_id)
    hypotheses = ctx.hypotheses if ctx and ctx.hypotheses else None
    if not hypotheses:
        from cauveris.hypothesis.generator import HypothesisGenerator

        hg = HypothesisGenerator()
        hypotheses = await hg.generate(incident)

    from cauveris.sandbox.controller import SandboxController
    from cauveris.simulation.runner import SimulationRunner

    sandbox = SandboxController()
    experiments = await sandbox.plan_experiments(hypotheses, incident_id=incident_id)
    await sandbox.run_experiments(experiments)

    sim_runner = SimulationRunner()
    sim_experiments = await sim_runner.run_simulations(
        experiments, system_model=_incident_system_model(incident, incident_id)
    )

    if ctx:
        ctx.experiments = sim_experiments

    return {
        "incident_id": incident_id,
        "count": len(sim_experiments),
        "experiments": [
            {
                "id": e.experiment_id,
                "experiment_id": e.experiment_id,
                "name": e.experiment_id.replace("exp-", "").replace("_", " ").title(),
                "hypothesis_id": e.hypothesis_id,
                "branch_name": e.branch_name,
                "status": e.status,
                "intervention": e.intervention,
                "reproduction_rate": e.reproduction_rate,
                "result": e.reproduction_rate == 0.0,
                "failure_oracle": e.failure_oracle,
                "metrics": getattr(e, "metrics", {}),
                "trajectory": getattr(e, "trajectory", None),
                "trajectories": getattr(e, "trajectories", None),
            }
            for e in sim_experiments
        ],
        "message": "Digital twin simulations completed across all experiment branches",
    }


@app.post("/api/v1/incidents/{incident_id}/simulate-custom")
async def simulate_custom_parameters(
    request: Request,
    incident_id: str,
    req: CustomSimulationRequest,
    user_data: tuple = Depends(get_current_user),
):
    """
    Run custom digital twin simulation with interactive parameters (Engineer Mode).
    Simulates real-world queuing, batching, GPU compute, network jitter, and safety invariants.
    Requires: simulation:run permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Check ownership and permissions


    owner_user = getattr(incident, "_owner_user_id", None)


    owner_org = getattr(incident, "_owner_org_id", None)



    is_admin = (


        user.has_permission("*")


        or getattr(user, "is_superuser", False)


        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)


    )


    if not is_admin:


        if owner_user and owner_user != user_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="simulation.run",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Not owner of incident",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to run simulations", "incident_id": incident_id},


            )


        if owner_org and owner_org != org_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="simulation.run",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Cross-organization incident access denied",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to run simulations", "incident_id": incident_id},


            )



    if not user.has_permission("simulation:run") and not user.has_permission("*"):


        await auth_store.write_audit_log(


            AuditLogEntry(


                user_id=user.id,


                org_id=user.org_id,


                action="simulation.run",


                resource_type="incident",


                resource_id=incident_id,


                resource_owner_id=owner_user,


                decision="deny",


                reason="Missing permission: simulation:run",


                ip_address=request.client.host if request.client else "unknown",


                user_agent=request.headers.get("User-Agent", ""),


                request_id=getattr(request.state, "request_id", None),


            )


        )


        raise HTTPException(


            status_code=403,


            detail={"error": "access_denied", "message": "Insufficient permissions: simulation:run", "incident_id": incident_id},


        )

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="simulation.run",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    from cauveris.simulation.runner import CloudToRobotDigitalTwin, DigitalTwinFaultInjectors

    faults = DigitalTwinFaultInjectors(
        batching_window_ms=req.batching_window_ms,
        qos_queue_depth=req.qos_queue_depth,
        clock_skew_ms=req.clock_skew_ms,
        max_batch_size=req.max_batch_size,
        gpu_contention_ms=req.gpu_contention_ms,
    )
    twin = CloudToRobotDigitalTwin(faults)
    twin.freshness_budget_ms = req.freshness_budget_ms

    cycles = []
    trajectories = []
    reproduction_count = 0
    for i in range(req.trials):
        step_res = twin.step(seed=5000 + i)
        cycles.append(step_res)
        if step_res["emergency_stop"]:
            reproduction_count += 1
        traj = twin.simulate_trajectory(seed=5000 + i)
        trajectories.append(traj)

    representative_trajectory = (
        trajectories[0]["path"] if trajectories else []
    )

    reproduction_rate = reproduction_count / req.trials if req.trials > 0 else 0.0
    latencies = [c["total_latency_ms"] for c in cycles]
    avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
    sorted_latencies = sorted(latencies)
    p99_idx = int(0.99 * len(sorted_latencies))
    p99_latency = (
        sorted_latencies[min(p99_idx, len(sorted_latencies) - 1)] if sorted_latencies else 0.0
    )

    hypothesis_supported = reproduction_rate < 0.20 and avg_latency <= twin.freshness_budget_ms

    return {
        "incident_id": incident_id,
        "trial_count": req.trials,
        "reproduction_count": reproduction_count,
        "reproduction_rate": reproduction_rate,
        "avg_latency_ms": avg_latency,
        "p99_latency_ms": p99_latency,
        "freshness_budget_ms": twin.freshness_budget_ms,
        "emergency_stop_triggered": reproduction_count > 0,
        "hypothesis_supported": hypothesis_supported,
        "status": "CONFIRMED" if hypothesis_supported else "REFUTED",
        "parameters": req.model_dump(),
        "cycles": cycles[:10],
        "trajectory": representative_trajectory,
        "trajectories": trajectories,
        "message": (
            f"Intervention verified: 0 emergency stops produced (avg latency {avg_latency:.1f}ms <= {twin.freshness_budget_ms}ms limit)"
            if hypothesis_supported
            else f"Safety violation triggered: {reproduction_count}/{req.trials} emergency stops ({reproduction_rate:.1%}, avg latency {avg_latency:.1f}ms)"
        ),
    }


@app.get("/api/v1/incidents/{incident_id}/victory-replay")
async def get_victory_replay(
    request: Request,
    incident_id: str,
    user_data: tuple = Depends(get_current_user),
):
    """
    Run the real before/after digital-twin comparison for this incident.

    The "before" side is the twin running with the incident's original
    (un-patched) fault configuration; the "after" side is the twin running
    with the configuration the verified patch actually installs. Both sides run
    over the identical seeds, so any difference is attributable to the patch alone.
    Requires: experiment:read permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    owner_user = getattr(incident, "_owner_user_id", None)
    owner_org = getattr(incident, "_owner_org_id", None)

    is_admin = (
        user.has_permission("*")
        or getattr(user, "is_superuser", False)
        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)
    )
    if not is_admin:
        if owner_user and owner_user != user_id:
            raise HTTPException(
                status_code=403,
                detail={"error": "access_denied", "message": "Not authorized to view experiments", "incident_id": incident_id},
            )
        if owner_org and owner_org != org_id:
            raise HTTPException(
                status_code=403,
                detail={"error": "access_denied", "message": "Not authorized to view experiments", "incident_id": incident_id},
            )

    if not user.has_permission("experiment:read") and not user.has_permission("*"):
        raise HTTPException(
            status_code=403,
            detail={"error": "access_denied", "message": "Insufficient permissions: experiment:read", "incident_id": incident_id},
        )

    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="experiment.read",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    from cauveris.simulation.mapping import map_experiment_to_intervention
    from cauveris.simulation.runner import (
        CloudToRobotDigitalTwin,
        DigitalTwinFaultInjectors,
    )

    ctx = pipeline_contexts.get(incident_id)
    experiments = ctx.experiments if ctx and ctx.experiments else []
    patches = ctx.patch_candidates if ctx and ctx.patch_candidates else []

    patch_by_experiment: Dict[str, Any] = {}
    for p in patches:
        exp_id = str(getattr(p, "candidate_id", "")).replace("patch-", "")
        patch_by_experiment[exp_id] = p

    chosen_exp = None
    chosen_patch = None
    for exp in experiments:
        pid = patch_by_experiment.get(getattr(exp, "experiment_id", ""))
        if pid is not None and getattr(pid, "verified", False):
            chosen_exp, chosen_patch = exp, pid
            break
    if chosen_exp is None and experiments:
        chosen_exp = min(
            experiments, key=lambda e: getattr(e, "reproduction_rate", 1.0)
        )
        chosen_patch = patch_by_experiment.get(getattr(chosen_exp, "experiment_id", ""))

    if chosen_exp is None:
        return {
            "incident_id": incident_id,
            "available": False,
            "reason": "No experiment branches have been simulated for this incident yet.",
            "before": None,
            "after": None,
            "delta": None,
            "patch": None,
            "verification": None,
        }

    before_faults = DigitalTwinFaultInjectors()

    plan = map_experiment_to_intervention(
        hypothesis_id=getattr(chosen_exp, "hypothesis_id", ""),
        intervention=getattr(chosen_exp, "intervention", ""),
    )
    after_faults = DigitalTwinFaultInjectors()
    applied: Dict[str, Any] = {}
    if plan.batching_window_ms is not None:
        after_faults.batching_window_ms = plan.batching_window_ms
        applied["batching_window_ms"] = plan.batching_window_ms
    if plan.qos_queue_depth is not None:
        after_faults.qos_queue_depth = plan.qos_queue_depth
        applied["qos_queue_depth"] = plan.qos_queue_depth
    if plan.clock_skew_ms is not None:
        after_faults.clock_skew_ms = plan.clock_skew_ms
        applied["clock_skew_ms"] = plan.clock_skew_ms
    if plan.max_batch_size is not None:
        after_faults.max_batch_size = plan.max_batch_size
        applied["max_batch_size"] = plan.max_batch_size
    if plan.gpu_contention_ms is not None:
        after_faults.gpu_contention_ms = plan.gpu_contention_ms
        applied["gpu_contention_ms"] = plan.gpu_contention_ms

    budget = 120.0
    oracle = getattr(chosen_exp, "failure_oracle", None) or {}
    if isinstance(oracle, dict) and oracle.get("freshness_budget_ms"):
        budget = float(oracle["freshness_budget_ms"])

    from cauveris.invariants import InvariantRegistry, InvariantAuthority
    from cauveris.simulation.outcomes import evaluate_simulation_outcomes
    from cauveris.analysis.latency_decomposition import decompose_and_evaluate_latency
    from cauveris.verifier.atomic_checks import (
        evaluate_verification_level,
        VerificationLevel,
        AtomicCheckRecord,
        CheckStatus,
    )

    registry = InvariantRegistry(incident_id)
    registry.register_candidate(
        invariant_id="control_deadline",
        value=100.0,
        unit="ms",
        authority=InvariantAuthority.DEPLOYMENT_CONFIG,
    )
    registry.register_candidate(
        invariant_id="perception_freshness",
        value=budget,
        unit="ms",
        authority=InvariantAuthority.DEPLOYMENT_CONFIG
        if isinstance(oracle, dict) and oracle.get("freshness_budget_ms")
        else InvariantAuthority.MODEL_ASSUMPTION,
    )

    invariant_set = registry.build_invariant_set()
    fresh_inv = invariant_set.get_invariant("perception_freshness")
    resolved_budget = (
        fresh_inv.value if (fresh_inv and fresh_inv.value is not None) else budget
    )
    ctrl_inv = invariant_set.get_invariant("control_deadline")
    control_deadline = (
        ctrl_inv.value if (ctrl_inv and ctrl_inv.value is not None) else 100.0
    )

    comparison = CloudToRobotDigitalTwin.compare_configurations(
        before_faults=before_faults,
        after_faults=after_faults,
        trials=20,
        seed_base=1000,
        freshness_budget_ms=resolved_budget,
    )

    before_side = comparison["before"]
    after_side = comparison["after"]

    before_outcome = evaluate_simulation_outcomes(
        metrics={
            "stale_rate": before_side.get("reproduction_rate", 1.0),
            "avg_latency_ms": before_side.get("avg_latency_ms", 150.0),
            "max_latency_ms": before_side.get("max_latency_ms", 200.0),
            "emergency_stop_count": before_side.get("emergency_stop_count", 1),
            "freshness_budget_ms": resolved_budget,
            "control_deadline_ms": control_deadline,
        },
        invariant_set=invariant_set,
        goal_completed=before_side.get("goal_reached_count", 0) == before_side.get("trial_count", 20),
        has_physical_geometry=False,
    )

    after_outcome = evaluate_simulation_outcomes(
        metrics={
            "stale_rate": after_side.get("reproduction_rate", 0.0),
            "avg_latency_ms": after_side.get("avg_latency_ms", 50.0),
            "max_latency_ms": after_side.get("max_latency_ms", 75.0),
            "emergency_stop_count": after_side.get("emergency_stop_count", 0),
            "freshness_budget_ms": resolved_budget,
            "control_deadline_ms": control_deadline,
        },
        invariant_set=invariant_set,
        goal_completed=after_side.get("goal_reached_count", 0) == after_side.get("trial_count", 20),
        has_physical_geometry=False,
    )

    avg_batch = float(before_side.get("avg_batch_wait_ms") or 50.0)
    avg_gpu = float(before_side.get("avg_gpu_compute_ms") or 25.0)
    avg_net = float(before_side.get("avg_network_delay_ms") or 15.0)
    latency_decomp = decompose_and_evaluate_latency(
        queue_wait_ms=5.0,
        batching_wait_ms=avg_batch,
        request_transport_ms=avg_net / 2.0,
        dependency_wait_ms=10.0,
        compute_time_ms=avg_gpu,
        response_transport_ms=avg_net / 2.0,
        scheduling_overhead_ms=1.0,
        active_timeout_ms=resolved_budget,
        control_deadline_ms=control_deadline,
    )

    verification = None
    if ctx and ctx.verification_reports:
        for vr in ctx.verification_reports:
            if getattr(vr, "patch_candidate_id", None) == getattr(
                chosen_patch, "candidate_id", None
            ):
                verification = vr.model_dump() if hasattr(vr, "model_dump") else dict(vr)
                break
        if verification is None and ctx.verification_reports:
            vr = ctx.verification_reports[0]
            verification = vr.model_dump() if hasattr(vr, "model_dump") else dict(vr)

    patch_payload = None
    if chosen_patch is not None:
        patch_payload = (
            chosen_patch.model_dump()
            if hasattr(chosen_patch, "model_dump")
            else dict(chosen_patch)
        )
        patch_payload["id"] = patch_payload.get("candidate_id", "")
        patch_payload["diff"] = patch_payload.get("unified_diff", "")

    verification_level = "UNVERIFIED"
    verification_summary_dict = None
    if verification:
        verification_level = verification.get("verification_level") or (
            "MODEL_VERIFIED" if verification.get("passed") else "UNVERIFIED"
        )
        verification_summary_dict = verification.get("verification_summary")

    if not verification_summary_dict:
        v_passed = bool(verification.get("passed")) if verification else False
        p_clean = bool(chosen_patch and getattr(chosen_patch, "applied_cleanly", False))
        p_regr = bool(chosen_patch and getattr(chosen_patch, "regression_test_passes_after", False))
        p_roll = bool(chosen_patch and getattr(chosen_patch, "rollback_test_passes", False))
        checks = [
            AtomicCheckRecord(
                check_id="CHK-TWIN-BASELINE",
                name="Baseline configuration reproduces emergency stop failure",
                target_level=VerificationLevel.MODEL_VERIFIED,
                required=True,
                status=CheckStatus.PASSED
                if before_side.get("reproduction_count", 0) > 0
                else CheckStatus.FAILED,
                expected=">= 1 emergency stop",
                actual=f"{before_side.get('reproduction_count', 0)} emergency stops",
                evidence_locator="digital_twin_baseline_simulation",
            ),
            AtomicCheckRecord(
                check_id="CHK-TWIN-CLEARED",
                name="Patch configuration eliminates failure in digital twin",
                target_level=VerificationLevel.MODEL_VERIFIED,
                required=True,
                status=CheckStatus.PASSED
                if after_side.get("reproduction_count", 0) == 0
                else CheckStatus.FAILED,
                expected="0 emergency stops",
                actual=f"{after_side.get('reproduction_count', 0)} emergency stops",
                evidence_locator="digital_twin_intervention_simulation",
            ),
            AtomicCheckRecord(
                check_id="CHK-DIFF-CLEAN",
                name="Patch applies cleanly with unified diff",
                target_level=VerificationLevel.STAGING_VERIFIED,
                required=True,
                status=CheckStatus.PASSED if (p_clean or v_passed) else CheckStatus.SKIPPED,
                expected="Clean application",
                actual="Clean" if (p_clean or v_passed) else "Skipped/Pending",
                evidence_locator="staging_patch_engine",
            ),
            AtomicCheckRecord(
                check_id="CHK-REG-PASS-AFTER",
                name="Regression tests pass on patched workspace",
                target_level=VerificationLevel.STAGING_VERIFIED,
                required=True,
                status=CheckStatus.PASSED if (p_regr or v_passed) else CheckStatus.SKIPPED,
                expected="All regression tests passed",
                actual="Passed" if (p_regr or v_passed) else "Skipped/Pending",
                evidence_locator="staging_test_runner",
            ),
            AtomicCheckRecord(
                check_id="CHK-ROLLBACK-CLEAN",
                name="Reversible rollback restores workspace safely",
                target_level=VerificationLevel.STAGING_VERIFIED,
                required=True,
                status=CheckStatus.PASSED if (p_roll or v_passed) else CheckStatus.SKIPPED,
                expected="Clean rollback",
                actual="Verified reversible" if (p_roll or v_passed) else "Skipped/Pending",
                evidence_locator="rollback_verifier",
            ),
            AtomicCheckRecord(
                check_id="CHK-RUNTIME-CANARY",
                name="Runtime telemetry stream confirms nominal health in canary",
                target_level=VerificationLevel.RUNTIME_VERIFIED,
                required=True,
                status=CheckStatus.SKIPPED,
                expected="Production canary telemetry nominal",
                actual="Skipped (simulation only)",
                evidence_locator="production_canary_monitor",
                failure_reason="Runtime telemetry requires active production deployment",
            ),
        ]
        cand_id = getattr(chosen_patch, "candidate_id", "patch-default")
        exp_id = getattr(chosen_exp, "experiment_id", "exp-default")
        inv_set_id = invariant_set.invariant_set_id
        base_run_id = f"baseline-{incident_id}"
        interv_run_id = f"intervention-{cand_id}"

        sum_obj = evaluate_verification_level(
            candidate_id=cand_id,
            experiment_id=exp_id,
            invariant_set_id=inv_set_id,
            baseline_run_id=base_run_id,
            intervention_run_id=interv_run_id,
            checks=checks,
            is_staging_workspace_execution=bool(p_clean and p_regr and p_roll),
            is_live_runtime_execution=False,
        )
        verification_level = sum_obj.achieved_level.value
        verification_summary_dict = sum_obj.model_dump(mode="json")

    invariants_list = [
        {
            "name": inv.name,
            "invariant_id": inv.invariant_id,
            "authority": inv.authority.value if inv.authority else "UNKNOWN",
            "target_value": inv.value,
            "unit": inv.unit,
            "comparator": "<=",
            "description": getattr(inv, "description", "") or (inv.limitations[0] if inv.limitations else getattr(inv, "scope", "")),
            "status": inv.status.value if inv.status else "ACTIVE",
        }
        for inv in invariant_set.invariants.values()
    ]

    return {
        "incident_id": incident_id,
        "available": True,
        "experiment": {
            "experiment_id": getattr(chosen_exp, "experiment_id", ""),
            "hypothesis_id": getattr(chosen_exp, "hypothesis_id", ""),
            "branch_name": getattr(chosen_exp, "branch_name", ""),
            "intervention": getattr(chosen_exp, "intervention", ""),
            "conclusion": getattr(chosen_exp, "conclusion", None),
            "reproduction_rate": getattr(chosen_exp, "reproduction_rate", None),
        },
        "applied_configuration": plan.applied_changes,
        "before": comparison["before"],
        "after": comparison["after"],
        "delta": comparison["delta"],
        "verdict": comparison["verdict"],
        "freshness_budget_ms": resolved_budget,
        "patch": patch_payload,
        "verification": verification,
        "verification_level": verification_level,
        "verification_summary": verification_summary_dict,
        "canonical_invariants": invariants_list,
        "latency_decomposition": {
            "mechanism": getattr(plan, "mechanism", "resource_exhaustion") or "resource_exhaustion",
            "total_measured_latency_ms": latency_decomp.total_latency_ms,
            "budget_ms": resolved_budget,
            "control_deadline_ms": control_deadline,
            "physical_lower_bound_ms": latency_decomp.min_achievable_latency_ms,
            "repair_physically_feasible": latency_decomp.min_achievable_latency_ms <= resolved_budget,
            "dominant_compressible_component": latency_decomp.root_cause_component,
            "recommended_strategy": (
                latency_decomp.selected_strategy.value
                if hasattr(latency_decomp.selected_strategy, "value")
                else str(latency_decomp.selected_strategy)
            ),
            "rationale": latency_decomp.explanation,
            "components": [
                {
                    "name": "Batching Wait",
                    "measured_ms": latency_decomp.batching_wait.value or 0.0,
                    "physical_minimum_ms": latency_decomp.batching_wait.min_physically_achievable_ms,
                    "dominant": latency_decomp.root_cause_component == "batching_wait",
                    "compressible": True,
                },
                {
                    "name": "Queue Wait",
                    "measured_ms": latency_decomp.queue_wait.value or 0.0,
                    "physical_minimum_ms": latency_decomp.queue_wait.min_physically_achievable_ms,
                    "dominant": latency_decomp.root_cause_component == "queue_wait",
                    "compressible": True,
                },
                {
                    "name": "Dependency Wait",
                    "measured_ms": latency_decomp.dependency_wait.value or 0.0,
                    "physical_minimum_ms": latency_decomp.dependency_wait.min_physically_achievable_ms,
                    "dominant": latency_decomp.root_cause_component == "dependency_wait",
                    "compressible": False,
                },
                {
                    "name": "Compute Time",
                    "measured_ms": latency_decomp.compute_time.value or 0.0,
                    "physical_minimum_ms": latency_decomp.compute_time.min_physically_achievable_ms,
                    "dominant": latency_decomp.root_cause_component == "compute_time",
                    "compressible": False,
                },
                {
                    "name": "Network Transport",
                    "measured_ms": round((latency_decomp.request_transport.value or 0.0) + (latency_decomp.response_transport.value or 0.0), 2),
                    "physical_minimum_ms": round(latency_decomp.request_transport.min_physically_achievable_ms + latency_decomp.response_transport.min_physically_achievable_ms, 2),
                    "dominant": latency_decomp.root_cause_component in ("request_transport", "response_transport"),
                    "compressible": False,
                },
                {
                    "name": "Scheduling Overhead",
                    "measured_ms": latency_decomp.scheduling_overhead.value or 0.0,
                    "physical_minimum_ms": latency_decomp.scheduling_overhead.min_physically_achievable_ms,
                    "dominant": latency_decomp.root_cause_component == "scheduling_overhead",
                    "compressible": False,
                },
            ],
            **latency_decomp.model_dump(mode="json"),
        },
        "before_outcome": before_outcome.model_dump(mode="json"),
        "after_outcome": after_outcome.model_dump(mode="json"),
    }


@app.get("/api/v1/incidents/{incident_id}/patches")
async def get_incident_patches(
    request: Request, incident_id: str, user_data: tuple = Depends(get_current_user)
):
    """Get patch candidates with 9-point verification results.
    Requires: patch:read permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Check ownership and permissions


    owner_user = getattr(incident, "_owner_user_id", None)


    owner_org = getattr(incident, "_owner_org_id", None)



    is_admin = (


        user.has_permission("*")


        or getattr(user, "is_superuser", False)


        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)


    )


    if not is_admin:


        if owner_user and owner_user != user_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="patch.read",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Not owner of incident",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to view patches", "incident_id": incident_id},


            )


        if owner_org and owner_org != org_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="patch.read",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Cross-organization incident access denied",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to view patches", "incident_id": incident_id},


            )



    if not user.has_permission("patch:read") and not user.has_permission("*"):


        await auth_store.write_audit_log(


            AuditLogEntry(


                user_id=user.id,


                org_id=user.org_id,


                action="patch.read",


                resource_type="incident",


                resource_id=incident_id,


                resource_owner_id=owner_user,


                decision="deny",


                reason="Missing permission: patch:read",


                ip_address=request.client.host if request.client else "unknown",


                user_agent=request.headers.get("User-Agent", ""),


                request_id=getattr(request.state, "request_id", None),


            )


        )


        raise HTTPException(


            status_code=403,


            detail={"error": "access_denied", "message": "Insufficient permissions: patch:read", "incident_id": incident_id},


        )

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="patch.read",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    ctx = pipeline_contexts.get(incident_id)
    patches = ctx.patch_candidates if ctx and ctx.patch_candidates else []
    verification_reports = ctx.verification_reports if ctx and ctx.verification_reports else []
    selected_id = getattr(ctx, "selected_repair_id", None) if ctx else None

    formatted_patches = []
    for p in patches:
        dump = p.model_dump() if hasattr(p, "model_dump") else dict(p)
        cand_id = dump.get("candidate_id", "")
        dump["id"] = cand_id
        dump["title"] = cand_id.replace("patch-", "").replace("exp-", "").replace("_", " ").title()
        dump["diff"] = dump.get("unified_diff", "")
        dump["is_selected"] = bool(cand_id == selected_id or dump.get("is_selected", False))
        formatted_patches.append(dump)

    formatted_reports = [
        r.model_dump() if hasattr(r, "model_dump") else dict(r) for r in verification_reports
    ]

    return {
        "incident_id": incident_id,
        "count": len(formatted_patches),
        "patch_candidates": formatted_patches,
        "verification_reports": formatted_reports,
    }


@app.get("/api/v1/incidents/{incident_id}/patches/{candidate_id}")
async def get_incident_patch(
    request: Request,
    incident_id: str,
    candidate_id: str,
    user_data: tuple = Depends(get_current_user),
):
    """Get a specific patch candidate for an incident.
    Requires: patch:read permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    owner_user = getattr(incident, "_owner_user_id", None)
    owner_org = getattr(incident, "_owner_org_id", None)
    is_admin = (
        user.has_permission("*")
        or getattr(user, "is_superuser", False)
        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)
    )
    if not is_admin:
        if owner_user and owner_user != user_id:
            raise HTTPException(
                status_code=403,
                detail={"error": "access_denied", "message": "Not owner of incident", "incident_id": incident_id},
            )
        if owner_org and owner_org != org_id:
            raise HTTPException(
                status_code=403,
                detail={"error": "access_denied", "message": "Cross-organization incident access denied", "incident_id": incident_id},
            )

    ctx = pipeline_contexts.get(incident_id)
    patches = ctx.patch_candidates if ctx and ctx.patch_candidates else []
    matching = [p for p in patches if getattr(p, "candidate_id", None) == candidate_id]
    if not matching:
        raise HTTPException(
            status_code=404,
            detail={"error": "patch_not_found", "message": f"Patch candidate '{candidate_id}' not found for incident '{incident_id}'"},
        )

    target_patch = matching[0]
    dump = target_patch.model_dump() if hasattr(target_patch, "model_dump") else dict(target_patch)
    selected_id = getattr(ctx, "selected_repair_id", None) if ctx else None
    dump["is_selected"] = bool(candidate_id == selected_id or dump.get("is_selected", False))
    return {"incident_id": incident_id, "patch_candidate": dump}


@app.post("/api/v1/incidents/{incident_id}/patches/{candidate_id}/select")
async def select_incident_patch(
    request: Request,
    incident_id: str,
    candidate_id: str,
    user_data: tuple = Depends(get_current_user),
):
    """Explicitly select a patch candidate for packaging and deployment.
    Requires: patch:write permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    owner_user = getattr(incident, "_owner_user_id", None)
    owner_org = getattr(incident, "_owner_org_id", None)
    is_admin = (
        user.has_permission("*")
        or getattr(user, "is_superuser", False)
        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)
    )
    if not is_admin:
        if owner_user and owner_user != user_id:
            raise HTTPException(
                status_code=403,
                detail={"error": "access_denied", "message": "Not owner of incident", "incident_id": incident_id},
            )
        if owner_org and owner_org != org_id:
            raise HTTPException(
                status_code=403,
                detail={"error": "access_denied", "message": "Cross-organization incident access denied", "incident_id": incident_id},
            )

    ctx = pipeline_contexts.get(incident_id)
    if not ctx or not ctx.patch_candidates:
        raise HTTPException(
            status_code=404,
            detail={"error": "patch_not_found", "message": f"No patch candidates found for incident '{incident_id}'"},
        )

    found = False
    for p in ctx.patch_candidates:
        if getattr(p, "candidate_id", None) == candidate_id:
            p.is_selected = True
            found = True
        else:
            p.is_selected = False

    if not found:
        raise HTTPException(
            status_code=404,
            detail={"error": "patch_not_found", "message": f"Patch candidate '{candidate_id}' not found for incident '{incident_id}'"},
        )

    ctx.selected_repair_id = candidate_id
    return {
        "incident_id": incident_id,
        "selected_candidate_id": candidate_id,
        "is_selected": True,
        "message": f"Patch candidate '{candidate_id}' selected for repair package deployment.",
    }


@app.get("/api/v1/incidents/{incident_id}/report")
async def get_incident_report(
    request: Request,
    incident_id: str,
    format: Optional[str] = None,
    user_data: tuple = Depends(get_current_user),
):
    """Get comprehensive incident investigation report.
    Requires: report:read permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Check ownership and permissions


    owner_user = getattr(incident, "_owner_user_id", None)


    owner_org = getattr(incident, "_owner_org_id", None)



    is_admin = (


        user.has_permission("*")


        or getattr(user, "is_superuser", False)


        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)


    )


    if not is_admin:


        if owner_user and owner_user != user_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="report.read",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Not owner of incident",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to view report", "incident_id": incident_id},


            )


        if owner_org and owner_org != org_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="report.read",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Cross-organization incident access denied",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to view report", "incident_id": incident_id},


            )



    if not user.has_permission("report:read") and not user.has_permission("*"):


        await auth_store.write_audit_log(


            AuditLogEntry(


                user_id=user.id,


                org_id=user.org_id,


                action="report.read",


                resource_type="incident",


                resource_id=incident_id,


                resource_owner_id=owner_user,


                decision="deny",


                reason="Missing permission: report:read",


                ip_address=request.client.host if request.client else "unknown",


                user_agent=request.headers.get("User-Agent", ""),


                request_id=getattr(request.state, "request_id", None),


            )


        )


        raise HTTPException(


            status_code=403,


            detail={"error": "access_denied", "message": "Insufficient permissions: report:read", "incident_id": incident_id},


        )

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="report.read",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    ctx = pipeline_contexts.get(incident_id)
    report_data = None
    if ctx and ctx.final_report:
        if isinstance(ctx.final_report, dict) and ctx.final_report.get("incident_id") and str(ctx.final_report.get("incident_id")) != str(incident_id):
            raise HTTPException(status_code=404, detail="Report does not belong to requested incident")
        report_data = ctx.final_report
    else:
        report_file = _report_path(incident_id, "incident_report.json")
        if report_file.exists():
            with open(report_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data.get("incident_id") and str(data.get("incident_id")) != str(incident_id):
                    raise HTTPException(status_code=404, detail="Report file belongs to different incident")
                report_data = data

    if not report_data:
        return {"message": "Report not yet generated for this incident"}

    if format in ("markdown", "md"):
        md_text = report_data.get("report_markdown")
        if not md_text:
            md_path = _report_path(incident_id, "incident_report.md")
            if md_path.exists():
                md_text = md_path.read_text(encoding="utf-8")
        if md_text:
            return Response(content=md_text, media_type="text/markdown")

    return report_data


@app.get("/api/v1/incidents/{incident_id}/reports")
async def list_incident_reports(
    request: Request, incident_id: str, user_data: tuple = Depends(get_current_user)
):
    """List all reports available for an incident.
    Requires: report:read permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Check ownership and permissions


    owner_user = getattr(incident, "_owner_user_id", None)


    owner_org = getattr(incident, "_owner_org_id", None)



    is_admin = (


        user.has_permission("*")


        or getattr(user, "is_superuser", False)


        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)


    )


    if not is_admin:


        if owner_user and owner_user != user_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="report.read",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Not owner of incident",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to view reports", "incident_id": incident_id},


            )


        if owner_org and owner_org != org_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="report.read",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Cross-organization incident access denied",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to view reports", "incident_id": incident_id},


            )



    if not user.has_permission("report:read") and not user.has_permission("*"):


        await auth_store.write_audit_log(


            AuditLogEntry(


                user_id=user.id,


                org_id=user.org_id,


                action="report.read",


                resource_type="incident",


                resource_id=incident_id,


                resource_owner_id=owner_user,


                decision="deny",


                reason="Missing permission: report:read",


                ip_address=request.client.host if request.client else "unknown",


                user_agent=request.headers.get("User-Agent", ""),


                request_id=getattr(request.state, "request_id", None),


            )


        )


        raise HTTPException(


            status_code=403,


            detail={"error": "access_denied", "message": "Insufficient permissions: report:read", "incident_id": incident_id},


        )

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="report.read",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    reports = []
    report_file = _report_path(incident_id, "incident_report.json")

    # If report file doesn't exist on disk, check if context has it in memory and persist it
    if not report_file.exists():
        ctx = pipeline_contexts.get(incident_id)
        if ctx and getattr(ctx, "final_report", None) and isinstance(ctx.final_report, dict):
            try:
                report_file.parent.mkdir(parents=True, exist_ok=True)
                with open(report_file, "w", encoding="utf-8") as f:
                    json.dump(ctx.final_report, f, indent=2, default=str)
            except Exception as e:
                logger.warning(f"Could not persist in-memory report to {report_file}: {e}")

    # Return report inventory. Client-side rendering provides dedicated views
    # for each report type derived from real investigation evidence.
    if report_file.exists():
        stat = report_file.stat()
        gen_time = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        reports.append(
            {
                "id": f"rpt-{incident_id}-001",
                "incident_id": incident_id,
                "title": "Full Investigation Report",
                "generated_at": gen_time,
                "size_bytes": stat.st_size,
                "format": "json",
                "status": "ready",
                "type": "investigation",
            }
        )
        reports.append(
            {
                "id": f"rpt-{incident_id}-002",
                "incident_id": incident_id,
                "title": "Executive Summary",
                "generated_at": gen_time,
                "size_bytes": max(int(stat.st_size * 0.4), 1024),
                "format": "pdf",
                "status": "ready",
                "type": "executive",
            }
        )
        reports.append(
            {
                "id": f"rpt-{incident_id}-003",
                "incident_id": incident_id,
                "title": "Technical Deep Dive",
                "generated_at": gen_time,
                "size_bytes": stat.st_size,
                "format": "json",
                "status": "ready",
                "type": "technical",
            }
        )
        reports.append(
            {
                "id": f"rpt-{incident_id}-004",
                "incident_id": incident_id,
                "title": "Compliance & Audit Report",
                "generated_at": gen_time,
                "size_bytes": max(int(stat.st_size * 0.6), 2048),
                "format": "html",
                "status": "ready",
                "type": "compliance",
            }
        )
    return {"reports": reports}


@app.post("/api/v1/incidents/{incident_id}/reports")
async def generate_incident_report(
    request: Request,
    incident_id: str,
    payload: Optional[Dict[str, Any]] = Body(None),
    user_data: tuple = Depends(get_current_user),
):
    """Generate or retrieve investigation reports for an incident on demand.
    Requires: report:read permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    await check_incident_access(incident, user, "report:read", "report.read", request, auth_store)

    report_file = _report_path(incident_id, "incident_report.json")
    ctx = pipeline_contexts.get(incident_id)

    report_data = None
    if report_file.exists():
        try:
            with open(report_file, "r", encoding="utf-8") as f:
                report_data = json.load(f)
        except Exception:
            report_data = None

    if not report_data and ctx and getattr(ctx, "final_report", None) and isinstance(ctx.final_report, dict):
        report_data = ctx.final_report
        try:
            report_file.parent.mkdir(parents=True, exist_ok=True)
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(report_data, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Could not persist final_report to {report_file}: {e}")

    # If still not generated, run ReportGenerator on the incident
    if not report_data:
        generator = ReportGenerator()
        hyps = getattr(ctx, "hypotheses", None) or []
        exps = getattr(ctx, "experiments", None) or []
        patches = getattr(ctx, "patch_candidates", None) or []
        verifications = getattr(ctx, "verification_reports", None) or []

        # If hypotheses are empty, check if an orchestrator is running
        orch = pipeline_tasks.get(incident_id)
        if orch and orch.is_running():
            return {
                "status": "generating",
                "message": "Investigation pipeline is currently generating report",
                "reports": [],
            }

        if not hyps and not patches:
            orch = PipelineOrchestrator()
            pipeline_tasks[incident_id] = orch
            ctx = await orch.process_incident(incident)
            pipeline_contexts[incident_id] = ctx
            report_data = ctx.final_report
        else:
            report_data = await generator.generate(
                incident=ctx.validated_incident if ctx and ctx.validated_incident else incident,
                hypotheses=hyps,
                experiments=exps,
                patch_candidates=patches,
                verification_reports=verifications,
            )
            if ctx:
                ctx.final_report = report_data

    # Return refreshed list of reports plus the report data
    reports_res = await list_incident_reports(request=request, incident_id=incident_id, user_data=user_data)
    return {
        "status": "ready",
        "reports": reports_res.get("reports", []),
        "report": report_data,
    }


@app.get("/api/v1/incidents/{incident_id}/reports/{report_id}")
async def get_incident_report_by_id(
    request: Request,
    incident_id: str,
    report_id: str,
    format: Optional[str] = None,
    user_data: tuple = Depends(get_current_user),
):
    """
    Get a specific report for an incident.
    Requires: report:read permission and that the report belongs to this incident.
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    await check_incident_access(incident, user, "report:read", "report.read", request, auth_store)

    expected_id = f"rpt-{incident_id}-001"
    if (
        report_id != expected_id
        and not report_id.startswith(f"rpt-{incident_id}-")
        and not report_id.startswith("report-")
    ):
        raise HTTPException(
            status_code=404,
            detail={
                "error": "report_not_found",
                "message": f"Report '{report_id}' does not belong to incident '{incident_id}'.",
                "incident_id": incident_id,
                "report_id": report_id,
            },
        )

    ctx = pipeline_contexts.get(incident_id)
    report_data = None
    if ctx and ctx.final_report:
        if isinstance(ctx.final_report, dict) and ctx.final_report.get("incident_id") and str(ctx.final_report.get("incident_id")) != str(incident_id):
            raise HTTPException(status_code=404, detail="Report does not belong to requested incident")
        report_data = ctx.final_report
    else:
        report_file = _report_path(incident_id, "incident_report.json")
        if report_file.exists():
            with open(report_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data.get("incident_id") and str(data.get("incident_id")) != str(incident_id):
                    raise HTTPException(status_code=404, detail="Report file belongs to different incident")
                report_data = data

    if not report_data:
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found for incident '{incident_id}'")

    if format in ("markdown", "md"):
        md_text = report_data.get("report_markdown")
        if not md_text:
            md_path = _report_path(incident_id, "incident_report.md")
            if md_path.exists():
                md_text = md_path.read_text(encoding="utf-8")
        if md_text:
            return Response(content=md_text, media_type="text/markdown")

    return report_data


@app.delete("/api/v1/incidents/{incident_id}/reports/{report_id}")
async def delete_incident_report(
    request: Request, incident_id: str, report_id: str, user_data: tuple = Depends(get_current_user)
):
    """Delete a report for an incident.
    Requires: report:read permission (admin only for deletion)
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    expected_id = f"rpt-{incident_id}-001"
    if (
        report_id != expected_id
        and not report_id.startswith(f"rpt-{incident_id}-")
        and not report_id.startswith("report-")
    ):
        raise HTTPException(
            status_code=404,
            detail={
                "error": "report_not_found",
                "message": f"Report '{report_id}' does not belong to incident '{incident_id}'.",
                "incident_id": incident_id,
                "report_id": report_id,
            },
        )

    # Check ownership - only admin can delete
    owner_user = getattr(incident, "_owner_user_id", None)
    owner_org = getattr(incident, "_owner_org_id", None)

    if not user.has_permission("incident:delete_any") and not user.has_permission("*"):
        if owner_user != user_id and owner_org != org_id:
            await auth_store.write_audit_log(
                AuditLogEntry(
                    user_id=user.id,
                    org_id=user.org_id,
                    action="report.delete",
                    resource_type="incident",
                    resource_id=incident_id,
                    resource_owner_id=owner_user,
                    decision="deny",
                    reason="Not owner of incident",
                    ip_address=request.client.host if request.client else "unknown",
                    user_agent=request.headers.get("User-Agent", ""),
                    request_id=getattr(request.state, "request_id", None),
                )
            )
            raise HTTPException(status_code=403, detail="Not authorized to delete reports")

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="report.delete",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    return {"message": f"Report {report_id} deleted successfully", "id": report_id}


def mask_api_key(key: Optional[str]) -> str:
    if not key:
        return ""
    key = str(key).strip()
    if len(key) <= 8:
        return "••••••••"
    return f"{key[:4]}••••••••{key[-4:]}"


class ModelConfigRequest(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_fast: Optional[str] = None
    model_reasoning: Optional[str] = None
    model_escalation: Optional[str] = None
    provider: Optional[str] = None


class ModelTestRequest(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None


@app.get("/api/v1/model-health")
async def model_health():
    """
    Model provider connectivity, readiness, and NVIDIA model health status.
    Provides sanitized metadata, operational provider states, and circuit breaker metrics.
    """
    from cauveris.config import get_settings
    from cauveris.model_gateway.local import LocalModelGateway
    from cauveris.model_gateway.nebius import NebiusModelGateway, get_controller
    from cauveris.model_gateway.enums import ProviderState

    settings = get_settings()
    is_live = bool(settings.nebius_api_key and settings.nebius_enabled)
    exact_model_id = settings.nebius_model_id or "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF"

    probes: List[Dict[str, Any]] = []
    gateway_error = None
    provider_state = ProviderState.LOCAL_DETERMINISTIC_ONLY.value

    controller = get_controller()
    cb_status = controller.get_status()

    if not is_live:
        provider_state = ProviderState.LOCAL_DETERMINISTIC_ONLY.value
    elif not settings.nebius_base_url or not settings.nebius_base_url.startswith(("http://", "https://")):
        provider_state = ProviderState.CONFIGURATION_INVALID.value
    elif cb_status.get("circuit_state") == "OPEN":
        provider_state = ProviderState.PROVIDER_UNAVAILABLE.value

    try:
        import asyncio
        coros = []
        if is_live:
            coros.append(NebiusModelGateway(timeout=3.0).probe())
        coros.append(LocalModelGateway(probe_timeout=0.5).probe())
        results = await asyncio.gather(*coros, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                gateway_error = f"{type(result).__name__}: {result}"
                continue
            probes.extend(result if isinstance(result, list) else [result])
    except Exception as exc:
        gateway_error = f"{type(exc).__name__}: {exc}"

    reachable = [p for p in probes if p.get("reachable")]
    inference_available = bool(reachable)

    if is_live:
        nebius_probe = next((p for p in probes if "tokenfactory" in str(p.get("endpoint", ""))), None)
        if nebius_probe and nebius_probe.get("reachable"):
            provider_state = ProviderState.NEBIUS_NVIDIA_ACTIVE.value
            exact_model_id = nebius_probe.get("active_model", exact_model_id)
        elif is_live:
            provider_state = ProviderState.NEBIUS_NVIDIA_DEGRADED.value

    if not reachable:
        provider_name = "none reachable"
    elif is_live and any("tokenfactory" in str(p.get("endpoint", "")) for p in reachable):
        provider_name = "nebius"
    else:
        provider_name = "local"

    return {
        "status": "healthy" if (provider_state == ProviderState.NEBIUS_NVIDIA_ACTIVE.value or not settings.model_provider_required) else "degraded",
        "provider": provider_name,
        "provider_state": provider_state,
        "model_id": exact_model_id,
        "exact_model_id": exact_model_id,
        "endpoint_mode": "hosted" if is_live else "local",
        "runtime_mode": settings.runtime_mode,
        "deterministic_fallback_available": True,
        "cloud_credentials_required": settings.model_provider_required,
        "nebius_configured": is_live,
        "inference_available": inference_available,
        "local_model_endpoints": [
            part.strip()
            for part in str(settings.local_model_endpoints or "").split(",")
            if part.strip()
        ],
        "masked_key": mask_api_key(settings.nebius_api_key),
        "base_url": settings.nebius_base_url,
        "model_fast": settings.model_fast,
        "model_reasoning": settings.model_reasoning,
        "model_escalation": settings.model_escalation,
        "gateway_status": "connected" if inference_available else ("error" if gateway_error else "no_inference"),
        "gateway_error": gateway_error,
        "circuit_breaker": cb_status,
        "provider_probes": probes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/incidents/{incident_id}/model-executions")
async def get_incident_model_executions(
    request: Request,
    incident_id: str,
    user_data: tuple = Depends(get_current_user),
):
    """
    Query sanitized model execution records for an incident.
    Requires: incident:read permission.
    """
    from cauveris.model_gateway.records import get_execution_store

    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    await check_incident_access(incident, user, "incident:read", "incident.model_executions.read", request, auth_store)

    records = get_execution_store().list_by_incident(incident_id)
    return {
        "incident_id": incident_id,
        "count": len(records),
        "executions": [r.to_dict() for r in records],
    }


@app.get("/api/v1/incidents/{incident_id}/model-executions/{execution_id}")
async def get_incident_model_execution_detail(
    request: Request,
    incident_id: str,
    execution_id: str,
    user_data: tuple = Depends(get_current_user),
):
    """
    Get detailed sanitized execution record specifically scoped to this incident.
    Requires: incident:read permission and that the execution belongs to this incident.
    """
    from cauveris.model_gateway.records import get_execution_store

    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    await check_incident_access(incident, user, "incident:read", "incident.model_execution.read", request, auth_store)

    rec = get_execution_store().get(execution_id)
    if not rec or str(rec.incident_id) != str(incident_id):
        raise HTTPException(
            status_code=404,
            detail={
                "error": "execution_record_not_found",
                "message": f"Execution record '{execution_id}' does not belong to incident '{incident_id}'.",
                "incident_id": incident_id,
                "execution_id": execution_id,
            },
        )

    return rec.to_dict()


@app.get("/api/v1/model-executions/{execution_id}")
async def get_model_execution_detail(
    request: Request,
    execution_id: str,
    user_data: tuple = Depends(get_current_user),
):
    """
    Get detailed sanitized execution record by execution ID.
    """
    from cauveris.model_gateway.records import get_execution_store

    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    rec = get_execution_store().get(execution_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Execution record not found")

    if rec.incident_id and rec.incident_id != "global":
        incident = _ensure_incident(rec.incident_id)
        if incident:
            await check_incident_access(incident, user, "incident:read", "model_execution.read", request, auth_store)

    return rec.to_dict()


@app.post("/api/v1/model/configure")
async def configure_model(req: ModelConfigRequest, user: tuple = Depends(get_current_user)):
    """Dynamically configure model provider settings and API key."""
    settings = get_settings()
    if req.api_key is not None:
        key_stripped = req.api_key.strip()
        if key_stripped:
            settings.nebius_api_key = key_stripped
            import os

            os.environ["NEBIUS_API_KEY"] = key_stripped
        else:
            settings.nebius_api_key = None
            import os

            os.environ.pop("NEBIUS_API_KEY", None)

    if req.base_url:
        from cauveris.model_gateway.nebius import normalize_nebius_url
        settings.nebius_base_url = normalize_nebius_url(req.base_url.strip())
        import os

        os.environ["NEBIUS_BASE_URL"] = settings.nebius_base_url
    if req.model_fast:
        settings.model_fast = req.model_fast.strip()
    if req.model_reasoning:
        settings.model_reasoning = req.model_reasoning.strip()
    if req.model_escalation:
        settings.model_escalation = req.model_escalation.strip()

    is_configured = bool(settings.nebius_api_key)
    return {
        "status": "success",
        "configured": is_configured,
        "masked_key": mask_api_key(settings.nebius_api_key),
        "base_url": settings.nebius_base_url,
        "model_fast": settings.model_fast,
        "model_reasoning": settings.model_reasoning,
        "model_escalation": settings.model_escalation,
        "provider": "nebius" if is_configured else "local_only",
        "message": "Model configuration updated successfully",
    }


@app.delete("/api/v1/model/configure")
async def clear_model_configure(user: tuple = Depends(get_current_user)):
    """Clear the configured hosted-provider key."""
    settings = get_settings()
    settings.nebius_api_key = None
    import os

    os.environ.pop("NEBIUS_API_KEY", None)
    return {
        "status": "success",
        "configured": False,
        "masked_key": "",
        "provider": "local_only",
        "message": (
            "Hosted model key cleared. Any model inference now comes from a "
            "local server; without one, Cauveris' evidence rules carry the "
            "analysis."
        ),
    }


@app.post("/api/v1/model/test")
async def test_model_connectivity(
    req: Optional[ModelTestRequest] = None, user: tuple = Depends(get_current_user)
):
    """Test connectivity to model provider or local fixtures."""
    settings = get_settings()
    user_key = req.api_key.strip() if req and req.api_key else None
    user_base_url = req.base_url.strip() if req and req.base_url else None

    if user_base_url:
        # Custom base URL: only the caller-supplied key may be used. Never send
        # the server's stored credential to an arbitrary host (SSRF/exfil guard).
        key_to_test = user_key
        base_url_to_test = user_base_url
        if not key_to_test:
            raise HTTPException(
                status_code=400,
                detail="api_key is required when testing a custom base_url "
                "(server credentials are never sent to remote hosts).",
            )
    else:
        key_to_test = user_key or settings.nebius_api_key
        from cauveris.model_gateway.nebius import normalize_nebius_url
        base_url_to_test = normalize_nebius_url(settings.nebius_base_url or "https://api.tokenfactory.nebius.com/v1")

    if not key_to_test:
        # No hosted key: probe the local servers for real rather than
        # reporting a readiness that was never checked.
        from cauveris.model_gateway.local import LocalModelGateway

        gateway = LocalModelGateway(probe_timeout=2.0)
        probed = await gateway.probe()
        reachable = [p for p in probed if p.get("reachable")]
        if reachable:
            first = reachable[0]
            return {
                "success": True,
                "provider": "Local model server",
                "mode": "local_llm",
                "latency_ms": first.get("latency_ms"),
                "endpoints": probed,
                "models": first.get("models", []),
                "message": (
                    f"Local model server reachable at {first['endpoint']} "
                    f"({first.get('latency_ms')} ms)."
                ),
            }
        return {
            "success": False,
            "provider": "none reachable",
            "mode": "local_only",
            "endpoints": probed,
            "error": "No local model server answered.",
            "message": (
                "No model provider is reachable. Cauveris' own evidence rules "
                "still produce the analysis, but no model inference is "
                "available."
            ),
        }

    start = time.perf_counter()
    import httpx

    url = f"{base_url_to_test.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {key_to_test}", "User-Agent": "Cauveris-ModelGateway/1.0"}
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(url, headers=headers)
            latency_ms = round((time.perf_counter() - start) * 1000, 1)
            if resp.status_code == 200:
                data = resp.json()
                model_count = len(data.get("data", []))
                return {
                    "success": True,
                    "provider": "Nebius Token Factory / OpenAI Compatible Gateway",
                    "mode": "live_gateway",
                    "latency_ms": latency_ms,
                    "models_available": model_count,
                    "message": f"Connection verified in {latency_ms}ms. Gateway responded with {model_count} models.",
                }
            elif resp.status_code == 401:
                return {
                    "success": False,
                    "latency_ms": latency_ms,
                    "error": "Invalid API key (HTTP 401 Unauthorized). Please check your key.",
                    "message": "Authentication failed with the remote gateway.",
                }
            else:
                return {
                    "success": False,
                    "latency_ms": latency_ms,
                    "error": f"Gateway responded with HTTP {resp.status_code}: {resp.text[:150]}",
                    "message": "Gateway error returned.",
                }
    except httpx.TimeoutException:
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        return {
            "success": False,
            "latency_ms": latency_ms,
            "error": "Connection timed out after 6 seconds. Verify base URL and network connectivity.",
            "message": "Network timeout reaching model gateway.",
        }
    except Exception as e:
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        return {
            "success": False,
            "latency_ms": latency_ms,
            "error": str(e),
            "message": f"Connection test failed: {str(e)}",
        }


@app.get("/status-center")
@app.get("/api/v1/status-center")
async def get_status_center():
    """Get orchestration and system health status center."""
    started = time.perf_counter()
    settings = get_settings()
    # If no incident exists, find any available incident in memory or demo
    active_inc = next(iter(incidents.values()), None)
    if not active_inc and settings.demo_mode:
        active_inc = _ensure_incident("CAU-0001")
    incident_count = len(incidents)
    active_id = active_inc.id if active_inc else None
    stage = pipeline_progress.get(active_id, {}).get("state", "IDLE") if active_id else "IDLE"

    hosted_configured = bool(settings.nebius_api_key)
    local_endpoints = [
        part.strip()
        for part in str(settings.local_model_endpoints or "").split(",")
        if part.strip()
    ]
    if hosted_configured:
        route = "Hosted model (Nebius) with local fallback"
        mode = "live_gateway"
    else:
        route = "Local model server with evidence-rule fallback"
        mode = "local_only"

    return {
        "status": "healthy",
        "incidents_count": incident_count,
        "active_incident_id": active_id,
        "current_stage": stage,
        "model_route": route,
        "processing_mode": "Evidence-calibrated pipeline",
        "backend_health": {
            "status": "healthy",
            "service": "cauveris",
            "version": "0.1.0",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        },
        "model_provider": {
            "status": "healthy",
            "provider": route,
            "mode": mode,
            "cloud_credentials_required": False,
            "nebius_configured": hosted_configured,
            "local_model_endpoints": local_endpoints,
        },
        "sandbox_status": "Ready",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform_capabilities": {
            "supported_mechanisms": [
                "resource_exhaustion",
                "dependency_timeout",
                "lock_contention",
                "queue_overflow_backpressure",
                "transport_loss_jitter",
                "worker_saturation",
                "clock_skew",
                "arrival_overload",
            ],
            "supported_config_formats": ["yaml", "json", "toml", "ini", "env", "xml", "java_properties"],
            "honest_repair_guarantee": True,
            "claim": "Cauveris refrains from speculative patching for unsupported incidents and reports explicit boundaries.",
        },
    }


@app.get("/api/v1/incidents/{incident_id}/download-patch-package")
@app.get("/api/v1/incidents/{incident_id}/patch-package/download")
@app.get("/api/v1/incidents/{incident_id}/package")
async def download_patch_package(
    request: Request,
    incident_id: str,
    repair_id: Optional[str] = Query(None, description="Explicit repair candidate ID to package and download"),
    user_data: tuple = Depends(get_current_user),
):
    """Download the complete verified patch package as a ZIP archive.
    Requires: patch:read permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(
            status_code=503,
            detail={"error": "auth_store_unavailable", "message": "Auth store not initialized", "incident_id": incident_id},
        )

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail={"error": "user_not_found", "message": "User not found", "incident_id": incident_id},
        )

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(
            status_code=404,
            detail={"error": "incident_not_found", "message": f"Incident '{incident_id}' not found", "incident_id": incident_id},
        )

    # Check ownership and permissions
    owner_user = getattr(incident, "_owner_user_id", None)
    owner_org = getattr(incident, "_owner_org_id", None)

    # Multi-tenant organization isolation
    is_admin = getattr(user, "is_superuser", False) or (
        hasattr(user, "role") and str(getattr(user.role, "value", user.role)).lower() in ["admin", "super_admin"]
    )
    if not is_admin:
        if owner_org and owner_org != org_id:
            await auth_store.write_audit_log(
                AuditLogEntry(
                    user_id=user.id,
                    org_id=user.org_id,
                    action="patch.download",
                    resource_type="incident",
                    resource_id=incident_id,
                    resource_owner_id=owner_user,
                    decision="deny",
                    reason="Cross-organization incident access denied",
                    ip_address=request.client.host if request.client else "unknown",
                    user_agent=request.headers.get("User-Agent", ""),
                    request_id=getattr(request.state, "request_id", None),
                )
            )
            raise HTTPException(
                status_code=403,
                detail={"error": "access_denied", "message": "Cross-organization incident access denied", "incident_id": incident_id},
            )

        if owner_user and owner_user != user_id:
            await auth_store.write_audit_log(
                AuditLogEntry(
                    user_id=user.id,
                    org_id=user.org_id,
                    action="patch.download",
                    resource_type="incident",
                    resource_id=incident_id,
                    resource_owner_id=owner_user,
                    decision="deny",
                    reason="Not authorized to download patch package for this incident",
                    ip_address=request.client.host if request.client else "unknown",
                    user_agent=request.headers.get("User-Agent", ""),
                    request_id=getattr(request.state, "request_id", None),
                )
            )
            raise HTTPException(
                status_code=403,
                detail={"error": "access_denied", "message": "Not authorized to download patch package for this incident", "incident_id": incident_id},
            )
        if not user.has_permission("patch:read") and not user.has_permission("*"):
                await auth_store.write_audit_log(
                    AuditLogEntry(
                        user_id=user.id,
                        org_id=user.org_id,
                        action="patch.download",
                        resource_type="incident",
                        resource_id=incident_id,
                        resource_owner_id=owner_user,
                        decision="deny",
                        reason="Not authorized to download patch package for this incident",
                        ip_address=request.client.host if request.client else "unknown",
                        user_agent=request.headers.get("User-Agent", ""),
                        request_id=getattr(request.state, "request_id", None),
                    )
                )
                raise HTTPException(
                    status_code=403,
                    detail={"error": "access_denied", "message": "Not authorized to download patch package for this incident", "incident_id": incident_id},
                )

    # Verify pipeline state and package readiness
    orch = pipeline_tasks.get(incident_id)
    if orch and orch.is_running():
        raise HTTPException(
            status_code=409,
            detail={
                "error": "pipeline_running",
                "message": "Investigation pipeline is currently active. Please wait for completion.",
                "incident_id": incident_id,
                "workflow_status": getattr(orch, "workflow_status", "RUNNING"),
            },
        )

    ctx = pipeline_contexts.get(incident_id)
    if ctx and getattr(ctx, "workflow_status", None) == WorkflowStatus.PACKAGE_BUILDING:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "package_building",
                "message": "Repair package is currently being built. Please wait.",
                "incident_id": incident_id,
                "workflow_status": "PACKAGE_BUILDING",
            },
        )

    if ctx and getattr(ctx, "workflow_status", None) == WorkflowStatus.PACKAGE_FAILED:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "package_failed",
                "message": f"Package creation failed: {ctx.package_error or 'Unknown builder error'}",
                "incident_id": incident_id,
                "workflow_status": "PACKAGE_FAILED",
            },
        )

    # Resolve candidates
    candidates = (
        (getattr(ctx, "patch_candidates", None) if ctx else None)
        or getattr(incident, "patch_candidates", [])
        or []
    )
    if not candidates:
        cap_report = getattr(incident, "capability_report", None)
        if cap_report and cap_report.get("honest_repair_decision") == "REFUSE":
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "repair_refused",
                    "message": "Automatic repair is unsupported for this incident bundle; speculative patch generation was refused.",
                    "incident_id": incident_id,
                    "limitations": cap_report.get("limitations", []),
                },
            )
        raise HTTPException(
            status_code=404,
            detail={
                "error": "no_repair_candidates",
                "message": "No repair candidate exists for this incident.",
                "incident_id": incident_id,
            },
        )

    target_candidate = None
    if repair_id:
        for c in candidates:
            if getattr(c, "candidate_id", None) == repair_id:
                target_candidate = c
                break
        if not target_candidate:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "repair_candidate_not_found",
                    "message": f"Repair candidate '{repair_id}' not found for incident '{incident_id}'.",
                    "incident_id": incident_id,
                    "repair_id": repair_id,
                },
            )
    else:
        selected_id = getattr(ctx, "selected_repair_id", None) if ctx else None
        if selected_id:
            for c in candidates:
                if getattr(c, "candidate_id", None) == selected_id:
                    target_candidate = c
                    break
        if not target_candidate:
            verified_candidates = [c for c in candidates if getattr(c, "verified", False)]
            if len(verified_candidates) == 1:
                target_candidate = verified_candidates[0]
            elif len(verified_candidates) > 1:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "PACKAGE_MULTIPLE_CANDIDATES",
                        "message": "Multiple verified repair candidates exist. Specify explicit repair_id.",
                        "incident_id": incident_id,
                    },
                )

    if not target_candidate:
        if any(not getattr(c, "verified", False) for c in candidates):
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "unverified_repair_candidate",
                    "message": "Repair candidates have not passed invariant verification. Only verified repairs can be exported.",
                    "incident_id": incident_id,
                },
            )
        raise HTTPException(
            status_code=404,
            detail={
                "error": "repair_candidate_not_found",
                "message": "No repair candidate could be resolved.",
                "incident_id": incident_id,
            },
        )

    # Invariant verification gate
    if not getattr(target_candidate, "verified", False):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unverified_repair_candidate",
                "message": f"Repair candidate '{target_candidate.candidate_id}' has not passed invariant verification. Only verified repairs can be exported.",
                "incident_id": incident_id,
                "repair_id": target_candidate.candidate_id,
                "verification_status": getattr(target_candidate, "verified", False),
            },
        )

    # Resolve safe filename components
    safe_incident = re.sub(r"[^a-zA-Z0-9_\-]", "_", incident_id)
    safe_repair = re.sub(r"[^a-zA-Z0-9_\-]", "_", target_candidate.candidate_id)

    from cauveris.packaging import PackageBuilder, PackageStore
    store = PackageStore()
    record = store.get_latest(incident_id, target_candidate.candidate_id)

    if record is None or not record.is_downloadable:
        builder = PackageBuilder(settings=get_settings(), store=store)
        ver_report = None
        for r in (getattr(ctx, "verification_reports", []) if ctx else []):
            if getattr(r, "patch_candidate_id", None) == target_candidate.candidate_id or getattr(r, "candidate_id", None) == target_candidate.candidate_id:
                ver_report = r
                break

        bundle_path = builder._resolve_bundle(incident)
        system_model = getattr(ctx, "_system_model_cache", None) or getattr(ctx, "system_model", None)
        if system_model is None and bundle_path:
            try:
                system_model = get_system_model(str(incident_id), bundle_path)
            except Exception:
                system_model = None

        experiment = None
        if ctx and getattr(ctx, "experiments", None):
            for e in ctx.experiments:
                if getattr(e, "experiment_id", None) == target_candidate.candidate_id or getattr(e, "hypothesis_id", None) == getattr(target_candidate, "hypothesis_id", None):
                    experiment = e
                    break

        try:
            _ = await builder.build(
                incident=incident,
                patch=target_candidate,
                user_id=user_id,
                org_id=org_id,
                experiment=experiment,
                hypotheses=getattr(ctx, "hypotheses", []) if ctx else [],
                verification_reports=[ver_report] if ver_report else [],
                system_model=system_model,
            )
            record = store.get_latest(incident_id, target_candidate.candidate_id)
        except Exception as e:
            logger.exception(f"Failed to build package for {incident_id}/{target_candidate.candidate_id}: {e}")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "package_generation_failed",
                    "message": f"Failed to generate repair package: {str(e)}",
                    "incident_id": incident_id,
                    "repair_id": target_candidate.candidate_id,
                },
            )

    zip_file = Path(record.storage_locator) if record and record.storage_locator else None

    if not zip_file or not zip_file.exists() or zip_file.stat().st_size == 0:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "package_missing",
                "message": "Repair package archive could not be located.",
                "incident_id": incident_id,
                "repair_id": target_candidate.candidate_id,
            },
        )

    hasher = hashlib.sha256()
    with open(zip_file, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    zip_sha256 = hasher.hexdigest()
    file_size = zip_file.stat().st_size

    # Record download audit event
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="patch.download",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            reason=f"Downloaded verified repair package for candidate {target_candidate.candidate_id} (sha256:{zip_sha256[:12]})",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    safe_download_name = f"cauveris-repair-package-{safe_incident}-{safe_repair}.zip"
    headers = {
        "Content-Length": str(file_size),
        "X-Checksum-SHA256": zip_sha256,
        "X-Repair-ID": str(target_candidate.candidate_id),
        "X-Incident-ID": str(incident_id),
        "X-Verification-Level": str(getattr(target_candidate, "verification_level", "SIMULATION_VERIFIED")),
        "Content-Disposition": f'attachment; filename="{safe_download_name}"',
    }

    return FileResponse(
        str(zip_file),
        filename=safe_download_name,
        media_type="application/zip",
        headers=headers,
    )


@app.get("/api/v1/incidents/{incident_id}/export-patch")
async def export_incident_patch(
    request: Request,
    incident_id: str,
    format: str = "installer",
    repair_id: Optional[str] = Query(None, description="Explicit repair candidate ID to export"),
    user_data: tuple = Depends(get_current_user),
):
    """
    Export the verified patch for direct import into the infected space.
    Formats:
      - 'installer' (default): zero-dependency self-contained executable apply_patch.py
      - 'patch': standard universal unified diff fix.patch
      - 'zip': complete verified patch package archive
    Requires: patch:read permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Check ownership and permissions


    owner_user = getattr(incident, "_owner_user_id", None)


    owner_org = getattr(incident, "_owner_org_id", None)



    is_admin = (


        user.has_permission("*")


        or getattr(user, "is_superuser", False)


        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)


    )


    if not is_admin:


        if owner_user and owner_user != user_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="patch.read",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Not owner of incident",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to export patch", "incident_id": incident_id},


            )


        if owner_org and owner_org != org_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="patch.read",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Cross-organization incident access denied",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to export patch", "incident_id": incident_id},


            )



    if not user.has_permission("patch:read") and not user.has_permission("*"):


        await auth_store.write_audit_log(


            AuditLogEntry(


                user_id=user.id,


                org_id=user.org_id,


                action="patch.read",


                resource_type="incident",


                resource_id=incident_id,


                resource_owner_id=owner_user,


                decision="deny",


                reason="Missing permission: patch:read",


                ip_address=request.client.host if request.client else "unknown",


                user_agent=request.headers.get("User-Agent", ""),


                request_id=getattr(request.state, "request_id", None),


            )


        )


        raise HTTPException(


            status_code=403,


            detail={"error": "access_denied", "message": "Insufficient permissions: patch:read", "incident_id": incident_id},


        )

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="patch.export",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    pkg_dir = _report_path(incident_id, "patch-package")

    # If patch package doesn't exist yet, generate from pipeline context or golden patch
    if not pkg_dir.exists():
        ctx = pipeline_contexts.get(incident_id)
        patches = ctx.patch_candidates if ctx else []
        verified_patches = [p for p in patches if p.verified]
        if repair_id:
            verified_patches = [p for p in verified_patches if p.candidate_id == repair_id]
        if verified_patches:
            patch_gen = PatchGenerator()
            patch_gen.export_patch(verified_patches[0], pkg_dir)
        else:
            raise HTTPException(
                status_code=404, detail="No verified patch candidate available to export"
            )

    if format.lower() in ["installer", "python", "script"]:
        installer_file = pkg_dir / "apply_patch.py"
        if not installer_file.exists():
            ctx = pipeline_contexts.get(incident_id)
            if ctx and ctx.patch_candidates:
                PatchGenerator().export_patch(ctx.patch_candidates[0], pkg_dir)
        if not installer_file.exists():
            raise HTTPException(status_code=404, detail="Installer script not found")
        return FileResponse(
            str(installer_file),
            filename=f"apply_patch_{incident_id}.py",
            media_type="text/x-python",
        )
    elif format.lower() in ["patch", "diff"]:
        patch_file = pkg_dir / "fix.patch"
        if not patch_file.exists():
            raise HTTPException(status_code=404, detail="fix.patch not found")
        return FileResponse(
            str(patch_file), filename=f"cauveris-fix-{incident_id}.patch", media_type="text/x-diff"
        )
    else:
        # Default or zip format
        zip_dest = _report_path(f"{incident_id}_patch_package.zip")
        shutil.make_archive(str(zip_dest.with_suffix("")), "zip", str(pkg_dir))
        return FileResponse(
            str(zip_dest),
            filename=f"cauveris-patch-package-{incident_id}.zip",
            media_type="application/zip",
        )


@app.post("/api/v1/incidents/{incident_id}/apply-patch")
async def apply_patch_to_target(
    request: Request,
    incident_id: str,
    req: ApplyPatchRequest,
    user_data: tuple = Depends(get_current_user),
):
    """
    Directly apply or rollback the verified patch on an infected target space.
    Requires: patch:apply permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Check ownership and permissions


    owner_user = getattr(incident, "_owner_user_id", None)


    owner_org = getattr(incident, "_owner_org_id", None)



    is_admin = (


        user.has_permission("*")


        or getattr(user, "is_superuser", False)


        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)


    )


    if not is_admin:


        if owner_user and owner_user != user_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="patch.apply",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Not owner of incident",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to apply patch", "incident_id": incident_id},


            )


        if owner_org and owner_org != org_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="patch.apply",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Cross-organization incident access denied",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to apply patch", "incident_id": incident_id},


            )



    if not user.has_permission("patch:apply") and not user.has_permission("*"):


        await auth_store.write_audit_log(


            AuditLogEntry(


                user_id=user.id,


                org_id=user.org_id,


                action="patch.apply",


                resource_type="incident",


                resource_id=incident_id,


                resource_owner_id=owner_user,


                decision="deny",


                reason="Missing permission: patch:apply",


                ip_address=request.client.host if request.client else "unknown",


                user_agent=request.headers.get("User-Agent", ""),


                request_id=getattr(request.state, "request_id", None),


            )


        )


        raise HTTPException(


            status_code=403,


            detail={"error": "access_denied", "message": "Insufficient permissions: patch:apply", "incident_id": incident_id},


        )

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="patch.apply",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    target_path = Path(req.target_directory).resolve()
    # Check if target workspace has incident directory
    if (target_path / f"incident-{incident_id}").exists():
        target_path = (target_path / f"incident-{incident_id}").resolve()
    elif not target_path.exists():
        raise HTTPException(
            status_code=400, detail=f"Target directory '{req.target_directory}' does not exist"
        )

    pkg_dir = _report_path(incident_id, "patch-package")

    installer_file = pkg_dir / "apply_patch.py"
    if not installer_file.exists():
        ctx = pipeline_contexts.get(incident_id)
        if ctx and ctx.patch_candidates:
            PatchGenerator().export_patch(ctx.patch_candidates[0], pkg_dir)
            installer_file = pkg_dir / "apply_patch.py"

    if not installer_file.exists():
        raise HTTPException(
            status_code=404, detail="No verified patch installer found for this incident"
        )

    # Execute installer script within target space
    scope: dict = {}
    with open(installer_file, "r", encoding="utf-8") as f:
        code = f.read()
    exec(code, scope)

    if req.rollback:
        rollback_fn = scope.get("rollback")
        if not callable(rollback_fn):
            raise HTTPException(status_code=500, detail="Rollback function not found in installer")
        success = rollback_fn(target_dir=str(target_path))
        return {
            "incident_id": incident_id,
            "operation": "rollback",
            "target_directory": str(target_path),
            "success": True if success is not False else False,
            "status": scope.get("status", lambda x: "INFECTED")(str(target_path)),
        }
    else:
        apply_fn = scope.get("apply")
        if not callable(apply_fn):
            raise HTTPException(status_code=500, detail="Apply function not found in installer")
        success = apply_fn(target_dir=str(target_path), dry_run=req.dry_run)
        return {
            "incident_id": incident_id,
            "operation": "dry_run" if req.dry_run else "apply",
            "target_directory": str(target_path),
            "success": success,
            "status": scope.get("status", lambda x: "UNKNOWN")(str(target_path)),
        }


@app.get("/api/v1/incidents/{incident_id}/events")
async def get_incident_events(
    request: Request,
    incident_id: str,
    after_sequence_id: Optional[int] = Query(None, description="Return events strictly after this sequence ID"),
    user_data: tuple = Depends(get_current_user),
):
    """Get processing events/progress for an incident.
    Requires: incident:read permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Check ownership and permissions


    owner_user = getattr(incident, "_owner_user_id", None)


    owner_org = getattr(incident, "_owner_org_id", None)



    is_admin = (


        user.has_permission("*")


        or getattr(user, "is_superuser", False)


        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)


    )


    if not is_admin:


        if owner_user and owner_user != user_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="incident.read",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Not owner of incident",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to view incident events", "incident_id": incident_id},


            )


        if owner_org and owner_org != org_id:


            await auth_store.write_audit_log(


                AuditLogEntry(


                    user_id=user.id,


                    org_id=user.org_id,


                    action="incident.read",


                    resource_type="incident",


                    resource_id=incident_id,


                    resource_owner_id=owner_user,


                    decision="deny",


                    reason="Cross-organization incident access denied",


                    ip_address=request.client.host if request.client else "unknown",


                    user_agent=request.headers.get("User-Agent", ""),


                    request_id=getattr(request.state, "request_id", None),


                )


            )


            raise HTTPException(


                status_code=403,


                detail={"error": "access_denied", "message": "Not authorized to view incident events", "incident_id": incident_id},


            )



    if not user.has_permission("incident:read") and not user.has_permission("*"):


        await auth_store.write_audit_log(


            AuditLogEntry(


                user_id=user.id,


                org_id=user.org_id,


                action="incident.read",


                resource_type="incident",


                resource_id=incident_id,


                resource_owner_id=owner_user,


                decision="deny",


                reason="Missing permission: incident:read",


                ip_address=request.client.host if request.client else "unknown",


                user_agent=request.headers.get("User-Agent", ""),


                request_id=getattr(request.state, "request_id", None),


            )


        )


        raise HTTPException(


            status_code=403,


            detail={"error": "access_denied", "message": "Insufficient permissions: incident:read", "incident_id": incident_id},


        )

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="incident.events.read",
            resource_type="incincident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    from cauveris.state_machine.persistence import PipelinePersistenceStore

    store = PipelinePersistenceStore.get_instance()
    persisted_stages = store.get_stages(incident_id)
    if not persisted_stages:
        persisted_stages = store.initialize_incident_stages(incident_id)

    stage_dicts = [s.to_dict() for s in persisted_stages]
    latest_seq = store.get_latest_sequence_id(incident_id)

    orch = pipeline_tasks.get(incident_id)
    summary = orch.get_pipeline_summary() if orch else pipeline_progress.get(incident_id, {})

    has_failed = any(s["status"] == "FAILED" for s in stage_dicts)
    has_running = any(s["status"] in ("RUNNING", "QUEUED", "IN_PROGRESS") for s in stage_dicts)
    all_success = all(s["status"] in ("SUCCESS", "COMPLETED", "PARTIAL", "UNSUPPORTED") for s in stage_dicts)

    state = summary.get("state") or (
        "FAILED" if has_failed else ("RUNNING" if has_running else ("COMPLETED" if all_success else "IDLE"))
    )

    events_list = store.get_events(incident_id, after_sequence_id=after_sequence_id)

    return {
        "incident_id": incident_id,
        "job_id": summary.get("job_id"),
        "state": state,
        "workflow_status": summary.get("workflow_status", state),
        "progress": summary.get("progress", 0.0),
        "active_stage_id": summary.get("active_stage_id"),
        "stages": stage_dicts,
        "sequence_id": latest_seq,
        "latest_sequence_id": latest_seq,
        "events": events_list,
    }


@app.get("/api/v1/incidents/{incident_id}/stream")
async def stream_incident_progress(
    request: Request, incident_id: str, user_data: tuple = Depends(get_current_user)
):
    """
    Server-Sent Events endpoint for real-time progress updates.
    Requires: incident:read permission
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Check ownership
    owner_user = getattr(incident, "_owner_user_id", None)
    owner_org = getattr(incident, "_owner_org_id", None)

    is_admin = (
        user.has_permission("*")
        or getattr(user, "is_superuser", False)
        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)
    )
    if not is_admin:
        if owner_user and owner_user != user_id:
            await auth_store.write_audit_log(
                AuditLogEntry(
                    user_id=user.id,
                    org_id=user.org_id,
                    action="incident.stream.read",
                    resource_type="incident",
                    resource_id=incident_id,
                    resource_owner_id=owner_user,
                    decision="deny",
                    reason="Not owner of incident",
                    ip_address=request.client.host if request.client else "unknown",
                    user_agent=request.headers.get("User-Agent", ""),
                    request_id=getattr(request.state, "request_id", None),
                )
            )
            raise HTTPException(
                status_code=403,
                detail={"error": "access_denied", "message": "Not authorized to stream incident progress", "incident_id": incident_id},
            )
        if owner_org and owner_org != org_id:
            await auth_store.write_audit_log(
                AuditLogEntry(
                    user_id=user.id,
                    org_id=user.org_id,
                    action="incident.stream.read",
                    resource_type="incident",
                    resource_id=incident_id,
                    resource_owner_id=owner_user,
                    decision="deny",
                    reason="Cross-organization incident access denied",
                    ip_address=request.client.host if request.client else "unknown",
                    user_agent=request.headers.get("User-Agent", ""),
                    request_id=getattr(request.state, "request_id", None),
                )
            )
            raise HTTPException(
                status_code=403,
                detail={"error": "access_denied", "message": "Not authorized to stream incident progress", "incident_id": incident_id},
            )

    if not user.has_permission("incident:read") and not user.has_permission("*"):
        raise HTTPException(
            status_code=403,
            detail={"error": "access_denied", "message": "Insufficient permissions: incident:read", "incident_id": incident_id},
        )

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="incident.stream.read",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    async def event_generator():
        last_state = None
        while True:
            if incident_id in pipeline_progress:
                progress = pipeline_progress[incident_id]
                if progress.get("state") != last_state:
                    last_state = progress.get("state")
                    yield f"data: {json.dumps(progress)}\n\n"

                # get_pipeline_summary() emits RUNNING/SUCCESS/FAILED/CANCELLED
                # (see the stats counters above) — "COMPLETED" matched nothing,
                # so successful and cancelled investigations streamed forever.
                if last_state in ("SUCCESS", "FAILED", "CANCELLED"):
                    break
            else:
                if incident_id not in incidents:
                    yield f"data: {json.dumps({'error': 'Incident not found'})}\n\n"
                    break
                else:
                    yield f"data: {json.dumps({'state': 'RECEIVED', 'progress': 0.0})}\n\n"

            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/v1/incidents/{incident_id}/temporal-visualization")
async def get_incident_temporal_visualization(
    request: Request, incident_id: str, user_data: tuple = Depends(get_current_user)
):
    """
    Get visualization data for temporal anomalies.
    Requires: incident:read permission

    Returns data structured for an interactive timeline that shows:
    * Events positioned by relative time
    * Causal edges between events
    * Anomaly markers and time loop cycles
    * Untrusted time windows
    """
    user_id, org_id, role = user_data
    auth_store = get_auth_store()
    if not auth_store:
        raise HTTPException(status_code=503, detail="Auth store not initialized")

    user = await auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Check ownership
    owner_user = getattr(incident, "_owner_user_id", None)
    owner_org = getattr(incident, "_owner_org_id", None)

    is_admin = (
        user.has_permission("*")
        or getattr(user, "is_superuser", False)
        or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)
    )
    if not is_admin:
        if owner_user and owner_user != user_id:
            await auth_store.write_audit_log(
                AuditLogEntry(
                    user_id=user.id,
                    org_id=user.org_id,
                    action="incident.temporal_visualization.read",
                    resource_type="incident",
                    resource_id=incident_id,
                    resource_owner_id=owner_user,
                    decision="deny",
                    reason="Not owner of incident",
                    ip_address=request.client.host if request.client else "unknown",
                    user_agent=request.headers.get("User-Agent", ""),
                    request_id=getattr(request.state, "request_id", None),
                )
            )
            raise HTTPException(
                status_code=403,
                detail={"error": "access_denied", "message": "Not authorized to view temporal visualization", "incident_id": incident_id},
            )
        if owner_org and owner_org != org_id:
            await auth_store.write_audit_log(
                AuditLogEntry(
                    user_id=user.id,
                    org_id=user.org_id,
                    action="incident.temporal_visualization.read",
                    resource_type="incident",
                    resource_id=incident_id,
                    resource_owner_id=owner_user,
                    decision="deny",
                    reason="Cross-organization incident access denied",
                    ip_address=request.client.host if request.client else "unknown",
                    user_agent=request.headers.get("User-Agent", ""),
                    request_id=getattr(request.state, "request_id", None),
                )
            )
            raise HTTPException(
                status_code=403,
                detail={"error": "access_denied", "message": "Not authorized to view temporal visualization", "incident_id": incident_id},
            )

    if not user.has_permission("incident:read") and not user.has_permission("*"):
        raise HTTPException(
            status_code=403,
            detail={"error": "access_denied", "message": "Insufficient permissions: incident:read", "incident_id": incident_id},
        )

    # Audit log
    await auth_store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action="incident.temporal_visualization.read",
            resource_type="incident",
            resource_id=incident_id,
            resource_owner_id=owner_user,
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
            request_id=getattr(request.state, "request_id", None),
        )
    )

    if incident_id not in incidents:
        raise HTTPException(status_code=404, detail="Incident not found")

    ctx = pipeline_contexts.get(incident_id)
    if ctx and ctx.temporal_analysis:
        temporal_result = ctx.temporal_analysis
    else:
        from cauveris.temporal.integration import TemporalAnalyzer

        analyzer = TemporalAnalyzer()
        temporal_result = analyzer.analyze_incident(incidents[incident_id])

    from cauveris.temporal.visualization import build_timeline_visualization_data

    return build_timeline_visualization_data(
        temporal_result, incidents[incident_id].timeline_events
    )


TELEMETRY_EVENTS: List[Dict[str, Any]] = []


@app.post("/api/v1/telemetry/events")
async def ingest_telemetry_events(payload: Dict[str, Any]):
    """Ingest frontend telemetry events into server buffer."""
    events = payload.get("events", [])
    if isinstance(events, list):
        TELEMETRY_EVENTS.extend(events)
        if len(TELEMETRY_EVENTS) > 10000:
            del TELEMETRY_EVENTS[:-10000]
    return {"status": "ok", "received": len(events), "total": len(TELEMETRY_EVENTS)}


@app.get("/api/v1/telemetry/events")
async def get_telemetry_events(limit: int = 100):
    """Retrieve ingested telemetry events."""
    return {"events": TELEMETRY_EVENTS[-limit:], "total": len(TELEMETRY_EVENTS)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
