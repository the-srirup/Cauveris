"""
System Topology for Holographic Reconstruction.

Builds the causal graph of services, dependencies, and capacities from
incident bundle configuration files (deployment manifests, robot_params.yaml, etc.).
"""
from __future__ import annotations

import logging
import yaml
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ResourceCapacity:
    """Resource capacity for a component."""
    cpu_cores: float = 4.0
    memory_gb: float = 8.0
    network_gbps: float = 1.0
    max_rps: float = 1000.0  # max requests per second

    def to_dict(self) -> Dict[str, float]:
        return {
            "cpu_cores": self.cpu_cores,
            "memory_gb": self.memory_gb,
            "network_gbps": self.network_gbps,
            "max_rps": self.max_rps,
        }


@dataclass(slots=True)
class ComponentInfo:
    """
    Information about a service/component in the system.
    """
    name: str
    instance_ids: List[str] = field(default_factory=list)
    component_type: str = "service"  # service, database, queue, gateway, etc.

    # Resource capacity
    capacity: ResourceCapacity = field(default_factory=ResourceCapacity)

    # Observed boundary layers this component exports
    boundary_layers: List[str] = field(default_factory=lambda: ["application_log"])

    # Deployment metadata
    deployment_version: str = ""
    deployment_time_ns: int = 0
    image_name: str = ""
    config_version: str = ""

    # Network
    hostname: str = ""
    port: int = 0
    protocol: str = "grpc"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "instance_ids": self.instance_ids,
            "component_type": self.component_type,
            "capacity": self.capacity.to_dict(),
            "boundary_layers": self.boundary_layers,
            "deployment_version": self.deployment_version,
            "deployment_time_ns": self.deployment_time_ns,
            "image_name": self.image_name,
            "config_version": self.config_version,
            "hostname": self.hostname,
            "port": self.port,
            "protocol": self.protocol,
        }


@dataclass(slots=True)
class CausalEdge:
    """
    Directed causal dependency between components.

    Represents a known or inferred causal relationship where state
    changes in source propagate to target.
    """
    source: str
    target: str
    edge_type: str = "rpc"  # rpc, topic, db, cache, filesystem
    latency_ms: float = 5.0  # Expected propagation latency
    queue_depth: int = 0     # Typical queue depth
    confidence: float = 0.8  # Confidence in this edge (0-1)
    bidirectional: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0,1], got {self.confidence}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "edge_type": self.edge_type,
            "latency_ms": self.latency_ms,
            "queue_depth": self.queue_depth,
            "confidence": self.confidence,
            "bidirectional": self.bidirectional,
        }


