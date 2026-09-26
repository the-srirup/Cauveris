"""
Unit tests for Reconstruction data structures - Phase 1.

Tests cover:
- ReconstructedServiceState
- ReconstructedNetworkState / NetworkEdge
- ReconstructedResourceState
- AmbiguityRegion
- HolographicReconstruction
"""
import pytest

from cauveris.holographic.reconstruction import (
    ReconstructedServiceState,
    ReconstructedNetworkState,
    NetworkEdge,
    ReconstructedResourceState,
    AmbiguityRegion,
    HolographicReconstruction,
)


class TestReconstructedServiceState:
    """Test ReconstructedServiceState dataclass."""

    def test_creation_with_defaults(self):
        state = ReconstructedServiceState(component_name="nav", instance_id="nav-1")
        assert state.component_name == "nav"
        assert state.instance_id == "nav-1"
        assert state.cpu_usage == 0.0
        assert state.confidence == 0.0
        assert state.coverage == 0.0

    def test_creation_with_values(self):
        state = ReconstructedServiceState(
            component_name="nav",
            instance_id="nav-1",
            cpu_usage=0.7,
            memory_usage=0.5,
            network_usage=0.3,
            error_rate=0.1,
            confidence=0.9,
            coverage=0.8,
        )
        assert state.cpu_usage == 0.7
        assert state.confidence == 0.9

    def test_clamping_to_range(self):
        # Values should be clamped to [0,1]
        state = ReconstructedServiceState(
            component_name="test",
            instance_id="i1",
            cpu_usage=1.5,  # Should clamp
            memory_usage=-0.2,  # Should clamp
            confidence=2.0,
        )
        assert state.cpu_usage == 1.0
        assert state.memory_usage == 0.0
        assert state.confidence == 1.0

    def test_is_healthy(self):
        healthy = ReconstructedServiceState(
            component_name="good", instance_id="g1",
            cpu_usage=0.5, memory_usage=0.4, error_rate=0.05, confidence=0.8
        )
        unhealthy_cpu = ReconstructedServiceState(
            component_name="bad_cpu", instance_id="b1",
            cpu_usage=0.9, memory_usage=0.4, error_rate=0.05, confidence=0.8
        )
        unhealthy_mem = ReconstructedServiceState(
            component_name="bad_mem", instance_id="b2",
            cpu_usage=0.5, memory_usage=0.9, error_rate=0.05, confidence=0.8
        )
        unhealthy_err = ReconstructedServiceState(
            component_name="bad_err", instance_id="b3",
            cpu_usage=0.5, memory_usage=0.4, error_rate=0.5, confidence=0.8
        )
        unhealthy_conf = ReconstructedServiceState(
            component_name="bad_conf", instance_id="b4",
            cpu_usage=0.5, memory_usage=0.4, error_rate=0.05, confidence=0.3
        )

        assert healthy.is_healthy
        assert not unhealthy_cpu.is_healthy
        assert not unhealthy_mem.is_healthy
        assert not unhealthy_err.is_healthy
        assert not unhealthy_conf.is_healthy

    def test_primary_bottleneck(self):
        # CPU is highest
        state = ReconstructedServiceState(
            component_name="test", instance_id="i1",
            cpu_usage=0.9, memory_usage=0.7, network_usage=0.5, error_rate=0.1
        )
        assert state.primary_bottleneck == "cpu"

        # Memory is highest
        state2 = ReconstructedServiceState(
            component_name="test", instance_id="i1",
            cpu_usage=0.7, memory_usage=0.9, network_usage=0.5, error_rate=0.1
        )
        assert state2.primary_bottleneck == "memory"

        # Error rate is highest
        state3 = ReconstructedServiceState(
            component_name="test", instance_id="i1",
            cpu_usage=0.5, memory_usage=0.5, network_usage=0.5, error_rate=0.8
        )
        assert state3.primary_bottleneck == "errors"

        # No bottleneck
        state4 = ReconstructedServiceState(
            component_name="test", instance_id="i1",
            cpu_usage=0.3, memory_usage=0.3, network_usage=0.3, error_rate=0.05
        )
        assert state4.primary_bottleneck is None

    def test_to_dict(self):
        state = ReconstructedServiceState(
            component_name="nav",
            instance_id="nav-1",
            cpu_usage=0.7,
            upstream_health={"svc_a": 0.9},
        )
        d = state.to_dict()
        assert d["component_name"] == "nav"
        assert d["cpu_usage"] == 0.7
        assert d["upstream_health"] == {"svc_a": 0.9}


