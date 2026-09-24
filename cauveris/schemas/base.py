"""
Base schemas and enums for Cauveris.
"""
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timezone
import uuid


class StatusLabel(str, Enum):
    """Status labels for evidence and conclusions."""
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    REPRODUCED = "REPRODUCED"
    PATCHED = "PATCHED"
    VERIFIED_IN_SANDBOX = "VERIFIED_IN_SANDBOX"
    PENDING_HARDWARE_VALIDATION = "PENDING_HARDWARE_VALIDATION"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    SECRETS_DETECTED = "SECRETS_DETECTED"
    PROCESSING_ERROR = "PROCESSING_ERROR"
    MISSING = "MISSING"
    # Experiment statuses
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    SIMULATING = "SIMULATING"
    SIMULATED = "SIMULATED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class BaseEntity(BaseModel):
    """Base entity with common fields."""
    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