class SystemTopology:
    """
    Complete system topology for holographic reconstruction.

    Contains components, causal edges, and resource capacities.
    Loaded from incident bundle configuration files.
    """

    def __init__(self):
        self.components: Dict[str, ComponentInfo] = {}
        self.causal_edges: List[CausalEdge] = []
        self._adjacency: Dict[str, Set[str]] = defaultdict(set)
        self._reverse_adjacency: Dict[str, Set[str]] = defaultdict(set)
        self._component_by_instance: Dict[str, str] = {}
        self._capacities: Dict[str, ResourceCapacity] = {}

    def add_component(self, component: ComponentInfo) -> None:
        """Add a component to the topology."""
        self.components[component.name] = component
        self._capacities[component.name] = component.capacity
        for instance in component.instance_ids:
            self._component_by_instance[instance] = component.name
        logger.debug(f"Added component: {component.name} with {len(component.instance_ids)} instances")

    def add_causal_edge(self, edge: CausalEdge) -> None:
        """Add a causal edge to the topology."""
        if edge.source not in self.components:
            logger.warning(f"Causal edge source '{edge.source}' not in components")
        if edge.target not in self.components:
            logger.warning(f"Causal edge target '{edge.target}' not in components")

        self.causal_edges.append(edge)
        self._adjacency[edge.source].add(edge.target)
        self._reverse_adjacency[edge.target].add(edge.source)

        if edge.bidirectional:
            self._adjacency[edge.target].add(edge.source)
            self._reverse_adjacency[edge.source].add(edge.target)

    def get_capacity(self, component: str) -> ResourceCapacity:
        """Get capacity for a component."""
        return self._capacities.get(component, ResourceCapacity())

    def has_path(self, source: str, target: str) -> bool:
        """Check if there's a directed path from source to target."""
        if source == target:
            return True
        visited = set()
        stack = [source]
        while stack:
            node = stack.pop()
            if node == target:
                return True
            if node in visited:
                continue
            visited.add(node)
            stack.extend(self._adjacency.get(node, []))
        return False

    def get_downstream(self, component: str) -> List[str]:
        """Get all downstream components (transitive)."""
        result = set()
        visited = set()
        stack = [component]
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            for neighbor in self._adjacency.get(node, []):
                result.add(neighbor)
                stack.append(neighbor)
        return sorted(result)

    def get_upstream(self, component: str) -> List[str]:
        """Get all upstream components (transitive)."""
        result = set()
        visited = set()
        stack = [component]
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            for neighbor in self._reverse_adjacency.get(node, []):
                result.add(neighbor)
                stack.append(neighbor)
        return sorted(result)

    def get_direct_downstream(self, component: str) -> List[str]:
        """Get immediate downstream neighbors."""
        return sorted(self._adjacency.get(component, []))

    def get_direct_upstream(self, component: str) -> List[str]:
        """Get immediate upstream neighbors."""
        return sorted(self._reverse_adjacency.get(component, []))

    def get_edge(self, source: str, target: str) -> Optional[CausalEdge]:
        """Get specific causal edge."""
        for edge in self.causal_edges:
            if edge.source == source and edge.target == target:
                return edge
        return None

    def get_all_instances(self) -> List[str]:
        """Get all instance IDs."""
        return list(self._component_by_instance.keys())

    def get_component_for_instance(self, instance_id: str) -> Optional[str]:
        """Get component name for an instance ID."""
        return self._component_by_instance.get(instance_id)

    def topological_order(self) -> List[str]:
        """Get topological ordering of components (for causal propagation)."""
        # Kahn's algorithm
        in_degree = {c: 0 for c in self.components}
        for edge in self.causal_edges:
            if edge.target in in_degree:
                in_degree[edge.target] += 1

        queue = [c for c, d in in_degree.items() if d == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            for neighbor in self._adjacency.get(node, []):
                if neighbor in in_degree:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        # Add any remaining (cycles)
        for node in in_degree:
            if node not in result:
                result.append(node)

        return result

    def to_dict(self) -> Dict[str, Any]:
        """Serialize topology to dictionary."""
        return {
            "components": {k: v.to_dict() for k, v in self.components.items()},
            "causal_edges": [e.to_dict() for e in self.causal_edges],
        }

    @classmethod
    def from_bundle(cls, bundle_path: Path) -> "SystemTopology":
        """
        Build SystemTopology from an incident bundle directory.

        Reads:
        - deployments/*.json - deployment manifests
        - config/robot_params.yaml - robot resource params
        - config/inference.yaml - inference service config
        - Manifest information from timeline events

        Args:
            bundle_path: Path to incident bundle directory.

        Returns:
            Populated SystemTopology instance.
        """
        topology = cls()
        bundle_path = Path(bundle_path)

        # 1. Load deployments
        topology._load_deployments(bundle_path)

        # 2. Load robot params (resource capacities)
        topology._load_robot_params(bundle_path)

        # 3. Load inference config (service mesh info)
        topology._load_inference_config(bundle_path)

        # 4. Infer causal edges from topology
        topology._infer_causal_edges()

        logger.info(f"Built topology with {len(topology.components)} components, {len(topology.causal_edges)} causal edges")
        return topology

    def _load_deployments(self, bundle_path: Path) -> None:
        """Load deployment manifests from bundle."""
        deploy_dir = bundle_path / "deployments"
        if not deploy_dir.exists():
            logger.warning(f"Deployments directory not found: {deploy_dir}")
            return

        for deploy_file in deploy_dir.glob("*.json"):
            try:
                import json
                with open(deploy_file, "r") as f:
                    deploy = json.load(f)

                component_name = deploy.get("service_name", deploy.get("name", deploy_file.stem))
                instances = deploy.get("instances", [])
                instance_ids = [inst.get("instance_id", f"{component_name}-{i}") for i, inst in enumerate(instances)]

                component = ComponentInfo(
                    name=component_name,
                    instance_ids=instance_ids,
                    component_type=deploy.get("type", "service"),
                    deployment_version=deploy.get("version", ""),
                    deployment_time_ns=int(deploy.get("deployed_at_ns", 0)),
                    image_name=deploy.get("image", ""),
                    config_version=deploy.get("config_version", ""),
                )
                self.add_component(component)

            except Exception as e:
                logger.error(f"Failed to parse deployment {deploy_file}: {e}")

    def _load_robot_params(self, bundle_path: Path) -> None:
        """Load resource capacities from robot_params.yaml."""
        params_file = bundle_path / "config" / "robot_params.yaml"
        if not params_file.exists():
            logger.debug(f"Robot params not found: {params_file}")
            return

        try:
            with open(params_file, "r") as f:
                params = yaml.safe_load(f)

            if not isinstance(params, dict):
                return

            # Resources section
            resources = params.get("resources", {})
            for component_name, res_config in resources.items():
                if component_name in self.components:
                    capacity = ResourceCapacity(
                        cpu_cores=float(res_config.get("cpu_cores", 4.0)),
                        memory_gb=float(res_config.get("memory_gb", 8.0)),
                        network_gbps=float(res_config.get("network_gbps", 1.0)),
                        max_rps=float(res_config.get("max_rps", 1000.0)),
                    )
                    self.components[component_name].capacity = capacity
                    self._capacities[component_name] = capacity

            # Default resources for components not explicitly listed
            default_res = resources.get("default", {})
            if default_res:
                default_capacity = ResourceCapacity(
                    cpu_cores=float(default_res.get("cpu_cores", 4.0)),
                    memory_gb=float(default_res.get("memory_gb", 8.0)),
                    network_gbps=float(default_res.get("network_gbps", 1.0)),
                    max_rps=float(default_res.get("max_rps", 1000.0)),
                )
                for component_name, component in self.components.items():
                    if component_name not in resources:
                        component.capacity = default_capacity
                        self._capacities[component_name] = default_capacity

        except Exception as e:
            logger.error(f"Failed to load robot params: {e}")

    def _load_inference_config(self, bundle_path: Path) -> None:
        """Load service mesh / inference config from inference.yaml."""
        inference_file = bundle_path / "config" / "inference.yaml"
        if not inference_file.exists():
            logger.debug(f"Inference config not found: {inference_file}")
            return

        try:
            with open(inference_file, "r") as f:
                config = yaml.safe_load(f)

            if not isinstance(config, dict):
                return

            # Service mesh configuration
            mesh = config.get("service_mesh", {})
            for service_name, svc_config in mesh.items():
                if service_name in self.components:
                    self.components[service_name].hostname = svc_config.get("hostname", "")
                    self.components[service_name].port = int(svc_config.get("port", 0))
                    self.components[service_name].protocol = svc_config.get("protocol", "grpc")

                    # Boundary layers this service exports
                    self.components[service_name].boundary_layers = svc_config.get("exports", [
                        "application_log",
                        "metrics_export",
                        "distributed_trace",
                    ])

        except Exception as e:
            logger.error(f"Failed to load inference config: {e}")

    def _infer_causal_edges(self) -> None:
        """
        Infer causal edges from deployment topology and service mesh.

        This builds the causal graph used by the holographic kernel.
        """
        # Standard service-to-service patterns
        service_pairs = [
            # (source, target, edge_type, latency_ms)
            ("api_gateway", "auth_service", "rpc", 2.0),
            ("api_gateway", "navigation_service", "rpc", 5.0),
            ("navigation_service", "planning_service", "rpc", 3.0),
            ("navigation_service", "localization_service", "rpc", 2.0),
            ("planning_service", "control_service", "rpc", 2.0),
            ("localization_service", "mapping_service", "rpc", 5.0),
            ("control_service", "actuator_interface", "rpc", 1.0),
            ("sensor_fusion", "localization_service", "topic", 10.0),
            ("sensor_fusion", "mapping_service", "topic", 10.0),
            ("detection_service", "navigation_service", "topic", 15.0),
        ]

        for src, tgt, edge_type, latency in service_pairs:
            if src in self.components and tgt in self.components:
                self.add_causal_edge(CausalEdge(
                    source=src,
                    target=tgt,
                    edge_type=edge_type,
                    latency_ms=latency,
                    confidence=0.8,
                ))

        # Add edges from observed deployments (deployment -> service)
        for comp_name, comp in self.components.items():
            if comp.deployment_time_ns > 0:
                # Deployment causally precedes all activity in that component
                # This is handled specially in the kernel, not as a regular edge
                pass


def build_topology_from_timeline(
    timeline_events: List[Dict[str, Any]],
    bundle_path: Optional[Path] = None,
) -> SystemTopology:
    """
    Alternative topology builder that infers components and edges from timeline events.

    Used when bundle config files are not available.
    """
    topology = SystemTopology()

    # Extract components from timeline events
    components_found: Dict[str, ComponentInfo] = {}
    edges_found: Set[Tuple[str, str]] = set()

    for event in timeline_events:
        source_type = event.get("source_type", "")
        attributes = event.get("attributes", {})

        # Identify component from attributes (check OTel standard attributes)
        component = attributes.get("service") or attributes.get("component") or attributes.get("service.name")
        instance = attributes.get("instance") or attributes.get("host") or "unknown"

        if component:
            if component not in components_found:
                components_found[component] = ComponentInfo(
                    name=component,
                    instance_ids=[],
                    component_type=_infer_component_type(source_type),
                )
            if instance and instance not in components_found[component].instance_ids:
                components_found[component].instance_ids.append(instance)

            # Add boundary layer
            layer = _source_type_to_boundary_layer(source_type)
            if layer not in components_found[component].boundary_layers:
                components_found[component].boundary_layers.append(layer)

        # Infer edges from OTel trace parent-child / peer service
        if source_type == "otel_trace":
            service_name = attributes.get("service.name")
            peer_service = attributes.get("peer.service")
            # Infer edge if we have a service and peer, regardless of parent_span
            if service_name and peer_service and service_name != peer_service:
                edges_found.add((service_name, peer_service))

    # Add inferred components
    for comp in components_found.values():
        topology.add_component(comp)

    # Add inferred edges
    for src, tgt in edges_found:
        if src in topology.components and tgt in topology.components:
            topology.add_causal_edge(CausalEdge(
                source=src,
                target=tgt,
                edge_type="rpc",
                latency_ms=5.0,
                confidence=0.6,  # Lower confidence for inferred edges
            ))

    return topology


def _infer_component_type(source_type: str) -> str:
    """Infer component type from source type."""
    if source_type in ("otel_trace", "jsonl_log"):
        return "service"
    elif source_type == "csv_metrics":
        return "monitored"
    elif source_type == "deployment_json":
        return "deployment"
    return "unknown"


def _source_type_to_boundary_layer(source_type: str) -> str:
    """Map source_type to boundary layer string."""
    mapping = {
        "jsonl_log": "application_log",
        "text_log": "infrastructure_log",
        "otel_trace": "distributed_trace",
        "mcap_recording": "distributed_trace",
        "csv_metrics": "metrics_export",
        "deployment_json": "deployment_event",
        "operator_note": "config_state",
    }
    return mapping.get(source_type, "application_log")
