"""
Telemetry Abstraction Layer - Backend

Provides a unified interface for metrics, traces, and events
with pluggable backends (OpenTelemetry, Prometheus, DataDog, console).
"""

import time
import uuid
import contextvars
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from enum import Enum


class TelemetryEventType(str, Enum):
    PAGE_VIEW = "page_view"
    API_REQUEST = "api_request"
    API_ERROR = "api_error"
    USER_ACTION = "user_action"
    PERFORMANCE = "performance"
    ERROR = "error"
    BUSINESS = "business"
    PIPELINE_STAGE = "pipeline_stage"
    EXPERIMENT = "experiment"
    PATCH_VERIFICATION = "patch_verification"
    SECURITY = "security"


@dataclass
class TelemetryEvent:
    name: str
    type: TelemetryEventType
    timestamp: float = field(default_factory=time.time)
    properties: Dict[str, Any] = field(default_factory=dict)
    tags: Dict[str, str] = field(default_factory=dict)
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    correlation_id: Optional[str] = None
    incident_id: Optional[str] = None


@dataclass
class TelemetryMetric:
    name: str
    value: float
    unit: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class TelemetrySpan:
    name: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    parent_span_id: Optional[str] = None
    span_id: str = field(default_factory=lambda: str(uuid.uuid4())[:16])
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4())[:32])
    tags: Dict[str, str] = field(default_factory=dict)
    status: str = "ok"
    error: Optional[Exception] = None

    def finish(self) -> None:
        self.end_time = time.time()
        self.duration_ms = round((self.end_time - self.start_time) * 1000, 2) if self.start_time else 0.0


