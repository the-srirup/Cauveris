"""Tests for counterfactual holography (Phase 4)."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from synthetic import SyntheticIncidentGenerator, IncidentType

from cauveris.holographic.counterfactual import (
    CounterfactualHolographer,
    CounterfactualResult,
    Intervention,
    InterventionType,
    create_standard_interventions,
)
from cauveris.holographic.heu_kernel import CausalKernelBuilder
from cauveris.holographic.integration import (
    HolographicAnalyzer,
    HolographicConfig,
)


@pytest.fixture(scope="module")
def incident():
    generator = SyntheticIncidentGenerator(seed=42)
    return generator.generate(IncidentType.CPU_SPIKE_CASCADE)


@pytest.fixture(scope="module")
def analysis(incident):
    config = HolographicConfig(enable_multiscale=False, enable_compression=False)
    analyzer = HolographicAnalyzer(config)
    return analyzer.analyze_incident(
        incident_id=incident.incident_id,
        timeline=incident.timeline,
        topology=incident.topology,
    )


@pytest.fixture(scope="module")
def holographer(incident):
    builder = CausalKernelBuilder(incident.topology)
    builder.build_all_kernels()
    return CounterfactualHolographer(incident.topology, builder)


class TestIntervention:
    def test_auto_description(self):
        iv = Intervention(
            intervention_type=InterventionType.CPU_SCALING,
            target_component="svc_0",
        )
        assert "cpu_scaling" in iv.description
        assert "svc_0" in iv.description

    def test_explicit_description_preserved(self):
        iv = Intervention(
            intervention_type=InterventionType.RESTART_SERVICE,
            target_component="svc_0",
            description="custom",
        )
        assert iv.description == "custom"

    def test_parameters_default_empty(self):
        iv = Intervention(
            intervention_type=InterventionType.RESTART_SERVICE,
            target_component="svc_0",
        )
        assert iv.parameters == {}


class TestCounterfactualHolographer:
    def test_simulate_returns_result(self, holographer, analysis):
        iv = Intervention(
            intervention_type=InterventionType.CPU_SCALING,
            target_component="svc_0",
            parameters={"scale_factor": 4.0},
        )
        result = holographer.simulate(
            analysis.reconstruction, iv, analysis.time_window_ns
        )
        assert isinstance(result, CounterfactualResult)
        assert result.intervention is iv

    def test_original_reconstruction_not_mutated(self, holographer, analysis):
        """Intervention must not mutate the caller's reconstruction."""
        before = {
            name: state.cpu_usage
            for name, state in analysis.reconstruction.reconstructed_services.items()
        }
        iv = Intervention(
            intervention_type=InterventionType.RESTART_SERVICE,
            target_component="svc_0",
        )
        holographer.simulate(analysis.reconstruction, iv, analysis.time_window_ns)

        after = {
            name: state.cpu_usage
            for name, state in analysis.reconstruction.reconstructed_services.items()
        }
        assert before == after

    def test_intervention_reduces_cpu(self, holographer, analysis):
        iv = Intervention(
            intervention_type=InterventionType.CPU_SCALING,
            target_component="svc_0",
            parameters={"scale_factor": 4.0},
        )
        result = holographer.simulate(
            analysis.reconstruction, iv, analysis.time_window_ns
        )
        original = result.original_reconstruction.reconstructed_services["svc_0"]
        intervened = result.intervened_reconstruction.reconstructed_services["svc_0"]
        assert intervened.cpu_usage <= original.cpu_usage

    def test_cpu_scaling_improves_health(self, holographer, analysis):
        iv = Intervention(
            intervention_type=InterventionType.CPU_SCALING,
            target_component="svc_0",
            parameters={"scale_factor": 4.0},
        )
        result = holographer.simulate(
            analysis.reconstruction, iv, analysis.time_window_ns
        )
        assert result.fidelity_improvement > 0

    def test_restart_reduces_error_rate(self, holographer, analysis):
        iv = Intervention(
            intervention_type=InterventionType.RESTART_SERVICE,
            target_component="svc_2",
        )
        result = holographer.simulate(
            analysis.reconstruction, iv, analysis.time_window_ns
        )
        intervened = result.intervened_reconstruction.reconstructed_services["svc_2"]
        assert intervened.error_rate <= 0.01

    def test_traffic_reduction_scales_load(self, holographer, analysis):
        target = "svc_0"
        iv = Intervention(
            intervention_type=InterventionType.TRAFFIC_REDUCTION,
            target_component=target,
            parameters={"reduction_factor": 0.5},
        )
        result = holographer.simulate(
            analysis.reconstruction, iv, analysis.time_window_ns
        )
        original = result.original_reconstruction.reconstructed_services[target]
        intervened = result.intervened_reconstruction.reconstructed_services[target]
        assert intervened.cpu_usage == pytest.approx(original.cpu_usage * 0.5)

    def test_unknown_component_is_noop(self, holographer, analysis):
        iv = Intervention(
            intervention_type=InterventionType.RESTART_SERVICE,
            target_component="does_not_exist",
        )
        result = holographer.simulate(
            analysis.reconstruction, iv, analysis.time_window_ns
        )
        assert result.fidelity_improvement == 0.0

    def test_network_capacity_updates_edges(self, holographer, analysis):
        target = "svc_0"
        iv = Intervention(
            intervention_type=InterventionType.NETWORK_CAPACITY,
            target_component=target,
            parameters={"bandwidth_factor": 2.0},
        )
        result = holographer.simulate(
            analysis.reconstruction, iv, analysis.time_window_ns
        )
        net = result.intervened_reconstruction.reconstructed_network
        if net and net.edges:
            touched = [
                e for (s, d), e in net.edges.items()
                if s == target or d == target
            ]
            for edge in touched:
                assert edge.bandwidth_mbps > 0

    def test_predicted_boundary_structure(self, holographer, analysis):
        iv = Intervention(
            intervention_type=InterventionType.RESTART_SERVICE,
            target_component="svc_0",
        )
        result = holographer.simulate(
            analysis.reconstruction, iv, analysis.time_window_ns
        )
        pb = result.predicted_boundary
        assert "service_predictions" in pb
        assert "network_predictions" in pb
        assert len(pb["service_predictions"]) == len(
            analysis.reconstruction.reconstructed_services
        )

    def test_cost_and_risk_bounded(self, holographer, analysis):
        iv = Intervention(
            intervention_type=InterventionType.RESTART_SERVICE,
            target_component="svc_0",
        )
        result = holographer.simulate(
            analysis.reconstruction, iv, analysis.time_window_ns
        )
        assert 0.0 <= result.cost_estimate <= 100.0
        assert 0.0 <= result.risk_score <= 1.0

    def test_rollout_covers_all_interventions(self, holographer, analysis):
        interventions = [
            Intervention(InterventionType.CPU_SCALING, "svc_0"),
            Intervention(InterventionType.MEMORY_SCALING, "svc_1"),
            Intervention(InterventionType.RESTART_SERVICE, "svc_2"),
        ]
        rollout = holographer.run_rollout(
            analysis.reconstruction, interventions, analysis.time_window_ns
        )
        assert len(rollout) == 3

    def test_recommendations_sorted_by_score(self, holographer, analysis):
        interventions = create_standard_interventions(holographer.topology)
        rollout = holographer.run_rollout(
            analysis.reconstruction, interventions, analysis.time_window_ns
        )
        recs = holographer.get_recommendations(rollout, max_cost=100, max_risk=1.0)
        assert len(recs) > 0
        # Verify ordering is monotonically non-increasing by score
        scores = [
            r.fidelity_improvement / (r.cost_estimate * r.risk_score + 1e-6)
            for _, r in recs
        ]
        assert scores == sorted(scores, reverse=True)

    def test_recommendations_respect_filters(self, holographer, analysis):
        interventions = create_standard_interventions(holographer.topology)
        rollout = holographer.run_rollout(
            analysis.reconstruction, interventions, analysis.time_window_ns
        )
        recs = holographer.get_recommendations(rollout, max_cost=6.0, max_risk=0.2)
        for _, result in recs:
            assert result.cost_estimate <= 6.0
            assert result.risk_score <= 0.2


class TestStandardInterventions:
    def test_generates_interventions_for_all_components(self, incident):
        interventions = create_standard_interventions(incident.topology)
        targets = {iv.target_component for iv in interventions}
        assert targets == set(incident.topology.components.keys())

    def test_includes_multiple_types(self, incident):
        interventions = create_standard_interventions(incident.topology)
        types = {iv.intervention_type for iv in interventions}
        assert InterventionType.CPU_SCALING in types
        assert InterventionType.RESTART_SERVICE in types


class TestAnalyzerCounterfactualIntegration:
    def test_simulate_counterfactuals(self, analysis, incident):
        config = HolographicConfig(enable_multiscale=False, enable_compression=False)
        analyzer = HolographicAnalyzer(config)
        analyzer.analyze_incident(
            incident_id=incident.incident_id,
            timeline=incident.timeline,
            topology=incident.topology,
        )
        recs = analyzer.simulate_counterfactuals(analysis, limit=3)
        assert len(recs) <= 3
        assert all(isinstance(desc, str) for desc, _ in recs)

    def test_requires_topology(self):
        analyzer = HolographicAnalyzer()
        with pytest.raises(RuntimeError):
            analyzer.simulate_counterfactuals(None)