class TestNetworkEdge:
    """Test NetworkEdge dataclass."""

    def test_creation(self):
        edge = NetworkEdge(source="a", target="b", latency_ms=5.0, loss_rate=0.01)
        assert edge.source == "a"
        assert edge.target == "b"
        assert edge.latency_ms == 5.0

    def test_clamping(self):
        edge = NetworkEdge(source="a", target="b", loss_rate=1.5, confidence=-0.1)
        assert edge.loss_rate == 1.0
        assert edge.confidence == 0.0

    def test_to_dict(self):
        edge = NetworkEdge(source="a", target="b", latency_ms=10.0)
        d = edge.to_dict()
        assert d["source"] == "a"
        assert d["target"] == "b"
        assert d["latency_ms"] == 10.0


class TestReconstructedNetworkState:
    """Test ReconstructedNetworkState dataclass."""

    def test_add_and_get_edge(self):
        net = ReconstructedNetworkState()
        edge = NetworkEdge(source="a", target="b", latency_ms=5.0)
        net.add_edge("a", "b", edge)

        retrieved = net.get_edge("a", "b")
        assert retrieved is not None
        assert retrieved.latency_ms == 5.0

        not_found = net.get_edge("b", "a")
        assert not_found is None

    def test_to_dict(self):
        net = ReconstructedNetworkState()
        net.add_edge("a", "b", NetworkEdge(source="a", target="b", latency_ms=5.0))
        d = net.to_dict()
        assert "a->b" in d["edges"]
        assert d["edges"]["a->b"]["latency_ms"] == 5.0


class TestReconstructedResourceState:
    """Test ReconstructedResourceState dataclass."""

    def test_utilization_properties(self):
        res = ReconstructedResourceState(
            total_cpu_cores=100.0,
            total_memory_gb=200.0,
            used_cpu_cores=75.0,
            used_memory_gb=150.0,
        )
        assert res.cpu_utilization == 0.75
        assert res.memory_utilization == 0.75

    def test_zero_totals(self):
        res = ReconstructedResourceState(
            total_cpu_cores=0.0,
            total_memory_gb=0.0,
        )
        assert res.cpu_utilization == 0.0
        assert res.memory_utilization == 0.0

    def test_to_dict(self):
        res = ReconstructedResourceState(
            total_cpu_cores=100.0,
            cpu_by_component={"svc_a": 50.0},
        )
        d = res.to_dict()
        assert d["total_cpu_cores"] == 100.0
        assert d["cpu_by_component"] == {"svc_a": 50.0}


class TestAmbiguityRegion:
    """Test AmbiguityRegion dataclass."""

    def test_creation(self):
        region = AmbiguityRegion(
            component="nav",
            time_range_ns=(100_000_000, 500_000_000),
            affected_dimensions=["cpu_pressure", "memory_pressure"],
            ambiguity_score=0.8,
            missing_layers=["distributed_trace"],
            description="Insufficient trace data",
        )
        assert region.component == "nav"
        assert region.ambiguity_score == 0.8

    def test_invalid_ambiguity_score(self):
        with pytest.raises(ValueError, match="ambiguity_score must be in"):
            AmbiguityRegion(
                component="test",
                time_range_ns=(0, 100),
                affected_dimensions=[],
                ambiguity_score=1.5,
                missing_layers=[],
                description="",
            )

    def test_duration_ms(self):
        region = AmbiguityRegion(
            component="test",
            time_range_ns=(0, 1_000_000_000),  # 1 second
            affected_dimensions=[],
            ambiguity_score=0.5,
            missing_layers=[],
            description="",
        )
        assert region.duration_ms == 1000.0

    def test_to_dict(self):
        region = AmbiguityRegion(
            component="nav",
            time_range_ns=(100_000_000, 200_000_000),
            affected_dimensions=["cpu"],
            ambiguity_score=0.7,
            missing_layers=["trace"],
            description="Test",
        )
        d = region.to_dict()
        assert d["component"] == "nav"
        assert d["start_ns"] == 100_000_000
        assert d["end_ns"] == 200_000_000
        assert d["duration_ms"] == 100.0
        assert d["ambiguity_score"] == 0.7


