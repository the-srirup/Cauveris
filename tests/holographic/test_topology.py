"""
Unit tests for SystemTopology - Phase 1.

Tests cover:
- ComponentInfo and ResourceCapacity
- CausalEdge
- SystemTopology graph operations
- Loading from bundle configs
- Building from timeline events
"""
import pytest
import yaml
import json

from cauveris.holographic.topology import (
    SystemTopology,
    ComponentInfo,
    CausalEdge,
    ResourceCapacity,
    build_topology_from_timeline,
    _infer_component_type,
    _source_type_to_boundary_layer,
)


class TestResourceCapacity:
    """Test ResourceCapacity dataclass."""

    def test_default_values(self):
        cap = ResourceCapacity()
        assert cap.cpu_cores == 4.0
        assert cap.memory_gb == 8.0
        assert cap.network_gbps == 1.0
        assert cap.max_rps == 1000.0

    def test_custom_values(self):
        cap = ResourceCapacity(cpu_cores=8.0, memory_gb=16.0, network_gbps=10.0, max_rps=5000.0)
        assert cap.cpu_cores == 8.0
        assert cap.memory_gb == 16.0
        assert cap.network_gbps == 10.0
        assert cap.max_rps == 5000.0

    def test_to_dict(self):
        cap = ResourceCapacity(cpu_cores=4.0, memory_gb=8.0)
        d = cap.to_dict()
        assert d["cpu_cores"] == 4.0
        assert d["memory_gb"] == 8.0


class TestComponentInfo:
    """Test ComponentInfo dataclass."""

    def test_creation(self):
        comp = ComponentInfo(
            name="nav_service",
            instance_ids=["nav-1", "nav-2"],
            component_type="service",
            capacity=ResourceCapacity(cpu_cores=4.0),
        )
        assert comp.name == "nav_service"
        assert len(comp.instance_ids) == 2
        assert comp.capacity.cpu_cores == 4.0

    def test_to_dict(self):
        comp = ComponentInfo(name="test", instance_ids=["i1"])
        d = comp.to_dict()
        assert d["name"] == "test"
        assert d["instance_ids"] == ["i1"]
        assert "capacity" in d


class TestCausalEdge:
    """Test CausalEdge dataclass."""

    def test_creation(self):
        edge = CausalEdge(
            source="svc_a",
            target="svc_b",
            edge_type="rpc",
            latency_ms=5.0,
            confidence=0.9,
        )
        assert edge.source == "svc_a"
        assert edge.target == "svc_b"
        assert edge.latency_ms == 5.0

    def test_invalid_confidence(self):
        with pytest.raises(ValueError, match="confidence must be in"):
            CausalEdge(source="a", target="b", confidence=1.5)

        with pytest.raises(ValueError, match="confidence must be in"):
            CausalEdge(source="a", target="b", confidence=-0.1)

    def test_to_dict(self):
        edge = CausalEdge(source="a", target="b", edge_type="topic", latency_ms=10.0)
        d = edge.to_dict()
        assert d["source"] == "a"
        assert d["target"] == "b"
        assert d["edge_type"] == "topic"


