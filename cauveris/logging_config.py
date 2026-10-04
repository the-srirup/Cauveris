"""
Structured JSON logging configuration for Cauveris.
Provides correlation ID propagation, request context binding, and JSON output.
"""

import logging
import sys
import contextvars
from datetime import datetime, timezone
from typing import Any, Dict
try:
    from pythonjsonlogger import json as jsonlogger
except ImportError:
    from pythonjsonlogger import jsonlogger  # type: ignore

# Context variables for request-scoped data
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
incident_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("incident_id", default="")

class StructuredLogFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter that adds context variables to every log record."""

    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: Dict[str, Any]) -> None:
        super().add_fields(log_record, record, message_dict)

        # Add standard fields
        log_record["timestamp"] = datetime.now(timezone.utc).isoformat()
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        log_record["module"] = record.module
        log_record["function"] = record.funcName
        log_record["line"] = record.lineno

        # Add correlation IDs from context variables
        request_id = request_id_var.get()
        incident_id = incident_id_var.get()

        if request_id:
            log_record["request_id"] = request_id
        if incident_id:
            log_record["incident_id"] = incident_id

        # Add exception info if present
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "message", "name", "pathname", "process", "processName",
                "relativeCreated", "thread", "threadName", "exc_info",
                "exc_text", "stack_info", "getMessage"
            }:
                log_record[key] = value


def setup_structured_logging(level: int = logging.INFO, json_output: bool = True) -> None:
    """
    Configure structured JSON logging for the application.

    Args:
        level: Logging level (default: INFO)
        json_output: Whether to output JSON (True) or human-readable (False)
    """
    formatter: logging.Formatter

    if json_output:
        formatter = StructuredLogFormatter(
            fmt="%(timestamp)s %(level)s %(logger)s %(message)s",
            rename_fields={"message": "message"}
        )
    else:
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    # File handler
    file_handler = logging.FileHandler("cauveris.log")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Suppress noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(name)


def bind_request_context(request_id: str, incident_id: str = "") -> None:
    """Bind request context to current context variables."""
    request_id_var.set(request_id)
    incident_id_var.set(incident_id)


def clear_request_context() -> None:
    """Clear request context variables."""
    request_id_var.set("")
    incident_id_var.set("")


class LogContext:
    """Context manager for temporarily binding log context."""

    def __init__(self, **kwargs: Any):
        self.kwargs = kwargs
        self.tokens = []

    def __enter__(self):
        for key, value in self.kwargs.items():
            if key == "request_id":
                self.tokens.append(request_id_var.set(value))
            elif key == "incident_id":
                self.tokens.append(incident_id_var.set(value))

    def __exit__(self, exc_type, exc_val, exc_tb):
        for token in self.tokens:
            # Reset context var to previous value
            if token.var is request_id_var:
                request_id_var.reset(token)
            elif token.var is incident_id_var:
                incident_id_var.reset(token)


# Structured logging helpers for common operations
def log_request(
    logger: logging.Logger,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    request_id: str = "",
    incident_id: str = "",
    **extra: Any
) -> None:
    """Log HTTP request with structured fields."""
    with LogContext(request_id=request_id, incident_id=incident_id):
        logger.info(
            "HTTP request completed",
            extra={
                "http_method": method,
                "http_path": path,
                "http_status": status_code,
                "duration_ms": duration_ms,
                **extra
            }
        )


def log_pipeline_stage(
    logger: logging.Logger,
    stage_name: str,
    stage_status: str,
    duration_ms: float,
    incident_id: str = "",
    request_id: str = "",
    **extra: Any
) -> None:
    """Log pipeline stage execution with structured fields."""
    with LogContext(request_id=request_id, incident_id=incident_id):
        logger.info(
            f"Pipeline stage {stage_status.lower()}",
            extra={
                "stage_name": stage_name,
                "stage_status": stage_status,
                "duration_ms": duration_ms,
                **extra
            }
        )


def log_experiment(
    logger: logging.Logger,
    experiment_id: str,
    hypothesis_id: str,
    status: str,
    reproduction_rate: float,
    incident_id: str = "",
    request_id: str = "",
    **extra: Any
) -> None:
    """Log experiment execution with structured fields."""
    with LogContext(request_id=request_id, incident_id=incident_id):
        logger.info(
            f"Experiment {status.lower()}",
            extra={
                "experiment_id": experiment_id,
                "hypothesis_id": hypothesis_id,
                "status": status,
                "reproduction_rate": reproduction_rate,
                **extra
            }
        )


def log_patch_verification(
    logger: logging.Logger,
    patch_id: str,
    score: float,
    verified: bool,
    incident_id: str = "",
    request_id: str = "",
    **extra: Any
) -> None:
    """Log patch verification with structured fields."""
    with LogContext(request_id=request_id, incident_id=incident_id):
        logger.info(
            f"Patch verification {'passed' if verified else 'failed'}",
            extra={
                "patch_id": patch_id,
                "score": score,
                "verified": verified,
                **extra
            }
        )


def log_security_event(
    logger: logging.Logger,
    event_type: str,
    severity: str,
    description: str,
    incident_id: str = "",
    request_id: str = "",
    **extra: Any
) -> None:
    """Log security-related events."""
    with LogContext(request_id=request_id, incident_id=incident_id):
        logger.warning(
            f"Security event: {event_type}",
            extra={
                "security_event_type": event_type,
                "severity": severity,
                "description": description,
                **extra
            }
        )


def log_error(
    logger: logging.Logger,
    error: Exception,
    context: str = "",
    incident_id: str = "",
    request_id: str = "",
    **extra: Any
) -> None:
    """Log error with structured context."""
    with LogContext(request_id=request_id, incident_id=incident_id):
        logger.exception(
            f"Error in {context}: {str(error)}" if context else str(error),
            extra={
                "error_type": type(error).__name__,
                "error_message": str(error),
                "context": context,
                **extra
            }
        )
