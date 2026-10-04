"""
User-Friendly Error Classes for Cauveris Backend

Provides structured error information with:
- Error code for programmatic handling
- Human-readable message
- Context for debugging
- Retryable flag for automatic retry logic
- Troubleshooting steps for user guidance
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from enum import Enum

from fastapi import HTTPException
from fastapi.responses import JSONResponse


class ErrorSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class TroubleshootingStep:
    step: int
    description: str
    action: Optional[str] = None  # Optional action user can take


@dataclass
class CauverisErrorConfig:
    code: str
    message: str
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    context: Dict[str, Any] = field(default_factory=dict)
    retryable: bool = False
    retry_after_ms: int = 0
    troubleshooting_steps: List[TroubleshootingStep] = field(default_factory=list)
    cause: Optional[Exception] = None
    status_code: Optional[int] = None


class CauverisError(Exception):
    """Base exception class for all Cauveris errors with structured metadata."""

    def __init__(self, config: CauverisErrorConfig):
        super().__init__(config.message)
        self.code = config.code
        self.message = config.message
        self.severity = config.severity
        self.context = config.context
        self.retryable = config.retryable
        self.retry_after_ms = config.retry_after_ms
        self.troubleshooting_steps = config.troubleshooting_steps
        self.cause = config.cause
        self.status_code = config.status_code
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.correlation_id = get_correlation_id()

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for JSON serialization."""
        return {
            "name": self.__class__.__name__,
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "context": self.context,
            "retryable": self.retryable,
            "retry_after_ms": self.retry_after_ms,
            "troubleshooting_steps": [
                {"step": s.step, "description": s.description, "action": s.action}
                for s in self.troubleshooting_steps
            ],
            "cause": str(self.cause) if self.cause else None,
            "status_code": self.status_code,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
        }

    def to_user_string(self) -> str:
        """Format error as user-friendly string."""
        parts = [f"[{self.code}] {self.message}"]

        if self.context:
            parts.append(f"Context: {self.context}")

        if self.troubleshooting_steps:
            parts.append("\nTroubleshooting:")
            for step in self.troubleshooting_steps:
                parts.append(f"  {step.step}. {step.description}")
                if step.action:
                    parts.append(f"     Action: {step.action}")

        if self.correlation_id:
            parts.append(f"\nCorrelation ID: {self.correlation_id}")

        return "\n".join(parts)


# Correlation ID management
_correlation_id: str = ""


def set_correlation_id(correlation_id: str) -> None:
    """Set the current correlation ID."""
    global _correlation_id
    _correlation_id = correlation_id


def get_correlation_id() -> str:
    """Get the current correlation ID, generating one if needed."""
    global _correlation_id
    if not _correlation_id:
        _correlation_id = f"corr-{int(datetime.now(timezone.utc).timestamp())}-{uuid.uuid4().hex[:8]}"
    return _correlation_id


def clear_correlation_id() -> None:
    """Clear the current correlation ID."""
    global _correlation_id
    _correlation_id = ""


# Predefined error codes
class ErrorCodes:
    # Network/Connection errors
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT = "TIMEOUT"
    CONNECTION_REFUSED = "CONNECTION_REFUSED"
    DNS_ERROR = "DNS_ERROR"

    # API errors
    API_ERROR = "API_ERROR"
    API_UNAUTHORIZED = "API_UNAUTHORIZED"
    API_FORBIDDEN = "API_FORBIDDEN"
    API_NOT_FOUND = "API_NOT_FOUND"
    API_RATE_LIMITED = "API_RATE_LIMITED"
    API_SERVER_ERROR = "API_SERVER_ERROR"
    API_VALIDATION_ERROR = "API_VALIDATION_ERROR"

    # Incident errors
    INCIDENT_NOT_FOUND = "INCIDENT_NOT_FOUND"
    INCIDENT_ALREADY_EXISTS = "INCIDENT_ALREADY_EXISTS"
    INCIDENT_PROCESSING = "INCIDENT_PROCESSING"
    INCIDENT_FAILED = "INCIDENT_FAILED"

    # Pipeline errors
    PIPELINE_FAILED = "PIPELINE_FAILED"
    PIPELINE_STAGE_FAILED = "PIPELINE_STAGE_FAILED"
    PIPELINE_CANCELLED = "PIPELINE_CANCELLED"
    PIPELINE_TIMEOUT = "PIPELINE_TIMEOUT"

    # Evidence errors
    EVIDENCE_UPLOAD_FAILED = "EVIDENCE_UPLOAD_FAILED"
    EVIDENCE_VALIDATION_FAILED = "EVIDENCE_VALIDATION_FAILED"
    EVIDENCE_SECRETS_DETECTED = "EVIDENCE_SECRETS_DETECTED"
    EVIDENCE_CHECKSUM_MISMATCH = "EVIDENCE_CHECKSUM_MISMATCH"
    EVIDENCE_TOO_LARGE = "EVIDENCE_TOO_LARGE"
    EVIDENCE_UNSUPPORTED_TYPE = "EVIDENCE_UNSUPPORTED_TYPE"

    # Patch errors
    PATCH_GENERATION_FAILED = "PATCH_GENERATION_FAILED"
    PATCH_VERIFICATION_FAILED = "PATCH_VERIFICATION_FAILED"
    PATCH_APPLY_FAILED = "PATCH_APPLY_FAILED"
    PATCH_ROLLBACK_FAILED = "PATCH_ROLLBACK_FAILED"
    PATCH_CONFLICT = "PATCH_CONFLICT"

    # Experiment errors
    EXPERIMENT_FAILED = "EXPERIMENT_FAILED"
    SIMULATION_FAILED = "SIMULATION_FAILED"
    SANDBOX_UNAVAILABLE = "SANDBOX_UNAVAILABLE"

    # Model/Provider errors
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MODEL_API_ERROR = "MODEL_API_ERROR"
    MODEL_RATE_LIMITED = "MODEL_RATE_LIMITED"
    MODEL_INVALID_RESPONSE = "MODEL_INVALID_RESPONSE"

    # Configuration errors
    CONFIG_MISSING = "CONFIG_MISSING"
    CONFIG_INVALID = "CONFIG_INVALID"
    CONFIG_MIGRATION_NEEDED = "CONFIG_MIGRATION_NEEDED"


# Factory functions for common errors

def network_error(message: str = "Network request failed", cause: Optional[Exception] = None) -> CauverisError:
    return CauverisError(CauverisErrorConfig(
        code=ErrorCodes.NETWORK_ERROR,
        message=message,
        severity=ErrorSeverity.HIGH,
        retryable=True,
        retry_after_ms=5000,
        cause=cause,
        troubleshooting_steps=[
            TroubleshootingStep(1, "Check your internet connection", "retry"),
            TroubleshootingStep(2, "Verify the backend server is running on port 8000", "check_backend"),
            TroubleshootingStep(3, "Try refreshing the page", "refresh"),
            TroubleshootingStep(4, "Check browser console for detailed error", "check_console"),
        ],
    ))


def timeout_error(endpoint: str, timeout_ms: int = 15000) -> CauverisError:
    return CauverisError(CauverisErrorConfig(
        code=ErrorCodes.TIMEOUT,
        message=f"Request to {endpoint} timed out after {timeout_ms}ms",
        severity=ErrorSeverity.HIGH,
        context={"endpoint": endpoint, "timeout_ms": timeout_ms},
        retryable=True,
        retry_after_ms=10000,
        troubleshooting_steps=[
            TroubleshootingStep(1, "The backend may be under heavy load", "retry"),
            TroubleshootingStep(2, "Try again in a few seconds", "retry"),
            TroubleshootingStep(3, "If persistent, check backend performance", "check_backend"),
        ],
    ))


def api_error(status_code: int, message: str, endpoint: str, cause: Optional[Exception] = None) -> CauverisError:
    code_map = {
        400: ErrorCodes.API_VALIDATION_ERROR,
        401: ErrorCodes.API_UNAUTHORIZED,
        403: ErrorCodes.API_FORBIDDEN,
        404: ErrorCodes.API_NOT_FOUND,
        429: ErrorCodes.API_RATE_LIMITED,
        500: ErrorCodes.API_SERVER_ERROR,
        502: ErrorCodes.API_SERVER_ERROR,
        503: ErrorCodes.API_SERVER_ERROR,
        504: ErrorCodes.TIMEOUT,
    }

    code = code_map.get(status_code, ErrorCodes.API_ERROR)
    retryable = status_code in [429, 500, 502, 503, 504]

    troubleshooting = [TroubleshootingStep(1, f"API returned {status_code}: {message}")]

    if status_code == 401:
        troubleshooting.append(TroubleshootingStep(2, "Authentication required - please log in again", "login"))
    elif status_code == 403:
        troubleshooting.append(TroubleshootingStep(2, "Insufficient permissions for this operation", "contact_support"))
    elif status_code == 404:
        troubleshooting.append(TroubleshootingStep(2, "The requested resource was not found", "refresh"))
    elif status_code == 429:
        troubleshooting.append(TroubleshootingStep(2, "Rate limited - wait before retrying", "wait_retry"))
        troubleshooting.append(TroubleshootingStep(3, "Reduce request frequency", "reduce_frequency"))
    elif status_code >= 500:
        troubleshooting.append(TroubleshootingStep(2, "Backend server error - try again later", "retry"))
        troubleshooting.append(TroubleshootingStep(3, "Check backend logs for details", "check_backend"))

    return CauverisError(CauverisErrorConfig(
        code=code,
        message=message,
        severity=ErrorSeverity.HIGH if status_code >= 500 else ErrorSeverity.MEDIUM,
        context={"endpoint": endpoint, "status_code": status_code},
        retryable=retryable,
        retry_after_ms=30000 if status_code == 429 else 5000,
        cause=cause,
        status_code=status_code,
        troubleshooting_steps=troubleshooting,
    ))


