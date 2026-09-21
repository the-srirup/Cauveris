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


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings
