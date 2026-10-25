/**
 * Telemetry Abstraction Layer - Frontend
 *
 * Provides a unified interface for metrics, traces, and events
 * with pluggable backends (OpenTelemetry, DataDog, console, no-op).
 */

export type TelemetryEventType =
  | "page_view"
  | "api_request"
  | "api_error"
  | "user_action"
  | "performance"
  | "error"
  | "business";

export interface TelemetryEvent {
  name: string;
  type: TelemetryEventType;
  timestamp: number;
  properties?: Record<string, unknown>;
  tags?: Record<string, string>;
  userId?: string;
  sessionId?: string;
  correlationId?: string;
}

export interface TelemetryMetric {
  name: string;
  value: number;
  unit?: string;
  timestamp: number;
  tags?: Record<string, string>;
}

export interface TelemetrySpan {
  name: string;
  startTime: number;
  endTime?: number;
  duration?: number;
  parentSpanId?: string;
  spanId: string;
  traceId: string;
  tags?: Record<string, string>;
  status?: "ok" | "error";
  error?: Error;
}

export interface TelemetryConfig {
  enabled: boolean;
  debug: boolean;
  sampleRate: number;
  serviceName: string;
  environment: string;
}

export interface TelemetryBackend {
  initialize(config: TelemetryConfig): Promise<void>;
  trackEvent(event: TelemetryEvent): void;
  trackMetric(metric: TelemetryMetric): void;
  startSpan(name: string, parentSpanId?: string): TelemetrySpan;
  endSpan(span: TelemetrySpan): void;
  trackError(error: Error, context?: Record<string, unknown>): void;
  flush(): Promise<void>;
  shutdown(): Promise<void>;
}

class NoOpBackend implements TelemetryBackend {
  async initialize(_config: TelemetryConfig): Promise<void> {}
  trackEvent(_event: TelemetryEvent): void {}
  trackMetric(_metric: TelemetryMetric): void {}
  startSpan(name: string, _parentSpanId?: string): TelemetrySpan {
    return {
      name,
      startTime: Date.now(),
      spanId: generateId(),
      traceId: generateId(),
    };
  }
  endSpan(_span: TelemetrySpan): void {}
  trackError(_error: Error, _context?: Record<string, unknown>): void {}
  async flush(): Promise<void> {}
  async shutdown(): Promise<void> {}
}

class ConsoleBackend implements TelemetryBackend {
  private config?: TelemetryConfig;

  async initialize(config: TelemetryConfig): Promise<void> {
    this.config = config;
    console.log("[Telemetry] Console backend initialized", config);
  }

  trackEvent(event: TelemetryEvent): void {
    if (this.config?.debug) {
      console.log("[Telemetry Event]", JSON.stringify(event, null, 2));
    }
  }

  trackMetric(metric: TelemetryMetric): void {
    if (this.config?.debug) {
      console.log("[Telemetry Metric]", JSON.stringify(metric, null, 2));
    }
  }

  startSpan(name: string, parentSpanId?: string): TelemetrySpan {
    const span = {
      name,
      startTime: Date.now(),
      parentSpanId,
      spanId: generateId(),
      traceId: generateId(),
    };
    if (this.config?.debug) {
      console.log("[Telemetry Span Start]", span);
    }
    return span;
  }

  endSpan(span: TelemetrySpan): void {
    span.endTime = Date.now();
    span.duration = span.endTime - span.startTime;
    if (this.config?.debug) {
      console.log("[Telemetry Span End]", span);
    }
  }

  trackError(error: Error, context?: Record<string, unknown>): void {
    console.error("[Telemetry Error]", error.message, context);
  }

  async flush(): Promise<void> {}
  async shutdown(): Promise<void> {}
}

function generateId(): string {
  return Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
}

// Telemetry client singleton
class TelemetryClient {
  private backend: TelemetryBackend = new NoOpBackend();
  private config: TelemetryConfig = {
    enabled: false,
    debug: false,
    sampleRate: 1.0,
    serviceName: "cauveris-web",
    environment: "development",
  };
  private initialized = false;
  private sessionId: string;
  private eventBuffer: TelemetryEvent[] = [];

  constructor() {
    this.sessionId = generateId();
  }

  async initialize(config: Partial<TelemetryConfig> = {}, backend?: TelemetryBackend): Promise<void> {
    this.config = { ...this.config, ...config };
    this.backend = backend || (this.config.debug ? new ConsoleBackend() : new NoOpBackend());
    await this.backend.initialize(this.config);
    this.initialized = true;

    // Track page view on initialization
    if (typeof window !== "undefined") {
      this.trackEvent({
        name: "page_view",
        type: "page_view",
        properties: {
          url: window.location.href,
          referrer: document.referrer,
          userAgent: navigator.userAgent,
        },
      });
    }
  }

