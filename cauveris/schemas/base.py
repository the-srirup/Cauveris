"""
Base schemas and enums for Cauveris.
"""
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime
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
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        validate_assignment = True