class TestHolographicReconstruction:
    """Test HolographicReconstruction dataclass."""

    def test_creation_with_defaults(self):
        recon = HolographicReconstruction(
            incident_id="INC-001",
            reconstruction_timestamp_ns=1_000_000_000,
            time_window_ns=(0, 1_000_000_000),
        )
        assert recon.incident_id == "INC-001"
        assert recon.reconstructed_network is not None
        assert recon.reconstructed_resources is not None
        assert recon.overall_fidelity == 0.0

    def test_get_service(self):
        recon = HolographicReconstruction(
            incident_id="INC-001",
            reconstruction_timestamp_ns=0,
            time_window_ns=(0, 100),
        )
        recon.reconstructed_services["navigation_service_nav-1"] = ReconstructedServiceState(
            component_name="navigation_service", instance_id="nav-1"
        )
        recon.reconstructed_services["planning_service_plan-1"] = ReconstructedServiceState(
            component_name="planning_service", instance_id="plan-1"
        )

        # Match by prefix
        nav = recon.get_service("navigation")
        assert nav is not None
        assert nav.component_name == "navigation_service"

        # Match by substring
        plan = recon.get_service("planning")
        assert plan is not None
        assert plan.component_name == "planning_service"

        # No match
        assert recon.get_service("unknown") is None

    def test_unhealthy_services(self):
        recon = HolographicReconstruction(
            incident_id="INC-001",
            reconstruction_timestamp_ns=0,
            time_window_ns=(0, 100),
        )
        recon.reconstructed_services["healthy"] = ReconstructedServiceState(
            component_name="healthy", instance_id="h1",
            cpu_usage=0.5, memory_usage=0.5, error_rate=0.0, confidence=0.8
        )
        recon.reconstructed_services["unhealthy1"] = ReconstructedServiceState(
            component_name="unhealthy1", instance_id="u1",
            cpu_usage=0.9, memory_usage=0.5, error_rate=0.0, confidence=0.8
        )
        recon.reconstructed_services["unhealthy2"] = ReconstructedServiceState(
            component_name="unhealthy2", instance_id="u2",
            cpu_usage=0.5, memory_usage=0.5, error_rate=0.5, confidence=0.8
        )

        unhealthy = recon.unhealthy_services
        assert len(unhealthy) == 2
        names = {s.component_name for s in unhealthy}
        assert names == {"unhealthy1", "unhealthy2"}

    def test_has_high_ambiguity(self):
        recon = HolographicReconstruction(
            incident_id="INC-001",
            reconstruction_timestamp_ns=0,
            time_window_ns=(0, 100),
        )
        assert not recon.has_high_ambiguity

        recon.ambiguity_regions.append(AmbiguityRegion(
            component="test",
            time_range_ns=(0, 100),
            affected_dimensions=["cpu"],
            ambiguity_score=0.7,
            missing_layers=[],
            description="",
        ))
        assert not recon.has_high_ambiguity  # 0.7 is not > 0.7

        recon.ambiguity_regions.append(AmbiguityRegion(
            component="test",
            time_range_ns=(0, 100),
            affected_dimensions=["cpu"],
            ambiguity_score=0.8,
            missing_layers=[],
            description="",
        ))
        assert recon.has_high_ambiguity

    def test_to_dict(self):
        recon = HolographicReconstruction(
            incident_id="INC-001",
            reconstruction_timestamp_ns=1_000_000_000,
            time_window_ns=(0, 1_000_000_000),
        )
        recon.reconstructed_services["test"] = ReconstructedServiceState(
            component_name="test", instance_id="t1"
        )
        d = recon.to_dict()
        assert d["incident_id"] == "INC-001"
        assert "reconstructed_services" in d
        assert "test" in d["reconstructed_services"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