class TelemetryBackend(ABC):
    """Abstract base class for telemetry backends."""

    @abstractmethod
    async def initialize(self, config: "TelemetryConfig") -> None:
        pass

    @abstractmethod
    def track_event(self, event: TelemetryEvent) -> None:
        pass

    @abstractmethod
    def track_metric(self, metric: TelemetryMetric) -> None:
        pass

    @abstractmethod
    def start_span(self, name: str, parent_span_id: Optional[str] = None) -> TelemetrySpan:
        pass

    @abstractmethod
    def end_span(self, span: TelemetrySpan) -> None:
        pass

    @abstractmethod
    def track_error(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> None:
        pass

    @abstractmethod
    async def flush(self) -> None:
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        pass


@dataclass
class TelemetryConfig:
    enabled: bool = True
    debug: bool = False
    sample_rate: float = 1.0
    service_name: str = "cauveris-api"
    environment: str = "development"


class NoOpBackend(TelemetryBackend):
    """No-op backend for when telemetry is disabled."""

    async def initialize(self, config: TelemetryConfig) -> None:
        pass

    def track_event(self, event: TelemetryEvent) -> None:
        pass

    def track_metric(self, metric: TelemetryMetric) -> None:
        pass

    def start_span(self, name: str, parent_span_id: Optional[str] = None) -> TelemetrySpan:
        return TelemetrySpan(name=name, parent_span_id=parent_span_id)

    def end_span(self, span: TelemetrySpan) -> None:
        pass

    def track_error(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


class ConsoleBackend(TelemetryBackend):
    """Console backend for development and debugging."""

    def __init__(self):
        self.config: Optional[TelemetryConfig] = None

    async def initialize(self, config: TelemetryConfig) -> None:
        self.config = config
        print(f"[Telemetry] Console backend initialized: {config}")

    def track_event(self, event: TelemetryEvent) -> None:
        if self.config and self.config.debug:
            print(f"[Telemetry Event] {event.name}: {event.properties}")

    def track_metric(self, metric: TelemetryMetric) -> None:
        if self.config and self.config.debug:
            print(f"[Telemetry Metric] {metric.name}: {metric.value} {metric.unit or ''}")

    def start_span(self, name: str, parent_span_id: Optional[str] = None) -> TelemetrySpan:
        span = TelemetrySpan(name=name, parent_span_id=parent_span_id)
        if self.config and self.config.debug:
            print(f"[Telemetry Span Start] {span.name} (trace={span.trace_id}, span={span.span_id})")
        return span

    def end_span(self, span: TelemetrySpan) -> None:
        span.finish()
        if self.config and self.config.debug:
            print(f"[Telemetry Span End] {span.name} duration={span.duration_ms}ms status={span.status}")

    def track_error(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> None:
        print(f"[Telemetry Error] {type(error).__name__}: {error}")
        if context:
            print(f"  Context: {context}")

    async def flush(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


class PrometheusBackend(TelemetryBackend):
    """Prometheus metrics backend for production use."""

    def __init__(self):
        self.config: Optional[TelemetryConfig] = None
        self._metrics: Dict[str, float] = {}
        try:
            from prometheus_client import Counter, Histogram, Gauge, start_http_server
            self._counter_cls = Counter
            self._histogram_cls = Histogram
            self._gauge_cls = Gauge
            self._start_http_server = start_http_server
            self._prometheus_available = True
        except ImportError:
            self._prometheus_available = False

    async def initialize(self, config: TelemetryConfig) -> None:
        self.config = config
        if self._prometheus_available and config.enabled:
            # Start Prometheus metrics HTTP server on port 9090
            try:
                self._start_http_server(9090)
                print("[Telemetry] Prometheus metrics server started on port 9090")
            except Exception as e:
                print(f"[Telemetry] Failed to start Prometheus server: {e}")

    def track_event(self, event: TelemetryEvent) -> None:
        # Events are typically not exported to Prometheus directly
        pass

    def track_metric(self, metric: TelemetryMetric) -> None:
        if not self._prometheus_available or not self.config or not self.config.enabled:
            return

        # Simple gauge metric tracking
        key = metric.name.replace(".", "_").replace("-", "_")
        if key not in self._metrics:
            try:
                gauge = self._gauge_cls(key, f"Telemetry metric: {metric.name}")
                self._metrics[key] = gauge
            except Exception:
                return
        else:
            gauge = self._metrics[key]

        try:
            gauge.set(metric.value)
        except Exception:
            pass

    def start_span(self, name: str, parent_span_id: Optional[str] = None) -> TelemetrySpan:
        return TelemetrySpan(name=name, parent_span_id=parent_span_id)

    def end_span(self, span: TelemetrySpan) -> None:
        span.finish()
        # Could export span duration as histogram
        if not self._prometheus_available:
            return

        key = f"{span.name}_duration_seconds".replace(".", "_").replace("-", "_")
        try:
            if key not in self._metrics:
                histogram = self._histogram_cls(key, f"Span duration for {span.name}")
                self._metrics[key] = histogram
            else:
                histogram = self._metrics[key]
            duration_seconds = (span.duration_ms or 0.0) / 1000.0
            histogram.observe(duration_seconds)
        except Exception:
            pass

    def track_error(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> None:
        if not self._prometheus_available:
            return

        key = "errors_total"
        try:
            if key not in self._metrics:
                counter = self._counter_cls(key, "Total errors", ["error_type"])
                self._metrics[key] = counter
            else:
                counter = self._metrics[key]
            counter.labels(error_type=type(error).__name__).inc()
        except Exception:
            pass

    async def flush(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


# Context variables for request-scoped correlation IDs
correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")
incident_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("incident_id", default="")
session_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("session_id", default="")


class TelemetryClient:
    """Main telemetry client with backend abstraction."""

    def __init__(self):
        self.backend: TelemetryBackend = NoOpBackend()
        self.config: TelemetryConfig = TelemetryConfig()
        self.initialized: bool = False
        self._session_id = str(uuid.uuid4())[:16]

    async def initialize(self, config: Optional[TelemetryConfig] = None, backend: Optional[TelemetryBackend] = None) -> None:
        config = config or TelemetryConfig()
        self.config = config

        # Determine backend
        if backend:
            self.backend = backend
        elif config.debug:
            self.backend = ConsoleBackend()
        else:
            # Try to use Prometheus if available
            try:
                self.backend = PrometheusBackend()
            except Exception:
                self.backend = NoOpBackend()

        await self.backend.initialize(self.config)
        self.initialized = True

    def track_event(
        self,
        name: str,
        event_type: TelemetryEventType,
        properties: Optional[Dict[str, Any]] = None,
        tags: Optional[Dict[str, str]] = None,
        user_id: Optional[str] = None,
    ) -> None:
        if not self.initialized or not self.config.enabled:
            return

        import random
        if random.random() > self.config.sample_rate:
            return

        event = TelemetryEvent(
            name=name,
            type=event_type,
            properties=properties or {},
            tags=tags or {},
            user_id=user_id,
            session_id=self._session_id,
            correlation_id=correlation_id_var.get() or None,
            incident_id=incident_id_var.get() or None,
        )
        self.backend.track_event(event)

    def track_metric(self, name: str, value: float, unit: Optional[str] = None, tags: Optional[Dict[str, str]] = None) -> None:
        if not self.initialized or not self.config.enabled:
            return

        metric = TelemetryMetric(
            name=name,
            value=value,
            unit=unit,
            tags={**(tags or {}), "session_id": self._session_id},
        )
        self.backend.track_metric(metric)

    def start_span(self, name: str, parent_span_id: Optional[str] = None) -> TelemetrySpan:
        span = self.backend.start_span(name, parent_span_id)
        # Add correlation IDs to span tags
        span.tags["correlation_id"] = correlation_id_var.get() or ""
        span.tags["incident_id"] = incident_id_var.get() or ""
        return span

    def end_span(self, span: TelemetrySpan) -> None:
        self.backend.end_span(span)

    def track_error(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> None:
        if not self.initialized:
            return

        context = context or {}
        context.update({
            "session_id": self._session_id,
            "correlation_id": correlation_id_var.get() or "",
            "incident_id": incident_id_var.get() or "",
        })
        self.backend.track_error(error, context)

    async def flush(self) -> None:
        await self.backend.flush()

    async def shutdown(self) -> None:
        await self.backend.shutdown()
        self.initialized = False


# Global telemetry instance
telemetry = TelemetryClient()


# Convenience functions
async def initialize_telemetry(
    config: Optional[TelemetryConfig] = None,
    backend: Optional[TelemetryBackend] = None
) -> None:
    """Initialize global telemetry client."""
    await telemetry.initialize(config, backend)


def set_correlation_id(correlation_id: str) -> None:
    """Set correlation ID for current context."""
    correlation_id_var.set(correlation_id)


def get_correlation_id() -> str:
    """Get current correlation ID."""
    return correlation_id_var.get() or ""


def set_incident_id(incident_id: str) -> None:
    """Set incident ID for current context."""
    incident_id_var.set(incident_id)


def get_incident_id() -> str:
    """Get current incident ID."""
    return incident_id_var.get() or ""


def track_api_request(
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    success: bool,
    incident_id: Optional[str] = None
) -> None:
    """Track API request metrics."""
    if incident_id:
        set_incident_id(incident_id)

    telemetry.track_event(
        name="api_request",
        event_type=TelemetryEventType.API_REQUEST,
        properties={
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "success": success,
        },
        tags={
            "method": method,
            "path": path,
            "status": str(status_code),
        },
    )

    telemetry.track_metric(
        name="http_request_duration_ms",
        value=duration_ms,
        unit="ms",
        tags={"method": method, "path": path, "status": str(status_code)},
    )

    if not success:
        telemetry.track_metric(
            name="http_request_errors_total",
            value=1,
            tags={"method": method, "path": path, "status": str(status_code)},
        )


def track_pipeline_stage(
    stage_name: str,
    status: str,
    duration_ms: float,
    incident_id: Optional[str] = None
) -> None:
    """Track pipeline stage execution."""
    if incident_id:
        set_incident_id(incident_id)

    telemetry.track_event(
        name=f"pipeline_stage_{status.lower()}",
        event_type=TelemetryEventType.PIPELINE_STAGE,
        properties={
            "stage_name": stage_name,
            "status": status,
            "duration_ms": duration_ms,
        },
        tags={"stage": stage_name, "status": status},
    )

    telemetry.track_metric(
        name="pipeline_stage_duration_ms",
        value=duration_ms,
        unit="ms",
        tags={"stage": stage_name, "status": status},
    )


def track_experiment(
    experiment_id: str,
    hypothesis_id: str,
    status: str,
    reproduction_rate: float,
    incident_id: Optional[str] = None
) -> None:
    """Track experiment execution."""
    if incident_id:
        set_incident_id(incident_id)

    telemetry.track_event(
        name=f"experiment_{status.lower()}",
        event_type=TelemetryEventType.EXPERIMENT,
        properties={
            "experiment_id": experiment_id,
            "hypothesis_id": hypothesis_id,
            "status": status,
            "reproduction_rate": reproduction_rate,
        },
        tags={"experiment_id": experiment_id, "hypothesis_id": hypothesis_id, "status": status},
    )


def track_patch_verification(
    patch_id: str,
    score: float,
    verified: bool,
    incident_id: Optional[str] = None
) -> None:
    """Track patch verification result."""
    if incident_id:
        set_incident_id(incident_id)

    telemetry.track_event(
        name="patch_verification",
        event_type=TelemetryEventType.PATCH_VERIFICATION,
        properties={
            "patch_id": patch_id,
            "score": score,
            "verified": verified,
        },
        tags={"patch_id": patch_id, "verified": str(verified)},
    )

    telemetry.track_metric(
        name="patch_score",
        value=score,
        tags={"patch_id": patch_id},
    )


def track_security_event(
    event_type: str,
    severity: str,
    description: str,
    incident_id: Optional[str] = None
) -> None:
    """Track security events."""
    if incident_id:
        set_incident_id(incident_id)

    telemetry.track_event(
        name=f"security_{event_type}",
        event_type=TelemetryEventType.SECURITY,
        properties={
            "event_type": event_type,
            "severity": severity,
            "description": description,
        },
        tags={"event_type": event_type, "severity": severity},
    )
