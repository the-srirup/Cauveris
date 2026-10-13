/**
 * User-Friendly Error Classes for Cauveris Frontend
 *
 * Provides structured error information with:
 * - Error code for programmatic handling
 * - Human-readable message
 * - Context for debugging
 * - Retryable flag for automatic retry logic
 * - Troubleshooting steps for user guidance
 */

export type ErrorSeverity = "low" | "medium" | "high" | "critical";

export interface ErrorCodeContext {
  [key: string]: string | number | boolean | undefined;
}

export interface TroubleshootingStep {
  step: number;
  description: string;
  action?: string; // Optional action user can take (e.g., "refresh", "retry", "contact_support")
}

export interface CauverisErrorOptions {
  code: string;
  message: string;
  severity?: ErrorSeverity;
  context?: ErrorCodeContext;
  retryable?: boolean;
  retryAfterMs?: number;
  troubleshootingSteps?: TroubleshootingStep[];
  cause?: Error;
  statusCode?: number;
}

export class CauverisError extends Error {
  public readonly code: string;
  public readonly severity: ErrorSeverity;
  public readonly context: ErrorCodeContext;
  public readonly retryable: boolean;
  public readonly retryAfterMs: number;
  public readonly troubleshootingSteps: TroubleshootingStep[];
  public readonly cause?: Error;
  public readonly statusCode?: number;
  public readonly timestamp: string;
  public readonly correlationId?: string;

  constructor(options: CauverisErrorOptions) {
    super(options.message);
    this.name = "CauverisError";
    this.code = options.code;
    this.severity = options.severity || "medium";
    this.context = options.context || {};
    this.retryable = options.retryable || false;
    this.retryAfterMs = options.retryAfterMs || 0;
    this.troubleshootingSteps = options.troubleshootingSteps || [];
    this.cause = options.cause;
    this.statusCode = options.statusCode;
    this.timestamp = new Date().toISOString();
    this.correlationId = getCorrelationId();

    // Maintains proper stack trace in V8 environments
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, CauverisError);
    }
  }

  toJSON(): Record<string, unknown> {
    return {
      name: this.name,
      code: this.code,
      message: this.message,
      severity: this.severity,
      context: this.context,
      retryable: this.retryable,
      retryAfterMs: this.retryAfterMs,
      troubleshootingSteps: this.troubleshootingSteps,
      cause: this.cause?.message,
      statusCode: this.statusCode,
      timestamp: this.timestamp,
      correlationId: this.correlationId,
      stack: this.stack,
    };
  }

  toUserString(): string {
    const parts = [`[${this.code}] ${this.message}`];

    if (Object.keys(this.context).length > 0) {
      parts.push(`Context: ${JSON.stringify(this.context)}`);
    }

    if (this.troubleshootingSteps.length > 0) {
      parts.push("\nTroubleshooting:");
      this.troubleshootingSteps.forEach((step) => {
        parts.push(`  ${step.step}. ${step.description}`);
        if (step.action) {
          parts.push(`     Action: ${step.action}`);
        }
      });
    }

    if (this.correlationId) {
      parts.push(`\nCorrelation ID: ${this.correlationId}`);
    }

    return parts.join("\n");
  }
}

// Correlation ID management (shared with telemetry)
let currentCorrelationId = "";

export function setCorrelationId(id: string): void {
  currentCorrelationId = id;
}

