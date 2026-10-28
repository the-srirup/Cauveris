"""
Repair-package generation, storage, and download for Cauveris.

This package implements the canonical repair-package workflow:

1. Explicit persisted package states (``PackageStatus``).
2. A canonical package record with source-bound, tamper-evident metadata
   (``RepairPackageRecord``).
3. Strict candidate selection and the 10-point pre-validation gate.
4. The exact verification ladder (``VerificationLevel``).
5. A versioned manifest schema.
6. Real archive assembly with per-file SHA-256 checksums and self-validation.
7. An artifact-storage abstraction with persistence, atomic promotion,
   retention, and cross-incident/cross-user isolation.
8. Structured, auditable API endpoints for package generation and download.

It is intentionally self-contained and writes to its own metadata index so that
package state survives process restarts independently of in-memory pipeline state.
"""

from cauveris.packaging.models import (
    PackageStatus,
    VerificationLevel,
    RepairPackageRecord,
    PackageGenerationRequest,
    PackageError,
    PACKAGE_ERRORS,
)
from cauveris.packaging.storage import PackageStore
from cauveris.packaging.builder import PackageBuilder, BuildOutcome
from cauveris.packaging.validation import validate_package_archive, ValidationFailure

__all__ = [
    "PackageStatus",
    "VerificationLevel",
    "RepairPackageRecord",
    "PackageGenerationRequest",
    "PackageError",
    "PACKAGE_ERRORS",
    "PackageStore",
    "PackageBuilder",
    "BuildOutcome",
    "validate_package_archive",
    "ValidationFailure",
]