  trackEvent(event: Omit<TelemetryEvent, "timestamp" | "sessionId">): void {
    if (!this.initialized || !this.config.enabled) return;

    if (Math.random() > this.config.sampleRate) return;

    const fullEvent: TelemetryEvent = {
      ...event,
      timestamp: Date.now(),
      sessionId: this.sessionId,
      correlationId: getCorrelationId(),
    };

    this.backend.trackEvent(fullEvent);
    this.eventBuffer.push(fullEvent);
    if (this.eventBuffer.length >= 25) {
      void this.flush();
    }
  }

  trackMetric(name: string, value: number, unit?: string, tags?: Record<string, string>): void {
    if (!this.initialized || !this.config.enabled) return;

    this.backend.trackMetric({
      name,
      value,
      unit,
      timestamp: Date.now(),
      tags: { ...tags, sessionId: this.sessionId },
    });
  }

  startSpan(name: string, parentSpanId?: string): TelemetrySpan {
    return this.backend.startSpan(name, parentSpanId);
  }

  endSpan(span: TelemetrySpan): void {
    this.backend.endSpan(span);
  }

  trackError(error: Error, context?: Record<string, unknown>): void {
    if (!this.initialized) return;

    this.backend.trackError(error, {
      ...context,
      sessionId: this.sessionId,
      correlationId: getCorrelationId(),
    });
  }

  async flush(): Promise<void> {
    await this.backend.flush();
    if (this.eventBuffer.length === 0) return;
    const toSend = [...this.eventBuffer];
    this.eventBuffer = [];
    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
      if (typeof window !== "undefined" && typeof fetch !== "undefined") {
        await fetch(`${baseUrl}/telemetry/events`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ events: toSend }),
        });
      }
    } catch (err) {
      if (this.config.debug) {
        console.warn("[Telemetry] Failed to flush events to server:", err);
      }
    }
  }

  async shutdown(): Promise<void> {
    await this.flush();
    await this.backend.shutdown();
    this.initialized = false;
  }

  getSessionId(): string {
    return this.sessionId;
  }
}

// Global telemetry instance
export const telemetry = new TelemetryClient();

// Correlation ID management
let currentCorrelationId = "";

export function setCorrelationId(id: string): void {
  currentCorrelationId = id;
}

export function getCorrelationId(): string {
  if (!currentCorrelationId) {
    currentCorrelationId = generateId();
  }
  return currentCorrelationId;
}

export function clearCorrelationId(): void {
  currentCorrelationId = "";
}

// Convenience functions
export function trackPageView(url: string, properties?: Record<string, unknown>): void {
  telemetry.trackEvent({
    name: "page_view",
    type: "page_view",
    properties: { url, ...properties },
  });
}

export function trackApiRequest(endpoint: string, method: string, durationMs: number, status: number, success: boolean): void {
  telemetry.trackEvent({
    name: "api_request",
    type: "api_request",
    properties: { endpoint, method, durationMs, status, success },
    tags: { endpoint, method, status: status.toString() },
  });
}

export function trackUserAction(action: string, properties?: Record<string, unknown>): void {
  telemetry.trackEvent({
    name: action,
    type: "user_action",
    properties,
  });
}

export function trackPerformance(name: string, value: number, unit: string = "ms"): void {
  telemetry.trackMetric(name, value, unit);
}

export function trackBusinessEvent(name: string, properties?: Record<string, unknown>): void {
  telemetry.trackEvent({
    name,
    type: "business",
    properties,
  });
}

// React hook for telemetry
export function useTelemetry() {
  return {
    trackEvent: telemetry.trackEvent.bind(telemetry),
    trackMetric: telemetry.trackMetric.bind(telemetry),
    startSpan: telemetry.startSpan.bind(telemetry),
    endSpan: telemetry.endSpan.bind(telemetry),
    trackError: telemetry.trackError.bind(telemetry),
    trackPageView,
    trackApiRequest,
    trackUserAction,
    trackPerformance,
    trackBusinessEvent,
  };
}

// Initialize telemetry on client side
export async function initializeTelemetry(overrides?: Partial<TelemetryConfig>): Promise<void> {
  const config: Partial<TelemetryConfig> = {
    enabled: process.env.NEXT_PUBLIC_TELEMETRY_ENABLED === "true",
    debug: process.env.NODE_ENV === "development",
    serviceName: "cauveris-web",
    environment: process.env.NEXT_PUBLIC_ENVIRONMENT || "development",
    ...overrides,
  };

  await telemetry.initialize(config);
}

// Cleanup on page unload
if (typeof window !== "undefined") {
  window.addEventListener("beforeunload", () => {
    telemetry.flush();
  });
}