export function getCorrelationId(): string {
  if (!currentCorrelationId) {
    currentCorrelationId = `corr-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
  }
  return currentCorrelationId;
}

export function clearCorrelationId(): void {
  currentCorrelationId = "";
}

// Predefined error codes and factory functions

export const ErrorCodes = {
  // Network/Connection errors
  NETWORK_ERROR: "NETWORK_ERROR",
  TIMEOUT: "TIMEOUT",
  CONNECTION_REFUSED: "CONNECTION_REFUSED",
  DNS_ERROR: "DNS_ERROR",

  // API errors
  API_ERROR: "API_ERROR",
  API_UNAUTHORIZED: "API_UNAUTHORIZED",
  API_FORBIDDEN: "API_FORBIDDEN",
  API_NOT_FOUND: "API_NOT_FOUND",
  API_RATE_LIMITED: "API_RATE_LIMITED",
  API_SERVER_ERROR: "API_SERVER_ERROR",
  API_VALIDATION_ERROR: "API_VALIDATION_ERROR",

  // Incident errors
  INCIDENT_NOT_FOUND: "INCIDENT_NOT_FOUND",
  INCIDENT_ALREADY_EXISTS: "INCIDENT_ALREADY_EXISTS",
  INCIDENT_PROCESSING: "INCIDENT_PROCESSING",
  INCIDENT_FAILED: "INCIDENT_FAILED",

  // Pipeline errors
  PIPELINE_FAILED: "PIPELINE_FAILED",
  PIPELINE_STAGE_FAILED: "PIPELINE_STAGE_FAILED",
  PIPELINE_CANCELLED: "PIPELINE_CANCELLED",
  PIPELINE_TIMEOUT: "PIPELINE_TIMEOUT",

  // Evidence errors
  EVIDENCE_UPLOAD_FAILED: "EVIDENCE_UPLOAD_FAILED",
  EVIDENCE_VALIDATION_FAILED: "EVIDENCE_VALIDATION_FAILED",
  EVIDENCE_SECRETS_DETECTED: "EVIDENCE_SECRETS_DETECTED",
  EVIDENCE_CHECKSUM_MISMATCH: "EVIDENCE_CHECKSUM_MISMATCH",
  EVIDENCE_TOO_LARGE: "EVIDENCE_TOO_LARGE",
  EVIDENCE_UNSUPPORTED_TYPE: "EVIDENCE_UNSUPPORTED_TYPE",

  // Patch errors
  PATCH_GENERATION_FAILED: "PATCH_GENERATION_FAILED",
  PATCH_VERIFICATION_FAILED: "PATCH_VERIFICATION_FAILED",
  PATCH_APPLY_FAILED: "PATCH_APPLY_FAILED",
  PATCH_ROLLBACK_FAILED: "PATCH_ROLLBACK_FAILED",
  PATCH_CONFLICT: "PATCH_CONFLICT",

  // Experiment errors
  EXPERIMENT_FAILED: "EXPERIMENT_FAILED",
  SIMULATION_FAILED: "SIMULATION_FAILED",
  SANDBOX_UNAVAILABLE: "SANDBOX_UNAVAILABLE",

  // Model/Provider errors
  MODEL_UNAVAILABLE: "MODEL_UNAVAILABLE",
  MODEL_API_ERROR: "MODEL_API_ERROR",
  MODEL_RATE_LIMITED: "MODEL_RATE_LIMITED",
  MODEL_INVALID_RESPONSE: "MODEL_INVALID_RESPONSE",

  // Client errors
  CLIENT_STORAGE_ERROR: "CLIENT_STORAGE_ERROR",
  CLIENT_PARSE_ERROR: "CLIENT_PARSE_ERROR",
  CLIENT_RENDER_ERROR: "CLIENT_RENDER_ERROR",
  CLIENT_PERMISSION_DENIED: "CLIENT_PERMISSION_DENIED",

  // Configuration errors
  CONFIG_MISSING: "CONFIG_MISSING",
  CONFIG_INVALID: "CONFIG_INVALID",
  CONFIG_MIGRATION_NEEDED: "CONFIG_MIGRATION_NEEDED",
} as const;

// Factory functions for common errors

export function networkError(message: string = "Network request failed", cause?: Error): CauverisError {
  return new CauverisError({
    code: ErrorCodes.NETWORK_ERROR,
    message,
    severity: "high",
    retryable: true,
    retryAfterMs: 5000,
    cause,
    troubleshootingSteps: [
      { step: 1, description: "Check your internet connection", action: "retry" },
      { step: 2, description: "Verify the backend server is running on port 8000", action: "check_backend" },
      { step: 3, description: "Try refreshing the page", action: "refresh" },
      { step: 4, description: "Check browser console for detailed error", action: "check_console" },
    ],
  });
}

export function timeoutError(endpoint: string, timeoutMs: number = 15000): CauverisError {
  return new CauverisError({
    code: ErrorCodes.TIMEOUT,
    message: `Request to ${endpoint} timed out after ${timeoutMs}ms`,
    severity: "high",
    context: { endpoint, timeoutMs },
    retryable: true,
    retryAfterMs: 10000,
    troubleshootingSteps: [
      { step: 1, description: "The backend may be under heavy load", action: "retry" },
      { step: 2, description: "Try again in a few seconds", action: "retry" },
      { step: 3, description: "If persistent, check backend performance", action: "check_backend" },
    ],
  });
}

export function apiError(statusCode: number, message: string, endpoint: string, cause?: Error): CauverisError {
  const codeMap: Record<number, string> = {
    400: ErrorCodes.API_VALIDATION_ERROR,
    401: ErrorCodes.API_UNAUTHORIZED,
    403: ErrorCodes.API_FORBIDDEN,
    404: ErrorCodes.API_NOT_FOUND,
    429: ErrorCodes.API_RATE_LIMITED,
    500: ErrorCodes.API_SERVER_ERROR,
    502: ErrorCodes.API_SERVER_ERROR,
    503: ErrorCodes.API_SERVER_ERROR,
    504: ErrorCodes.TIMEOUT,
  };

  const code = codeMap[statusCode] || ErrorCodes.API_ERROR;
  const retryable = [429, 500, 502, 503, 504].includes(statusCode);

  const troubleshooting: TroubleshootingStep[] = [
    { step: 1, description: `API returned ${statusCode}: ${message}` },
  ];

  if (statusCode === 401) {
    troubleshooting.push({ step: 2, description: "Authentication required - please log in again", action: "login" });
  } else if (statusCode === 403) {
    troubleshooting.push({ step: 2, description: "Insufficient permissions for this operation", action: "contact_support" });
  } else if (statusCode === 404) {
    troubleshooting.push({ step: 2, description: "The requested resource was not found", action: "refresh" });
  } else if (statusCode === 429) {
    troubleshooting.push({ step: 2, description: "Rate limited - wait before retrying", action: "wait_retry" });
    troubleshooting.push({ step: 3, description: "Reduce request frequency", action: "reduce_frequency" });
  } else if (statusCode >= 500) {
    troubleshooting.push({ step: 2, description: "Backend server error - try again later", action: "retry" });
    troubleshooting.push({ step: 3, description: "Check backend logs for details", action: "check_backend" });
  }

  return new CauverisError({
    code,
    message,
    severity: statusCode >= 500 ? "high" : "medium",
    context: { endpoint, statusCode },
    retryable,
    retryAfterMs: statusCode === 429 ? 30000 : 5000,
    cause,
    statusCode,
    troubleshootingSteps: troubleshooting,
  });
}

export function incidentNotFound(incidentId: string): CauverisError {
  return new CauverisError({
    code: ErrorCodes.INCIDENT_NOT_FOUND,
    message: `Incident ${incidentId} not found`,
    severity: "medium",
    context: { incidentId },
    retryable: false,
    troubleshootingSteps: [
      { step: 1, description: "Verify the incident ID is correct" },
      { step: 2, description: "Check if the incident was deleted or expired" },
      { step: 3, description: "Try loading a different incident", action: "navigate_incidents" },
    ],
  });
}

export function pipelineFailed(stageName: string, incidentId: string, cause?: Error): CauverisError {
  return new CauverisError({
    code: ErrorCodes.PIPELINE_FAILED,
    message: `Pipeline failed at stage: ${stageName}`,
    severity: "high",
    context: { stageName, incidentId },
    retryable: true,
    retryAfterMs: 30000,
    cause,
    troubleshootingSteps: [
      { step: 1, description: `Pipeline stage "${stageName}" encountered an error` },
      { step: 2, description: "Check the pipeline progress panel for details", action: "check_progress" },
      { step: 3, description: "Try resetting the investigation and re-running", action: "reset_pipeline" },
      { step: 4, description: "If persistent, check backend logs", action: "check_backend" },
    ],
  });
}

export function evidenceUploadFailed(filename: string, reason: string, cause?: Error): CauverisError {
  return new CauverisError({
    code: ErrorCodes.EVIDENCE_UPLOAD_FAILED,
    message: `Failed to upload ${filename}: ${reason}`,
    severity: "medium",
    context: { filename, reason },
    retryable: true,
    retryAfterMs: 5000,
    cause,
    troubleshootingSteps: [
      { step: 1, description: `Upload failed for "${filename}"` },
      { step: 2, description: `Reason: ${reason}` },
      { step: 3, description: "Check file size and type are supported", action: "check_file" },
      { step: 4, description: "Try uploading again", action: "retry" },
    ],
  });
}

export function secretsDetected(incidentId: string, files: string[]): CauverisError {
  return new CauverisError({
    code: ErrorCodes.EVIDENCE_SECRETS_DETECTED,
    message: `Secrets detected in uploaded evidence - upload blocked`,
    severity: "critical",
    context: { incidentId, files: files.join(", ") },
    retryable: false,
    troubleshootingSteps: [
      { step: 1, description: "Secrets (API keys, passwords, tokens) were detected in your evidence files" },
      { step: 2, description: "Affected files: " + files.join(", ") },
      { step: 3, description: "Remove secrets from files before re-uploading", action: "sanitize_files" },
      { step: 4, description: "Use environment variables or secret managers instead", action: "best_practice" },
    ],
  });
}

export function patchApplyFailed(patchId: string, reason: string, cause?: Error): CauverisError {
  return new CauverisError({
    code: ErrorCodes.PATCH_APPLY_FAILED,
    message: `Failed to apply patch ${patchId}: ${reason}`,
    severity: "high",
    context: { patchId, reason },
    retryable: false,
    troubleshootingSteps: [
      { step: 1, description: `Patch "${patchId}" could not be applied` },
      { step: 2, description: `Reason: ${reason}` },
      { step: 3, description: "Check if target files have been modified", action: "check_files" },
      { step: 4, description: "Try downloading the patch package and applying manually", action: "manual_apply" },
    ],
  });
}

export function patchVerificationFailed(patchId: string, failedChecks: string[]): CauverisError {
  return new CauverisError({
    code: ErrorCodes.PATCH_VERIFICATION_FAILED,
    message: `Patch ${patchId} failed verification checks`,
    severity: "high",
    context: { patchId, failedChecks: failedChecks.join(", ") },
    retryable: false,
    troubleshootingSteps: [
      { step: 1, description: `Patch "${patchId}" did not pass all verification gates` },
      { step: 2, description: "Failed checks: " + failedChecks.join(", ") },
      { step: 3, description: "Review patch details in Patch Forge for more information", action: "view_patch" },
      { step: 4, description: "Consider generating a new patch candidate", action: "generate_patch" },
    ],
  });
}

export function modelUnavailable(provider: string, cause?: Error): CauverisError {
  return new CauverisError({
    code: ErrorCodes.MODEL_UNAVAILABLE,
    message: `Model provider ${provider} is unavailable`,
    severity: "high",
    context: { provider },
    retryable: true,
    retryAfterMs: 30000,
    cause,
    troubleshootingSteps: [
      { step: 1, description: `Model provider "${provider}" is not responding` },
      { step: 2, description: "Check API credentials and network connectivity", action: "check_credentials" },
      { step: 3, description: "Try switching to local fixture mode", action: "switch_mode" },
      { step: 4, description: "Check provider status page for outages", action: "check_status" },
    ],
  });
}

export function clientStorageError(operation: string, cause?: Error): CauverisError {
  return new CauverisError({
    code: ErrorCodes.CLIENT_STORAGE_ERROR,
    message: `Local storage operation failed: ${operation}`,
    severity: "medium",
    context: { operation },
    retryable: false,
    cause,
    troubleshootingSteps: [
      { step: 1, description: `Failed to ${operation} data in browser storage` },
      { step: 2, description: "Try clearing browser cache and localStorage", action: "clear_storage" },
      { step: 3, description: "Check if private browsing mode is enabled", action: "check_private_mode" },
      { step: 4, description: "Ensure sufficient disk space is available", action: "check_disk" },
    ],
  });
}

export function configMissing(key: string): CauverisError {
  return new CauverisError({
    code: ErrorCodes.CONFIG_MISSING,
    message: `Required configuration missing: ${key}`,
    severity: "high",
    context: { key },
    retryable: false,
    troubleshootingSteps: [
      { step: 1, description: `Missing required configuration: ${key}` },
      { step: 2, description: "Check environment variables and .env files", action: "check_env" },
      { step: 3, description: "Refer to documentation for required settings", action: "read_docs" },
      { step: 4, description: "Restart application after fixing configuration", action: "restart" },
    ],
  });
}

export function unknownError(message: string, cause?: Error, context?: ErrorCodeContext): CauverisError {
  return new CauverisError({
    code: "UNKNOWN_ERROR",
    message,
    severity: "high",
    context,
    retryable: false,
    cause,
    troubleshootingSteps: [
      { step: 1, description: "An unexpected error occurred" },
      { step: 2, description: `Details: ${message}` },
      { step: 3, description: "Try refreshing the page", action: "refresh" },
      { step: 4, description: "If persistent, report this issue with the correlation ID", action: "report" },
    ],
  });
}

// Error handler utility for API responses
export async function handleApiError(response: Response, endpoint: string): Promise<CauverisError> {
  let message = `HTTP ${response.status}`;
  let errorData: any = {};

  try {
    errorData = await response.json();
    if (typeof errorData.detail === 'string') {
      message = errorData.detail;
    } else if (Array.isArray(errorData.detail)) {
      message = errorData.detail
        .map((d: any) => (d && typeof d === 'object' ? d.msg || d.message || JSON.stringify(d) : String(d)))
        .join(', ');
    } else if (errorData.detail && typeof errorData.detail === 'object') {
      message = errorData.detail.msg || errorData.detail.message || JSON.stringify(errorData.detail);
    } else if (typeof errorData.error === 'string') {
      message = errorData.error;
    } else if (typeof errorData.message === 'string') {
      message = errorData.message;
    }
  } catch {
    // Ignore JSON parse errors
  }

  return apiError(response.status, message, endpoint);
}

// Retry utility with exponential backoff
export async function retryWithBackoff<T>(
  operation: () => Promise<T>,
  maxRetries: number = 3,
  baseDelayMs: number = 1000,
  maxDelayMs: number = 30000,
  isRetryable: (error: Error) => boolean = (e) => e instanceof CauverisError && e.retryable
): Promise<T> {
  let lastError: Error;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await operation();
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));

      if (attempt === maxRetries || !isRetryable(lastError)) {
        throw lastError;
      }

      const delay = Math.min(baseDelayMs * Math.pow(2, attempt), maxDelayMs);
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }

  throw lastError!;
}

// Error boundary integration helper
export function errorToBoundaryInfo(error: Error): {
  code: string;
  message: string;
  retryable: boolean;
  troubleshootingSteps: TroubleshootingStep[];
} {
  if (error instanceof CauverisError) {
    return {
      code: error.code,
      message: error.message,
      retryable: error.retryable,
      troubleshootingSteps: error.troubleshootingSteps,
    };
  }

  return {
    code: "UNKNOWN_ERROR",
    message: error.message,
    retryable: false,
    troubleshootingSteps: [
      { step: 1, description: "An unexpected error occurred" },
      { step: 2, description: `Details: ${error.message}` },
      { step: 3, description: "Try refreshing the page", action: "refresh" },
    ],
  };
}