class TestSystemTopology:
    """Test SystemTopology class."""

    def setup_method(self):
        self.topology = SystemTopology()

    def test_add_component(self):
        comp = ComponentInfo(name="svc_a", instance_ids=["a1", "a2"])
        self.topology.add_component(comp)
        assert "svc_a" in self.topology.components
        assert self.topology.get_component_for_instance("a1") == "svc_a"
        assert self.topology.get_component_for_instance("a2") == "svc_a"

    def test_add_causal_edge(self):
        self.topology.add_component(ComponentInfo(name="svc_a"))
        self.topology.add_component(ComponentInfo(name="svc_b"))

        edge = CausalEdge(source="svc_a", target="svc_b", latency_ms=5.0)
        self.topology.add_causal_edge(edge)

        assert len(self.topology.causal_edges) == 1
        assert self.topology.get_direct_downstream("svc_a") == ["svc_b"]
        assert self.topology.get_direct_upstream("svc_b") == ["svc_a"]

    def test_bidirectional_edge(self):
        self.topology.add_component(ComponentInfo(name="svc_a"))
        self.topology.add_component(ComponentInfo(name="svc_b"))

        edge = CausalEdge(source="svc_a", target="svc_b", bidirectional=True)
        self.topology.add_causal_edge(edge)

        assert self.topology.get_direct_downstream("svc_a") == ["svc_b"]
        assert self.topology.get_direct_downstream("svc_b") == ["svc_a"]

    def test_has_path(self):
        self.topology.add_component(ComponentInfo(name="a"))
        self.topology.add_component(ComponentInfo(name="b"))
        self.topology.add_component(ComponentInfo(name="c"))

        self.topology.add_causal_edge(CausalEdge(source="a", target="b"))
        self.topology.add_causal_edge(CausalEdge(source="b", target="c"))

        assert self.topology.has_path("a", "c") is True
        assert self.topology.has_path("c", "a") is False
        assert self.topology.has_path("a", "a") is True

    def test_get_downstream_upstream(self):
        self.topology.add_component(ComponentInfo(name="a"))
        self.topology.add_component(ComponentInfo(name="b"))
        self.topology.add_component(ComponentInfo(name="c"))
        self.topology.add_component(ComponentInfo(name="d"))

        self.topology.add_causal_edge(CausalEdge(source="a", target="b"))
        self.topology.add_causal_edge(CausalEdge(source="b", target="c"))
        self.topology.add_causal_edge(CausalEdge(source="a", target="d"))

        assert self.topology.get_downstream("a") == ["b", "c", "d"]
        assert self.topology.get_upstream("c") == ["a", "b"]
        assert self.topology.get_direct_downstream("a") == ["b", "d"]
        assert self.topology.get_direct_upstream("c") == ["b"]

    def test_get_capacity(self):
        comp = ComponentInfo(name="svc_a", capacity=ResourceCapacity(cpu_cores=8.0))
        self.topology.add_component(comp)

        cap = self.topology.get_capacity("svc_a")
        assert cap.cpu_cores == 8.0

        # Non-existent component returns default
        cap_default = self.topology.get_capacity("unknown")
        assert cap_default.cpu_cores == 4.0

    def test_topological_order(self):
        self.topology.add_component(ComponentInfo(name="a"))
        self.topology.add_component(ComponentInfo(name="b"))
        self.topology.add_component(ComponentInfo(name="c"))

        self.topology.add_causal_edge(CausalEdge(source="a", target="b"))
        self.topology.add_causal_edge(CausalEdge(source="b", target="c"))

        order = self.topology.topological_order()
        assert order.index("a") < order.index("b")
        assert order.index("b") < order.index("c")
        assert set(order) == {"a", "b", "c"}

    def test_to_dict(self):
        self.topology.add_component(ComponentInfo(name="svc_a", instance_ids=["a1"]))
        self.topology.add_component(ComponentInfo(name="svc_b"))
        self.topology.add_causal_edge(CausalEdge(source="svc_a", target="svc_b"))

        d = self.topology.to_dict()
        assert "components" in d
        assert "causal_edges" in d
        assert "svc_a" in d["components"]
        assert len(d["causal_edges"]) == 1

    def test_all_instances(self):
        self.topology.add_component(ComponentInfo(name="svc_a", instance_ids=["a1", "a2"]))
        self.topology.add_component(ComponentInfo(name="svc_b", instance_ids=["b1"]))

        instances = self.topology.get_all_instances()
        assert set(instances) == {"a1", "a2", "b1"}


