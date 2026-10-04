"""
Configuration management for Cauveris.
Loads settings from environment variables with sensible defaults.
"""
import os
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class Settings:
    """Application configuration."""

    # Server settings
    host: str = field(default_factory=lambda: os.getenv("CAUVERIS_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_PORT", "8000")))
    debug: bool = field(default_factory=lambda: os.getenv("CAUVERIS_DEBUG", "false").lower() == "true")

    # Security
    secret_key: str = field(default_factory=lambda: os.getenv("CAUVERIS_SECRET_KEY", "dev-secret-change-in-prod"))
    max_upload_size: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_MAX_UPLOAD_SIZE", "104857600")))  # 100MB

    # Incident Creation Limits (Phase 2)
    max_incidents_per_minute: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_MAX_INCIDENTS_PER_MINUTE", "5")))
    max_incidents_per_hour: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_MAX_INCIDENTS_PER_HOUR", "20")))
    max_incidents_per_day: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_MAX_INCIDENTS_PER_DAY", "50")))
    max_active_incidents_per_user: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_MAX_ACTIVE_INCIDENTS_PER_USER", "10")))
    max_retained_incidents_per_user: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_MAX_RETAINED_INCIDENTS_PER_USER", "100")))
    max_active_incidents_per_org: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_MAX_ACTIVE_INCIDENTS_PER_ORG", "50")))
    max_retained_incidents_per_org: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_MAX_RETAINED_INCIDENTS_PER_ORG", "500")))
    max_anonymous_incidents: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_MAX_ANONYMOUS_INCIDENTS", "2")))
    max_global_active_incidents: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_MAX_GLOBAL_ACTIVE_INCIDENTS", "100")))
    max_global_daily_creation: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_MAX_GLOBAL_DAILY_CREATION", "500")))

    # Model Gateway
    model_fast: str = field(default_factory=lambda: os.getenv("NEBIUS_MODEL_FAST", "nemotron-3-nano"))
    model_reasoning: str = field(default_factory=lambda: os.getenv("NEBIUS_MODEL_REASONING", "nemotron-3-super"))
    model_escalation: str = field(default_factory=lambda: os.getenv("NEBIUS_MODEL_ESCALATION", "nemotron-3-ultra"))
    nebius_api_key: Optional[str] = field(default_factory=lambda: os.getenv("NEBIUS_API_KEY"))
    nebius_base_url: str = field(default_factory=lambda: os.getenv("NEBIUS_BASE_URL", "https://api.nebius.ai/v1"))

    # Simulation
    simulation_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_SIMULATION_TIMEOUT", "300")))
    max_experiment_trials: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_MAX_EXPERIMENT_TRIALS", "10")))

    # Storage
    evidence_store_path: str = field(default_factory=lambda: os.getenv("CAUVERIS_EVIDENCE_STORE", "./evidence_store"))
    sandbox_workspace_path: str = field(default_factory=lambda: os.getenv("CAUVERIS_SANDBOX_WORKSPACE", "./sandbox_workspace"))

    # Safety thresholds
    max_patch_lines: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_MAX_PATCH_LINES", "50")))
    safety_invariant_timeout: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_SAFETY_TIMEOUT", "60")))

    # Concurrency Limits (Phase 5)
    concurrency_backend: str = field(default_factory=lambda: os.getenv("CAUVERIS_CONCURRENCY_BACKEND", "memory"))
    concurrency_redis_url: str = field(default_factory=lambda: os.getenv("CAUVERIS_CONCURRENCY_REDIS_URL", "redis://localhost:6379"))
    max_concurrent_pipelines: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_MAX_CONCURRENT_PIPELINES", "5")))
    max_concurrent_simulations: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_MAX_CONCURRENT_SIMULATIONS", "3")))
    max_concurrent_model_inferences: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_MAX_CONCURRENT_MODEL_INFERENCES", "10")))
    max_concurrent_sandboxes: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_MAX_CONCURRENT_SANDBOXES", "3")))
    max_concurrent_patch_generation: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_MAX_CONCURRENT_PATCH_GENERATION", "3")))
    concurrency_acquire_timeout: float = field(default_factory=lambda: float(os.getenv("CAUVERIS_CONCURRENCY_ACQUIRE_TIMEOUT", "30.0")))
    concurrency_heartbeat_interval: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_CONCURRENCY_HEARTBEAT_INTERVAL", "30")))
    concurrency_stale_threshold: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_CONCURRENCY_STALE_THRESHOLD", "300")))

    # Rate Limiting (Phase 3)
    rate_limit_backend: str = field(default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_BACKEND", "memory"))
    rate_limit_redis_url: str = field(default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_REDIS_URL", "redis://localhost:6379"))
    rate_limit_fail_open: bool = field(default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_FAIL_OPEN", "true").lower() == "true")

    # Rate limit defaults per cost class (format: "limit/window_seconds,limit/window_seconds")
    rate_limit_low_cost: str = field(default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_LOW_COST", "100/60,1000/3600"))
    rate_limit_normal_read: str = field(default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_NORMAL_READ", "60/60,500/3600"))
    rate_limit_public_read: str = field(default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_PUBLIC_READ", "200/60,2000/3600"))
    rate_limit_mutation: str = field(default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_MUTATION", "30/60,200/3600"))
    rate_limit_upload: str = field(default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_UPLOAD", "10/60,50/3600"))
    rate_limit_compute: str = field(default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_COMPUTE", "5/60,30/3600"))
    rate_limit_experiment: str = field(default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_EXPERIMENT", "3/60,10/3600"))
    rate_limit_patch: str = field(default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_PATCH", "5/60,20/3600"))
    rate_limit_download: str = field(default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_DOWNLOAD", "20/60,200/3600"))
    rate_limit_stream: str = field(default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_STREAM", "5/60"))
    rate_limit_model: str = field(default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_MODEL", "20/60,100/3600"))
    rate_limit_critical_cost: str = field(default_factory=lambda: os.getenv("CAUVERIS_RATE_LIMIT_CRITICAL_COST", "2/60,10/3600"))

    # Idempotency (Phase 4)
    idempotency_backend: str = field(default_factory=lambda: os.getenv("CAUVERIS_IDEMPOTENCY_BACKEND", "memory"))
    idempotency_redis_url: str = field(default_factory=lambda: os.getenv("CAUVERIS_IDEMPOTENCY_REDIS_URL", "redis://localhost:6379"))
    idempotency_ttl_seconds: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_IDEMPOTENCY_TTL", "86400")))  # 24h
    idempotency_enabled: bool = field(default_factory=lambda: os.getenv("CAUVERIS_IDEMPOTENCY_ENABLED", "true").lower() == "true")

    # Job Queue (Phase 6)
    job_queue_backend: str = field(default_factory=lambda: os.getenv("CAUVERIS_JOB_QUEUE_BACKEND", "memory"))
    job_queue_redis_url: str = field(default_factory=lambda: os.getenv("CAUVERIS_JOB_QUEUE_REDIS_URL", "redis://localhost:6379"))
    job_queue_max_size: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_JOB_QUEUE_MAX_SIZE", "10000")))
    job_queue_default_ttl: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_JOB_QUEUE_DEFAULT_TTL", "3600")))
    job_queue_worker_concurrency: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_JOB_QUEUE_WORKER_CONCURRENCY", "2")))

    # Authentication & Authorization
    auth_backend: str = field(default_factory=lambda: os.getenv("CAUVERIS_AUTH_BACKEND", "memory"))
    auth_redis_url: str = field(default_factory=lambda: os.getenv("CAUVERIS_AUTH_REDIS_URL", "redis://localhost:6379"))
    auth_jwt_secret: str = field(default_factory=lambda: os.getenv("CAUVERIS_JWT_SECRET", "dev-jwt-secret-change-in-production-min-32-chars"))
    auth_jwt_algorithm: str = field(default_factory=lambda: os.getenv("CAUVERIS_JWT_ALGORITHM", "HS256"))
    auth_access_token_ttl_minutes: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_AUTH_ACCESS_TOKEN_TTL", "60")))
    auth_refresh_token_ttl_days: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_AUTH_REFRESH_TOKEN_TTL", "30")))
    auth_session_max_concurrent: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_AUTH_MAX_SESSIONS", "5")))
    auth_password_min_length: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_AUTH_PASSWORD_MIN_LENGTH", "12")))
    auth_mfa_required_for_roles: str = field(default_factory=lambda: os.getenv("CAUVERIS_AUTH_MFA_REQUIRED_ROLES", "admin,super_admin"))
    auth_cookie_secure: bool = field(default_factory=lambda: os.getenv("CAUVERIS_AUTH_COOKIE_SECURE", "false").lower() == "true")
    auth_cookie_samesite: str = field(default_factory=lambda: os.getenv("CAUVERIS_AUTH_COOKIE_SAMESITE", "lax"))
    auth_rate_limit_logins_per_minute: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_AUTH_LOGIN_RATE_LIMIT", "10")))
    auth_rate_limit_logins_per_hour: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_AUTH_LOGIN_RATE_LIMIT_HOUR", "50")))
    auth_lockout_after_failures: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_AUTH_LOCKOUT_FAILURES", "5")))
    auth_lockout_duration_minutes: int = field(default_factory=lambda: int(os.getenv("CAUVERIS_AUTH_LOCKOUT_DURATION", "15")))


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings
