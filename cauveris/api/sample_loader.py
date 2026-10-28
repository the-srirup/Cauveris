"""Explicit opt-in loader for the bundled demonstration incident."""

from __future__ import annotations

from cauveris.schemas.incident import Incident


def load_explicit_sample() -> Incident:
    """Load sample data only after an explicit caller request."""
    from cauveris.datasets.golden_incident import GoldenIncidentGenerator

    incident = GoldenIncidentGenerator().generate()
    incident.is_demonstration = True
    return incident