class TestSystemTopologyFromBundle:
    """Test SystemTopology.from_bundle with real configs."""

    def test_load_deployments(self, tmp_path):
        # Create deployment files
        deploy_dir = tmp_path / "deployments"
        deploy_dir.mkdir()

        deploy_data = {
            "service_name": "navigation_service",
            "version": "v42",
            "deployed_at_ns": 1000000000,
            "image": "nav:v42",
            "config_version": "cfg_123",
            "instances": [
                {"instance_id": "nav-1", "host": "host1"},
                {"instance_id": "nav-2", "host": "host2"},
            ],
        }
        (deploy_dir / "navigation_v42.json").write_text(json.dumps(deploy_data))

        # Config dir
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "robot_params.yaml").write_text("resources: {}")
        (config_dir / "inference.yaml").write_text("service_mesh: {}")

        topology = SystemTopology.from_bundle(tmp_path)

        assert "navigation_service" in topology.components
        comp = topology.components["navigation_service"]
        assert comp.deployment_version == "v42"
        assert comp.image_name == "nav:v42"
        assert comp.config_version == "cfg_123"
        assert set(comp.instance_ids) == {"nav-1", "nav-2"}

    def test_load_robot_params(self, tmp_path):
        # Create deployment
        deploy_dir = tmp_path / "deployments"
        deploy_dir.mkdir()
        (deploy_dir / "test.json").write_text(json.dumps({
            "service_name": "test_svc",
            "instances": [{"instance_id": "test-1"}],
        }))

        # Robot params with custom resources
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "robot_params.yaml").write_text(yaml.dump({
            "resources": {
                "test_svc": {
                    "cpu_cores": 8.0,
                    "memory_gb": 16.0,
                    "network_gbps": 10.0,
                },
                "default": {
                    "cpu_cores": 2.0,
                    "memory_gb": 4.0,
                }
            }
        }))
        (config_dir / "inference.yaml").write_text("service_mesh: {}")

        topology = SystemTopology.from_bundle(tmp_path)

        # test_svc should have custom resources
        assert topology.components["test_svc"].capacity.cpu_cores == 8.0
        assert topology.components["test_svc"].capacity.memory_gb == 16.0

    def test_load_inference_config(self, tmp_path):
        deploy_dir = tmp_path / "deployments"
        deploy_dir.mkdir()
        (deploy_dir / "test.json").write_text(json.dumps({
            "service_name": "mesh_svc",
            "instances": [{"instance_id": "mesh-1"}],
        }))

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "robot_params.yaml").write_text("resources: {}")
        (config_dir / "inference.yaml").write_text(yaml.dump({
            "service_mesh": {
                "mesh_svc": {
                    "hostname": "mesh-host",
                    "port": 50051,
                    "protocol": "grpc",
                    "exports": ["application_log", "metrics_export", "distributed_trace"],
                }
            }
        }))

        topology = SystemTopology.from_bundle(tmp_path)

        comp = topology.components["mesh_svc"]
        assert comp.hostname == "mesh-host"
        assert comp.port == 50051
        assert comp.protocol == "grpc"
        assert "distributed_trace" in comp.boundary_layers


class TestBuildTopologyFromTimeline:
    """Test build_topology_from_timeline function."""

    def test_infers_components_from_events(self):
        timeline = [
            {"source_type": "jsonl_log", "attributes": {"service": "svc_a", "instance": "a1"}},
            {"source_type": "otel_trace", "attributes": {"service": "svc_b", "instance": "b1"}},
            {"source_type": "csv_metrics", "attributes": {"service": "svc_a", "instance": "a2"}},
        ]

        topology = build_topology_from_timeline(timeline)

        assert "svc_a" in topology.components
        assert "svc_b" in topology.components
        assert set(topology.components["svc_a"].instance_ids) == {"a1", "a2"}
        assert topology.components["svc_b"].instance_ids == ["b1"]

    def test_infers_boundary_layers(self):
        timeline = [
            {"source_type": "jsonl_log", "attributes": {"service": "svc_a"}},
            {"source_type": "csv_metrics", "attributes": {"service": "svc_a"}},
        ]

        topology = build_topology_from_timeline(timeline)

        layers = topology.components["svc_a"].boundary_layers
        assert "application_log" in layers
        assert "metrics_export" in layers

    def test_infers_causal_edges_from_traces(self):
        timeline = [
            {"source_type": "otel_trace", "attributes": {"service.name": "svc_a", "peer.service": "svc_b"}},
            {"source_type": "otel_trace", "attributes": {"service.name": "svc_b", "peer.service": "svc_c"}},
        ]

        topology = build_topology_from_timeline(timeline)

        edge = topology.get_edge("svc_a", "svc_b")
        assert edge is not None
        assert edge.edge_type == "rpc"
        assert edge.confidence == 0.6  # Inferred has lower confidence

    def test_component_type_inference(self):
        assert _infer_component_type("otel_trace") == "service"
        assert _infer_component_type("jsonl_log") == "service"
        assert _infer_component_type("csv_metrics") == "monitored"
        assert _infer_component_type("deployment_json") == "deployment"
        assert _infer_component_type("unknown") == "unknown"

    def test_source_type_to_boundary_layer(self):
        assert _source_type_to_boundary_layer("jsonl_log") == "application_log"
        assert _source_type_to_boundary_layer("text_log") == "infrastructure_log"
        assert _source_type_to_boundary_layer("otel_trace") == "distributed_trace"
        assert _source_type_to_boundary_layer("mcap_recording") == "distributed_trace"
        assert _source_type_to_boundary_layer("csv_metrics") == "metrics_export"
        assert _source_type_to_boundary_layer("deployment_json") == "deployment_event"
        assert _source_type_to_boundary_layer("operator_note") == "config_state"
        assert _source_type_to_boundary_layer("unknown") == "application_log"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