def incident_not_found(incident_id: str) -> CauverisError:
    return CauverisError(CauverisErrorConfig(
        code=ErrorCodes.INCIDENT_NOT_FOUND,
        message=f"Incident {incident_id} not found",
        severity=ErrorSeverity.MEDIUM,
        context={"incident_id": incident_id},
        retryable=False,
        troubleshooting_steps=[
            TroubleshootingStep(1, "Verify the incident ID is correct"),
            TroubleshootingStep(2, "Check if the incident was deleted or expired"),
            TroubleshootingStep(3, "Try loading a different incident", "navigate_incidents"),
        ],
    ))


def pipeline_failed(stage_name: str, incident_id: str, cause: Optional[Exception] = None) -> CauverisError:
    return CauverisError(CauverisErrorConfig(
        code=ErrorCodes.PIPELINE_FAILED,
        message=f"Pipeline failed at stage: {stage_name}",
        severity=ErrorSeverity.HIGH,
        context={"stage_name": stage_name, "incident_id": incident_id},
        retryable=True,
        retry_after_ms=30000,
        cause=cause,
        troubleshooting_steps=[
            TroubleshootingStep(1, f'Pipeline stage "{stage_name}" encountered an error'),
            TroubleshootingStep(2, "Check the pipeline progress panel for details", "check_progress"),
            TroubleshootingStep(3, "Try resetting the investigation and re-running", "reset_pipeline"),
            TroubleshootingStep(4, "If persistent, check backend logs", "check_backend"),
        ],
    ))


def evidence_upload_failed(filename: str, reason: str, cause: Optional[Exception] = None) -> CauverisError:
    return CauverisError(CauverisErrorConfig(
        code=ErrorCodes.EVIDENCE_UPLOAD_FAILED,
        message=f"Failed to upload {filename}: {reason}",
        severity=ErrorSeverity.MEDIUM,
        context={"filename": filename, "reason": reason},
        retryable=True,
        retry_after_ms=5000,
        cause=cause,
        troubleshooting_steps=[
            TroubleshootingStep(1, f'Upload failed for "{filename}"'),
            TroubleshootingStep(2, f"Reason: {reason}"),
            TroubleshootingStep(3, "Check file size and type are supported", "check_file"),
            TroubleshootingStep(4, "Try uploading again", "retry"),
        ],
    ))


def secrets_detected(incident_id: str, files: List[str]) -> CauverisError:
    return CauverisError(CauverisErrorConfig(
        code=ErrorCodes.EVIDENCE_SECRETS_DETECTED,
        message="Secrets detected in uploaded evidence - upload blocked",
        severity=ErrorSeverity.CRITICAL,
        context={"incident_id": incident_id, "files": files},
        retryable=False,
        troubleshooting_steps=[
            TroubleshootingStep(1, "Secrets (API keys, passwords, tokens) were detected in your evidence files"),
            TroubleshootingStep(2, f"Affected files: {', '.join(files)}"),
            TroubleshootingStep(3, "Remove secrets from files before re-uploading", "sanitize_files"),
            TroubleshootingStep(4, "Use environment variables or secret managers instead", "best_practice"),
        ],
    ))


def patch_apply_failed(patch_id: str, reason: str, cause: Optional[Exception] = None) -> CauverisError:
    return CauverisError(CauverisErrorConfig(
        code=ErrorCodes.PATCH_APPLY_FAILED,
        message=f"Failed to apply patch {patch_id}: {reason}",
        severity=ErrorSeverity.HIGH,
        context={"patch_id": patch_id, "reason": reason},
        retryable=False,
        cause=cause,
        troubleshooting_steps=[
            TroubleshootingStep(1, f'Patch "{patch_id}" could not be applied'),
            TroubleshootingStep(2, f"Reason: {reason}"),
            TroubleshootingStep(3, "Check if target files have been modified", "check_files"),
            TroubleshootingStep(4, "Try downloading the patch package and applying manually", "manual_apply"),
        ],
    ))


