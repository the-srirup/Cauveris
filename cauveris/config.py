"""
Configuration management for Cauveris.
Loads settings from environment variables with sensible defaults.
"""

import os
import secrets
import warnings
from typing import Optional
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _generate_secure_secret() -> str:
    """Generate a cryptographically secure random secret."""
    return secrets.token_urlsafe(32)


def _validate_secret_key(key: str, env_name: str = "CAUVERIS_SECRET_KEY") -> str:
    """Validate secret key meets security requirements."""
    if not key or key == "dev-secret-change-in-prod":
        if not key:
            warnings.warn(
                f"{env_name} is not set. Using insecure random key. "
                "Set {env_name} environment variable in production!",
                UserWarning
            )
        return _generate_secure_secret()

    # Validate minimum length for security
    if len(key) < 32:
        raise ValueError(
            f"{env_name} must be at least 32 characters long for security. "
            f"Current length: {len(key)}"
        )

    return key


@dataclass
class Settings:
    """Application configuration."""

    # Server settings
    host: str = field(default_factory=lambda: os.getenv("CAUVERIS_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_PORT", "8000")))
    debug: bool = field(
        default_factory=lambda: os.getenv("CAUVERIS_DEBUG", "false").lower() == "true"
    )

    # Security
    secret_key: str = field(
        default_factory=lambda: _validate_secret_key(
            os.getenv("CAUVERIS_SECRET_KEY", "dev-secret-change-in-prod")
        )
    )
    max_upload_size: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_MAX_UPLOAD_SIZE", "104857600"))
    )  # 100MB
    max_archive_members: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_MAX_ARCHIVE_MEMBERS", "10000"))
    )
    max_archive_uncompressed_size: int = field(
        default_factory=lambda: int(
            os.getenv("CAUVERIS_MAX_ARCHIVE_UNCOMPRESSED_SIZE", "536870912")
        )
    )

    # Demo mode: seeds the demo user and allows implicit CAU-0001 golden-incident
    # hydration in read paths. Default is false to prevent implicit hydration.
    demo_mode: bool = field(
        default_factory=lambda: os.getenv("CAUVERIS_DEMO_MODE", "false").lower() == "true"
    )

    # Incident Creation Limits (Phase 2)
    max_incidents_per_minute: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_MAX_INCIDENTS_PER_MINUTE", "5"))
    )
    max_incidents_per_hour: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_MAX_INCIDENTS_PER_HOUR", "20"))
    )
    max_incidents_per_day: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_MAX_INCIDENTS_PER_DAY", "50"))
    )
    max_active_incidents_per_user: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_MAX_ACTIVE_INCIDENTS_PER_USER", "10"))
    )
    max_retained_incidents_per_user: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_MAX_RETAINED_INCIDENTS_PER_USER", "100"))
    )
    max_active_incidents_per_org: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_MAX_ACTIVE_INCIDENTS_PER_ORG", "50"))
    )
    max_retained_incidents_per_org: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_MAX_RETAINED_INCIDENTS_PER_ORG", "500"))
    )
    max_anonymous_incidents: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_MAX_ANONYMOUS_INCIDENTS", "2"))
    )
    max_global_active_incidents: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_MAX_GLOBAL_ACTIVE_INCIDENTS", "100"))
    )
    max_global_daily_creation: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_MAX_GLOBAL_DAILY_CREATION", "500"))
    )

    # Model Gateway (Nebius Token Factory / OpenAI Compatible)
    model_fast: str = field(
        default_factory=lambda: os.getenv("NEBIUS_MODEL_FAST", "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF")
    )
    model_reasoning: str = field(
        default_factory=lambda: os.getenv("NEBIUS_MODEL_REASONING", "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF")
    )
    model_escalation: str = field(
        default_factory=lambda: os.getenv("NEBIUS_MODEL_ESCALATION", "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF")
    )
    nebius_model_id: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_NEBIUS_MODEL_ID") or os.getenv("NEBIUS_MODEL_ID", "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF")
    )
    nebius_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("CAUVERIS_NEBIUS_API_KEY") or os.getenv("NEBIUS_API_KEY")
    )
    nebius_base_url: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_NEBIUS_BASE_URL") or os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1")
    )
    nebius_request_timeout_seconds: float = field(
        default_factory=lambda: float(
            os.getenv("CAUVERIS_NEBIUS_REQUEST_TIMEOUT_SECONDS")
            or os.getenv("NEBIUS_REQUEST_TIMEOUT_SECONDS", "60.0")
        )
    )
    nebius_max_retries: int = field(
        default_factory=lambda: int(
            os.getenv("CAUVERIS_NEBIUS_MAX_RETRIES")
            or os.getenv("NEBIUS_MAX_RETRIES", "3")
        )
    )
    nebius_max_concurrent_requests: int = field(
        default_factory=lambda: int(
            os.getenv("CAUVERIS_NEBIUS_MAX_CONCURRENT_REQUESTS")
            or os.getenv("NEBIUS_MAX_CONCURRENT_REQUESTS", "5")
        )
    )
    nebius_daily_budget_limit: float = field(
        default_factory=lambda: float(
            os.getenv("CAUVERIS_NEBIUS_DAILY_BUDGET_LIMIT")
            or os.getenv("NEBIUS_DAILY_BUDGET_LIMIT", "100.0")
        )
    )
    nebius_enabled: bool = field(
        default_factory=lambda: (
            os.getenv("CAUVERIS_NEBIUS_ENABLED")
            or os.getenv("NEBIUS_ENABLED", "true")
        ).lower() == "true"
    )
    model_provider_required: bool = field(
        default_factory=lambda: (
            os.getenv("CAUVERIS_MODEL_PROVIDER_REQUIRED")
            or os.getenv("MODEL_PROVIDER_REQUIRED", "false")
        ).lower() == "true"
    )
    runtime_fixtures: bool = field(
        default_factory=lambda: os.getenv("CAUVERIS_RUNTIME_FIXTURES", "false").lower() == "true"
    )
    autoload_sample: bool = field(
        default_factory=lambda: os.getenv("CAUVERIS_AUTOLOAD_SAMPLE", "false").lower() == "true"
    )
    allow_explicit_samples: bool = field(
        default_factory=lambda: os.getenv("CAUVERIS_ALLOW_EXPLICIT_SAMPLES", "false").lower() == "true"
    )
    nebius_routing_policy_version: str = field(
        default_factory=lambda: os.getenv("NEBIUS_ROUTING_POLICY_VERSION", "1.0")
    )
    prompt_template_version: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_PROMPT_TEMPLATE_VERSION", "1.0")
    )
    structured_output_schema_version: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_SCHEMA_VERSION", "1.0")
    )

    # Local model servers (Ollama / vLLM / LM Studio), OpenAI-compatible.
    # These are the fallback when the hosted provider cannot be reached -
    # which, on a robot, is a normal operating condition rather than an
    # exception.
    local_model_endpoints: str = field(
        default_factory=lambda: os.getenv(
            "CAUVERIS_LOCAL_MODEL_ENDPOINTS",
            "http://localhost:11434/v1,http://localhost:8000/v1",
        )
    )
    local_model_name: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_LOCAL_MODEL_NAME", "qwen2.5:7b-instruct")
    )
    local_model_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("CAUVERIS_LOCAL_MODEL_TIMEOUT", "60"))
    )
    local_model_probe_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("CAUVERIS_LOCAL_MODEL_PROBE_TIMEOUT", "0.5"))
    )

    # Simulation
    simulation_timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_SIMULATION_TIMEOUT", "300"))
    )
    max_experiment_trials: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_MAX_EXPERIMENT_TRIALS", "10"))
    )

    # Storage
    evidence_store_path: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_EVIDENCE_STORE", "./evidence_store")
    )
    report_store_path: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_REPORT_STORE", "./report")
    )
    sandbox_workspace_path: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_SANDBOX_WORKSPACE", "./sandbox_workspace")
    )

    # Safety thresholds
    max_patch_lines: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_MAX_PATCH_LINES", "50"))
    )
    safety_invariant_timeout: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_SAFETY_TIMEOUT", "60"))
    )

    # Concurrency Limits (Phase 5)
    concurrency_backend: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_CONCURRENCY_BACKEND", "memory")
    )
    concurrency_redis_url: str = field(
        default_factory=lambda: os.getenv(
            "CAUVERIS_CONCURRENCY_REDIS_URL", "redis://localhost:6379"
        )
    )
    max_concurrent_pipelines: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_MAX_CONCURRENT_PIPELINES", "5"))
    )
    max_concurrent_simulations: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_MAX_CONCURRENT_SIMULATIONS", "3"))
    )
    max_concurrent_model_inferences: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_MAX_CONCURRENT_MODEL_INFERENCES", "10"))
    )
    max_concurrent_sandboxes: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_MAX_CONCURRENT_SANDBOXES", "3"))
    )
    max_concurrent_patch_generation: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_MAX_CONCURRENT_PATCH_GENERATION", "3"))
    )
    concurrency_acquire_timeout: float = field(
        default_factory=lambda: float(os.getenv("CAUVERIS_CONCURRENCY_ACQUIRE_TIMEOUT", "30.0"))
    )
    concurrency_heartbeat_interval: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_CONCURRENCY_HEARTBEAT_INTERVAL", "30"))
    )
    concurrency_stale_threshold: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_CONCURRENCY_STALE_THRESHOLD", "300"))
    )

    # Rate Limiting (Phase 3)
    rate_limit_backend: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_BACKEND", "memory")
    )
    rate_limit_redis_url: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_REDIS_URL", "redis://localhost:6379")
    )
    rate_limit_fail_open: bool = field(
        default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_FAIL_OPEN", "true").lower() == "true"
    )

    # Rate limit defaults per cost class (format: "limit/window_seconds,limit/window_seconds").
    # Limits are expressed in the same unit as the class cost (see
    # cauveris.rate_limit_config.build_policies_from_settings), i.e. a request
    # of a class with cost N consumes N units of each window's allowance.
    rate_limit_low_cost: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_LOW_COST", "100/60,1000/3600")
    )
    rate_limit_normal_read: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_NORMAL_READ", "60/60,500/3600")
    )
    rate_limit_public_read: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_PUBLIC_READ", "200/60,2000/3600")
    )
    rate_limit_mutation: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_MUTATION", "30/60,200/3600")
    )
    rate_limit_upload: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_UPLOAD", "50/60,250/3600")
    )
    rate_limit_compute: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_COMPUTE", "50/60,300/3600")
    )
    rate_limit_experiment: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_EXPERIMENT", "60/60,200/3600")
    )
    rate_limit_patch: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_PATCH", "75/60,300/3600")
    )
    rate_limit_download: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_DOWNLOAD", "40/60,400/3600")
    )
    rate_limit_stream: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_STREAM", "5/60")
    )
    rate_limit_model: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_MODEL", "1000/60,5000/3600")
    )
    rate_limit_critical_cost: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_CRITICAL_COST", "200/60,1000/3600")
    )

    # Idempotency (Phase 4)
    idempotency_backend: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_IDEMPOTENCY_BACKEND", "memory")
    )
    idempotency_redis_url: str = field(
        default_factory=lambda: os.getenv(
            "CAUVERIS_IDEMPOTENCY_REDIS_URL", "redis://localhost:6379"
        )
    )
    idempotency_ttl_seconds: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_IDEMPOTENCY_TTL", "86400"))
    )  # 24h
    idempotency_enabled: bool = field(
        default_factory=lambda: os.getenv("CAUVERIS_IDEMPOTENCY_ENABLED", "true").lower() == "true"
    )

    # Job Queue (Phase 6)
    job_queue_backend: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_JOB_QUEUE_BACKEND", "memory")
    )
    job_queue_sqlite_path: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_JOB_QUEUE_SQLITE_PATH", "data/job_queue.db")
    )
    job_queue_redis_url: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_JOB_QUEUE_REDIS_URL", "redis://localhost:6379")
    )
    job_queue_rabbitmq_url: str = field(
        default_factory=lambda: os.getenv(
            "CAUVERIS_JOB_QUEUE_RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"
        )
    )
    job_queue_max_size: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_JOB_QUEUE_MAX_SIZE", "10000"))
    )
    job_queue_default_ttl: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_JOB_QUEUE_DEFAULT_TTL", "3600"))
    )
    job_queue_worker_concurrency: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_JOB_QUEUE_WORKER_CONCURRENCY", "2"))
    )
    # Run the worker handlers inside the API process.  A queue that nobody
    # serves fills up and never drains, so the default is to serve it.
    job_queue_embedded_worker: bool = field(
        default_factory=lambda: os.getenv(
            "CAUVERIS_JOB_QUEUE_EMBEDDED_WORKER", "true"
        ).lower()
        == "true"
    )
    # How long a worker may hold a job before the job is treated as abandoned
    # and handed back to the queue.  This is the lease a Redis-backed claim
    # holds: a worker that dies mid-job must not take the job with it.
    job_queue_claim_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("CAUVERIS_JOB_QUEUE_CLAIM_TIMEOUT", "300"))
    )

    # Authentication & Authorization
    runtime_mode: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_RUNTIME_MODE", "development").lower()
    )
    demo_auth: bool = field(
        default_factory=lambda: os.getenv("CAUVERIS_DEMO_AUTH", "false").lower() == "true"
    )
    auth_registration_enabled: bool = field(
        default_factory=lambda: os.getenv("CAUVERIS_AUTH_REGISTRATION_ENABLED", "true").lower() == "true"
    )
    auth_db_path: str = field(
        default_factory=lambda: os.getenv(
            "CAUVERIS_AUTH_DB_PATH",
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cauveris_auth.db"),
        )
    )
    model_execution_db_path: str = field(
        default_factory=lambda: os.getenv(
            "CAUVERIS_MODEL_EXECUTION_DB_PATH",
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "model_executions.db"),
        )
    )
    pipeline_db_path: str = field(
        default_factory=lambda: os.getenv(
            "CAUVERIS_PIPELINE_DB_PATH",
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "pipeline_stages.db"),
        )
    )
    auth_backend: str = field(default_factory=lambda: os.getenv("CAUVERIS_AUTH_BACKEND", "sqlite"))
    auth_redis_url: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_AUTH_REDIS_URL", "redis://localhost:6379")
    )
    auth_jwt_secret: str = field(
        default_factory=lambda: _validate_secret_key(
            os.getenv("CAUVERIS_JWT_SECRET", ""),
            "CAUVERIS_JWT_SECRET"
        )
    )
    auth_jwt_algorithm: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_JWT_ALGORITHM", "HS256")
    )
    auth_access_token_ttl_minutes: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_AUTH_ACCESS_TOKEN_TTL", "60"))
    )
    auth_refresh_token_ttl_days: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_AUTH_REFRESH_TOKEN_TTL", "30"))
    )
    auth_session_max_concurrent: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_AUTH_MAX_SESSIONS", "5"))
    )
    auth_password_min_length: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_AUTH_PASSWORD_MIN_LENGTH", "12"))
    )
    auth_mfa_required_for_roles: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_AUTH_MFA_REQUIRED_ROLES", "admin,super_admin")
    )
    auth_cookie_secure: bool = field(
        default_factory=lambda: (
            os.getenv("CAUVERIS_AUTH_COOKIE_SECURE", "true").lower() == "true"
            if os.getenv("CAUVERIS_RUNTIME_MODE", "development").lower() == "production"
            else os.getenv("CAUVERIS_AUTH_COOKIE_SECURE", "false").lower() == "true"
        )
    )
    auth_cookie_samesite: str = field(
        default_factory=lambda: os.getenv("CAUVERIS_AUTH_COOKIE_SAMESITE", "lax")
    )
    auth_rate_limit_logins_per_minute: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_AUTH_LOGIN_RATE_LIMIT", "10"))
    )
    auth_rate_limit_logins_per_hour: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_AUTH_LOGIN_RATE_LIMIT_HOUR", "50"))
    )
    auth_lockout_after_failures: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_AUTH_LOCKOUT_FAILURES", "5"))
    )
    auth_lockout_duration_minutes: int = field(
        default_factory=lambda: int(os.getenv("CAUVERIS_AUTH_LOCKOUT_DURATION", "15"))
    )

    def validate_production_security(self) -> None:
        """Validate production security invariants.

        Strictly forbids running with insecure demo authentication, insecure demo mode,
        or default development secrets in production runtime mode.
        """
        if self.runtime_mode in ("production", "production-demo"):
            if self.demo_auth:
                raise RuntimeError(
                    f"FATAL SECURITY VIOLATION: CAUVERIS_DEMO_AUTH is enabled while CAUVERIS_RUNTIME_MODE={self.runtime_mode}"
                )
            if self.demo_mode:
                raise RuntimeError(
                    f"FATAL SECURITY VIOLATION: CAUVERIS_DEMO_MODE is enabled while CAUVERIS_RUNTIME_MODE={self.runtime_mode}"
                )
            if self.runtime_fixtures:
                raise RuntimeError(
                    f"FATAL SECURITY VIOLATION: CAUVERIS_RUNTIME_FIXTURES is enabled while CAUVERIS_RUNTIME_MODE={self.runtime_mode}"
                )
            if self.autoload_sample:
                raise RuntimeError(
                    f"FATAL SECURITY VIOLATION: CAUVERIS_AUTOLOAD_SAMPLE is enabled while CAUVERIS_RUNTIME_MODE={self.runtime_mode}"
                )
            if self.allow_explicit_samples:
                raise RuntimeError(
                    f"FATAL SECURITY VIOLATION: CAUVERIS_ALLOW_EXPLICIT_SAMPLES is enabled while CAUVERIS_RUNTIME_MODE={self.runtime_mode}"
                )
            if self.runtime_mode == "production" and (
                self.secret_key == "dev-secret-change-in-prod"
                or os.getenv("CAUVERIS_SECRET_KEY") == "dev-secret-change-in-prod"
            ):
                raise RuntimeError(
                    "FATAL SECURITY VIOLATION: CAUVERIS_SECRET_KEY is using development default in production"
                )
            if self.runtime_mode == "production-demo" and not self.nebius_enabled:
                raise RuntimeError(
                    "FATAL CONFIGURATION ERROR: CAUVERIS_NEBIUS_ENABLED must be true in production-demo mode"
                )
            if not self.job_queue_embedded_worker and self.job_queue_backend == "memory":
                raise RuntimeError(
                    "FATAL CONFIGURATION ERROR: CAUVERIS_JOB_QUEUE_BACKEND cannot be 'memory' when CAUVERIS_JOB_QUEUE_EMBEDDED_WORKER=false. "
                    "External worker processes cannot access an in-memory queue in another process. "
                    "Configure a shared persistent backend ('sqlite', 'redis', or 'rabbitmq')."
                )

        if self.model_provider_required:
            if not self.nebius_api_key:
                raise RuntimeError(
                    "FATAL CONFIGURATION ERROR: Live model provider is required "
                    "(CAUVERIS_MODEL_PROVIDER_REQUIRED=true) but NEBIUS_API_KEY is not configured"
                )
            if not self.nebius_base_url or not self.nebius_base_url.startswith(("http://", "https://")):
                raise RuntimeError(
                    "FATAL CONFIGURATION ERROR: NEBIUS_BASE_URL must be a valid HTTP/HTTPS endpoint"
                )
            if not self.nebius_model_id:
                raise RuntimeError(
                    "FATAL CONFIGURATION ERROR: NEBIUS_MODEL_ID is not configured"
                )

        if self.nebius_request_timeout_seconds <= 0:
            raise RuntimeError(
                f"FATAL CONFIGURATION ERROR: NEBIUS_REQUEST_TIMEOUT_SECONDS must be positive, got {self.nebius_request_timeout_seconds}"
            )
        if self.nebius_max_retries < 0:
            raise RuntimeError(
                f"FATAL CONFIGURATION ERROR: NEBIUS_MAX_RETRIES cannot be negative, got {self.nebius_max_retries}"
            )


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings
