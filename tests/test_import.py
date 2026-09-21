"""
Test to verify all key Cauveris modules can be imported.
"""
import sys
import os

# Add repo root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_imports():
    """Test that all key modules import cleanly."""
    import cauveris.config
    import cauveris.schemas.incident
    import cauveris.schemas.hypothesis
    import cauveris.schemas.experiment
    import cauveris.schemas.patch
    import cauveris.model_gateway.base
    import cauveris.model_gateway.local
    import cauveris.model_gateway.nebius
    import cauveris.ingestion.controller
    import cauveris.timeline.builder
    import cauveris.hypothesis.generator
    import cauveris.sandbox.controller
    import cauveris.simulation.runner
    import cauveris.patch.generator
    import cauveris.verifier.engine
    import cauveris.report.generator
    import cauveris.state_machine.orchestrator
    import cauveris.api.main
    import cauveris.datasets.golden_incident

    assert cauveris.config.get_settings() is not None
