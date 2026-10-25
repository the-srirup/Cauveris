"""
Golden incident generator for CAU-0001.

This module used to hold a second, divergent copy of the generator that
wrote a placeholder MCAP file and a different evidence set than the rest of
the project used.  Two generators meant two different "golden" bundles, and
the one in this directory was the fabricated one.

There is now exactly one generator - :mod:`cauveris.datasets.golden_incident`
- and this module re-exports it, so any code that still imports
``datasets.golden_incident`` gets the real bundle.
"""

from cauveris.datasets.golden_incident import GoldenIncidentGenerator

__all__ = ["GoldenIncidentGenerator"]

if __name__ == "__main__":  # pragma: no cover - manual regeneration
    incident = GoldenIncidentGenerator().generate()
    print(f"Generated incident {incident.id} at ./incident-{incident.id}")