def patch_verification_failed(patch_id: str, failed_checks: List[str]) -> CauverisError:
    return CauverisError(CauverisErrorConfig(
        code=ErrorCodes.PATCH_VERIFICATION_FAILED,
        message=f"Patch {patch_id} failed verification checks",
        severity=ErrorSeverity.HIGH,
        context={"patch_id": patch_id, "failed_checks": failed_checks},
        retryable=False,
        troubleshooting_steps=[
            TroubleshootingStep(1, f'Patch "{patch_id}" did not pass all verification gates'),
            TroubleshootingStep(2, f"Failed checks: {', '.join(failed_checks)}"),
            TroubleshootingStep(3, "Review patch details in Patch Forge for more information", "view_patch"),
            TroubleshootingStep(4, "Consider generating a new patch candidate", "generate_patch"),
        ],
    ))


def model_unavailable(provider: str, cause: Optional[Exception] = None) -> CauverisError:
    return CauverisError(CauverisErrorConfig(
        code=ErrorCodes.MODEL_UNAVAILABLE,
        message=f"Model provider {provider} is unavailable",
        severity=ErrorSeverity.HIGH,
        context={"provider": provider},
        retryable=True,
        retry_after_ms=30000,
        cause=cause,
        troubleshooting_steps=[
            TroubleshootingStep(1, f'Model provider "{provider}" is not responding'),
            TroubleshootingStep(2, "Check API credentials and network connectivity", "check_credentials"),
            TroubleshootingStep(3, "Try switching to local fixture mode", "switch_mode"),
            TroubleshootingStep(4, "Check provider status page for outages", "check_status"),
        ],
    ))


def config_missing(key: str) -> CauverisError:
    return CauverisError(CauverisErrorConfig(
        code=ErrorCodes.CONFIG_MISSING,
        message=f"Required configuration missing: {key}",
        severity=ErrorSeverity.HIGH,
        context={"key": key},
        retryable=False,
        troubleshooting_steps=[
            TroubleshootingStep(1, f"Missing required configuration: {key}"),
            TroubleshootingStep(2, "Check environment variables and .env files", "check_env"),
            TroubleshootingStep(3, "Refer to documentation for required settings", "read_docs"),
            TroubleshootingStep(4, "Restart application after fixing configuration", "restart"),
        ],
    ))


def unknown_error(message: str, cause: Optional[Exception] = None, context: Optional[Dict[str, Any]] = None) -> CauverisError:
    return CauverisError(CauverisErrorConfig(
        code="UNKNOWN_ERROR",
        message=message,
        severity=ErrorSeverity.HIGH,
        context=context or {},
        retryable=False,
        cause=cause,
        troubleshooting_steps=[
            TroubleshootingStep(1, "An unexpected error occurred"),
            TroubleshootingStep(2, f"Details: {message}"),
            TroubleshootingStep(3, "Try refreshing the page", "refresh"),
            TroubleshootingStep(4, "If persistent, report this issue with the correlation ID", "report"),
        ],
    ))


# Error handler utility for FastAPI
async def handle_api_error(_request, exc: Exception) -> JSONResponse:
    """Global error handler for FastAPI that returns structured error responses."""

    correlation_id = get_correlation_id()

    if isinstance(exc, CauverisError):
        return JSONResponse(
            status_code=exc.status_code or 500,
            content={
                "error": exc.to_dict(),
            },
            headers={"X-Correlation-ID": correlation_id}
        )

    if isinstance(exc, HTTPException):
        # Convert HTTPException to CauverisError
        cauveris_error = api_error(exc.status_code, exc.detail, str(_request.url))
        return JSONResponse(
            status_code=cauveris_error.status_code or 500,
            content={
                "error": cauveris_error.to_dict(),
            },
            headers={"X-Correlation-ID": correlation_id}
        )

    # Unknown error
    cauveris_error = unknown_error(str(exc), cause=exc, context={"url": str(_request.url)})
    return JSONResponse(
        status_code=500,
        content={
            "error": cauveris_error.to_dict(),
        },
        headers={"X-Correlation-ID": correlation_id}
    )


# Retry utility with exponential backoff
async def retry_with_backoff(
    operation: Callable,
    max_retries: int = 3,
    base_delay_ms: int = 1000,
    max_delay_ms: int = 30000,
    is_retryable: Callable = lambda e: isinstance(e, CauverisError) and e.retryable
):
    """Execute operation with exponential backoff retry logic."""
    last_error: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            return await operation()
        except Exception as error:
            last_error = error

            if attempt == max_retries or not is_retryable(error):
                raise

            delay = min(base_delay_ms * (2 ** attempt), max_delay_ms)
            await asyncio.sleep(delay / 1000.0)

    raise last_error if last_error else Exception("Unknown error in retry_with_backoff")


