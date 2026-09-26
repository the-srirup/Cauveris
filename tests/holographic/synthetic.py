"""
Synthetic Incident Generator for Holographic Evidence Reconstruction Validation.

Generates incidents with known ground truth internal states to validate
reconstruction fidelity.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

from cauveris.holographic.topology import (
    SystemTopology,
    ComponentInfo,
    ResourceCapacity,
    CausalEdge,
)
from cauveris.holographic.heu import (
    HolographicEvidenceUnit,
    BoundaryLayer,
    convert_timeline_to_heus,
)
from cauveris.holographic.reconstruction import (
    HolographicReconstruction,
    ReconstructedServiceState,
)


class IncidentType(Enum):
    """Types of synthetic incidents to generate."""
    CPU_SPIKE_CASCADE = "cpu_spike_cascade"
    MEMORY_LEAK = "memory_leak"
    NETWORK_PARTITION = "network_partition"
    DEPLOYMENT_ROLLBACK = "deployment_rollback"
    DEPENDENCY_FAILURE = "dependency_failure"
    RESOURCE_CONTENTION = "resource_contention"
    SILENT_DATA_CORRUPTION = "silent_data_corruption"


@dataclass
class GroundTruthState:
    """Known ground truth internal state for validation."""
    component_states: Dict[str, Dict[str, float]]  # {comp: {dim: value}}
    network_states: Dict[Tuple[str, str], Dict[str, float]]  # {(src,dst): {latency, loss}}
    root_cause: str  # Component name
    root_cause_dimension: str  # Which dimension was root cause
    incident_type: IncidentType
    start_time_ns: int
    end_time_ns: int


@dataclass
class SyntheticIncident:
    """Complete synthetic incident with topology, timeline, and ground truth."""
    topology: SystemTopology
    timeline: List[Dict[str, Any]]
    ground_truth: GroundTruthState
    heus: List[HolographicEvidenceUnit]
    incident_id: str


class SyntheticIncidentGenerator:
    """
    Generates synthetic incidents with known ground truth.

    Each incident type models a specific failure mode with mathematically
    well-defined internal state evolution and boundary observations.
    """

    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)

    def generate(self, incident_type: IncidentType, **kwargs) -> SyntheticIncident:
        """Generate a synthetic incident of the specified type."""
        generators = {
            IncidentType.CPU_SPIKE_CASCADE: self._generate_cpu_spike_cascade,
            IncidentType.MEMORY_LEAK: self._generate_memory_leak,
            IncidentType.NETWORK_PARTITION: self._generate_network_partition,
            IncidentType.DEPLOYMENT_ROLLBACK: self._generate_deployment_rollback,
            IncidentType.DEPENDENCY_FAILURE: self._generate_dependency_failure,
            IncidentType.RESOURCE_CONTENTION: self._generate_resource_contention,
            IncidentType.SILENT_DATA_CORRUPTION: self._generate_silent_data_corruption,
        }

        if incident_type not in generators:
            raise ValueError(f"Unknown incident type: {incident_type}")

        return generators[incident_type](**kwargs)

    def _generate_cpu_spike_cascade(self, n_services: int = 4, **kwargs) -> SyntheticIncident:
        """CPU spike in one service cascading downstream."""
        # Build chain topology: svc_0 -> svc_1 -> svc_2 -> ...
        topology = SystemTopology()
        for i in range(n_services):
            topology.add_component(ComponentInfo(
                name=f"svc_{i}",
                component_type="service",
                capacity=ResourceCapacity(
                    cpu_cores=4.0 + i * 2.0,
                    memory_gb=8.0,
                    max_rps=5000,
                ),
                boundary_layers=[
                    "application_log",
                    "metrics_export",
                    "distributed_trace",
                ],
            ))
            if i > 0:
                topology.add_causal_edge(CausalEdge(
                    source=f"svc_{i-1}",
                    target=f"svc_{i}",
                    latency_ms=5.0,
                    edge_type="rpc",
                ))

        # Time parameters
        duration_ns = 60_000_000_000  # 60 seconds
        spike_start = 10_000_000_000  # 10s in
        spike_duration = 30_000_000_000  # 30s spike

        # Ground truth: svc_0 CPU spikes to 0.95, cascades to svc_1, svc_2, etc.
        component_states = {}
        for i in range(n_services):
            # Delayed cascade
            cascade_delay = i * 5_000_000_000  # 5s per hop

            cpu_pressure = 0.3  # baseline
            if i == 0:
                cpu_pressure = 0.95  # root cause
            elif spike_start + cascade_delay < duration_ns:
                cpu_pressure = 0.3 + 0.6 * np.exp(-(spike_start + cascade_delay - spike_start) / 10_000_000_000)

            component_states[f"svc_{i}"] = {
                "cpu_pressure": cpu_pressure,
                "memory_pressure": 0.4,
                "network_latency": 0.2 + i * 0.1,
                "error_rate": 0.01 + i * 0.05,
                "service_dependency": 0.5 + i * 0.1,
            }

        ground_truth = GroundTruthState(
            component_states=component_states,
            network_states={},
            root_cause="svc_0",
            root_cause_dimension="cpu_pressure",
            incident_type=IncidentType.CPU_SPIKE_CASCADE,
            start_time_ns=spike_start,
            end_time_ns=spike_start + spike_duration,
        )

        # Generate timeline events from ground truth
        timeline = self._ground_truth_to_timeline(topology, ground_truth, duration_ns)
        heus = convert_timeline_to_heus(timeline, {}, duration_ns)

        return SyntheticIncident(
            topology=topology,
            timeline=timeline,
            ground_truth=ground_truth,
            heus=heus,
            incident_id=f"SYNTH_CPU_SPIKE_{self.rng.integers(1000, 9999)}",
        )

    def _generate_memory_leak(self, **kwargs) -> SyntheticIncident:
        """Gradual memory leak in database service."""
        topology = SystemTopology()
        topology.add_component(ComponentInfo(
            name="api",
            component_type="gateway",
            capacity=ResourceCapacity(cpu_cores=8.0, memory_gb=16.0),
            boundary_layers=["application_log", "metrics_export", "distributed_trace"],
        ))
        topology.add_component(ComponentInfo(
            name="db",
            component_type="database",
            capacity=ResourceCapacity(cpu_cores=16.0, memory_gb=64.0),
            boundary_layers=["application_log", "metrics_export", "infrastructure_log"],
        ))
        topology.add_causal_edge(CausalEdge(
            source="api", target="db", latency_ms=2.0, edge_type="db",
        ))

        duration = 300_000_000_000  # 5 minutes
        leak_rate = 0.0025  # per second - faster leak to trigger thresholds

        component_states = {
            "api": {"cpu_pressure": 0.4, "memory_pressure": 0.6, "network_latency": 0.1, "error_rate": 0.05},
            "db": {
                "cpu_pressure": 0.3 + leak_rate * 300,  # gradually increases to ~1.05 -> clamped to 1.0
                "memory_pressure": 0.2 + leak_rate * 300,  # leak: 0.2 -> 0.95
                "network_latency": 0.1 + leak_rate * 100,
                "error_rate": 0.02,
            },
        }

        ground_truth = GroundTruthState(
            component_states=component_states,
            network_states={},
            root_cause="db",
            root_cause_dimension="memory_pressure",
            incident_type=IncidentType.MEMORY_LEAK,
            start_time_ns=0,
            end_time_ns=duration,
        )

        timeline = self._ground_truth_to_timeline(topology, ground_truth, duration)
        heus = convert_timeline_to_heus(timeline, {}, duration)

        return SyntheticIncident(
            topology=topology,
            timeline=timeline,
            ground_truth=ground_truth,
            heus=heus,
            incident_id=f"SYNTH_MEM_LEAK_{self.rng.integers(1000, 9999)}",
        )

    def _generate_network_partition(self, **kwargs) -> SyntheticIncident:
        """Network partition between two service groups."""
        topology = SystemTopology()
        # Group A
        topology.add_component(ComponentInfo(name="gateway", boundary_layers=["application_log", "metrics_export"]))
        topology.add_component(ComponentInfo(name="auth", boundary_layers=["application_log", "metrics_export"]))
        # Group B
        topology.add_component(ComponentInfo(name="payments", boundary_layers=["application_log", "metrics_export"]))
        topology.add_component(ComponentInfo(name="orders", boundary_layers=["application_log", "metrics_export"]))

        # Normal edges
        topology.add_causal_edge(CausalEdge(source="gateway", target="auth"))
        topology.add_causal_edge(CausalEdge(source="gateway", target="payments"))
        topology.add_causal_edge(CausalEdge(source="payments", target="orders"))

        # Partitioned edge (gateway -> orders directly fails)
        # This is implicit - the partition means no connectivity

        duration = 60_000_000_000
        partition_start = 20_000_000_000

        component_states = {
            "gateway": {"cpu_pressure": 0.5, "memory_pressure": 0.4, "network_latency": 0.8, "error_rate": 0.3},
            "auth": {"cpu_pressure": 0.3, "memory_pressure": 0.3, "network_latency": 0.2, "error_rate": 0.05},
            "payments": {"cpu_pressure": 0.4, "memory_pressure": 0.4, "network_latency": 0.7, "error_rate": 0.25},
            "orders": {"cpu_pressure": 0.3, "memory_pressure": 0.3, "network_latency": 0.1, "error_rate": 0.01},
        }

        network_states = {
            ("gateway", "auth"): {"latency": 5.0, "loss": 0.0},
            ("gateway", "payments"): {"latency": 8.0, "loss": 0.0},
            ("payments", "orders"): {"latency": 3.0, "loss": 0.0},
            ("gateway", "orders"): {"latency": 200.0, "loss": 0.9},  # Partitioned!
        }

        ground_truth = GroundTruthState(
            component_states=component_states,
            network_states=network_states,
            root_cause="gateway->orders",
            root_cause_dimension="network_latency",
            incident_type=IncidentType.NETWORK_PARTITION,
            start_time_ns=partition_start,
            end_time_ns=duration,
        )

        timeline = self._ground_truth_to_timeline(topology, ground_truth, duration)
        heus = convert_timeline_to_heus(timeline, {}, duration)

        return SyntheticIncident(
            topology=topology,
            timeline=timeline,
            ground_truth=ground_truth,
            heus=heus,
            incident_id=f"SYNTH_NET_PART_{self.rng.integers(1000, 9999)}",
        )

    def _generate_deployment_rollback(self, **kwargs) -> SyntheticIncident:
        """Bad deployment causing config regression."""
        topology = SystemTopology()
        topology.add_component(ComponentInfo(
            name="svc",
            capacity=ResourceCapacity(cpu_cores=4.0),
            boundary_layers=["application_log", "metrics_export", "distributed_trace", "deployment_event"],
        ))

        duration = 120_000_000_000  # 2 minutes
        deploy_time = 30_000_000_000

        # Ground truth: config change at deploy_time causes error spike
        component_states = {
            "svc": {
                "cpu_pressure": 0.5,
                "memory_pressure": 0.4,
                "config_change": 1.0,  # major config change
                "deployment_activity": 1.0,
                "error_rate": 0.4,  # bad deploy causes errors
            },
        }

        ground_truth = GroundTruthState(
            component_states=component_states,
            network_states={},
            root_cause="svc",
            root_cause_dimension="config_change",
            incident_type=IncidentType.DEPLOYMENT_ROLLBACK,
            start_time_ns=deploy_time,
            end_time_ns=duration,
        )

        timeline = self._ground_truth_to_timeline(topology, ground_truth, duration)
        heus = convert_timeline_to_heus(timeline, {}, duration)

        return SyntheticIncident(
            topology=topology,
            timeline=timeline,
            ground_truth=ground_truth,
            heus=heus,
            incident_id=f"SYNTH_DEPLOY_{self.rng.integers(1000, 9999)}",
        )

    def _generate_dependency_failure(self, **kwargs) -> SyntheticIncident:
        """Upstream dependency (cache/db) fails, cascading to consumers."""
        topology = SystemTopology()
        topology.add_component(ComponentInfo(name="cache", capacity=ResourceCapacity(), boundary_layers=["application_log", "infrastructure_log"]))
        topology.add_component(ComponentInfo(name="app", capacity=ResourceCapacity(), boundary_layers=["application_log", "metrics_export", "distributed_trace"]))
        topology.add_causal_edge(CausalEdge(source="app", target="cache", latency_ms=1.0, edge_type="cache"))

        duration = 60_000_000_000

        component_states = {
            "cache": {"cpu_pressure": 0.9, "memory_pressure": 0.8, "error_rate": 0.8, "network_latency": 0.9},
            "app": {"cpu_pressure": 0.6, "memory_pressure": 0.5, "error_rate": 0.4, "service_dependency": 0.9},
        }

        ground_truth = GroundTruthState(
            component_states=component_states,
            network_states={},
            root_cause="cache",
            root_cause_dimension="error_rate",
            incident_type=IncidentType.DEPENDENCY_FAILURE,
            start_time_ns=10_000_000_000,
            end_time_ns=duration,
        )

        timeline = self._ground_truth_to_timeline(topology, ground_truth, duration)
        heus = convert_timeline_to_heus(timeline, {}, duration)

        return SyntheticIncident(
            topology=topology,
            timeline=timeline,
            ground_truth=ground_truth,
            heus=heus,
            incident_id=f"SYNTH_DEP_FAIL_{self.rng.integers(1000, 9999)}",
        )

    def _generate_resource_contention(self, **kwargs) -> SyntheticIncident:
        """Multiple services contending for shared resource (DB connection pool)."""
        topology = SystemTopology()
        topology.add_component(ComponentInfo(name="app1", boundary_layers=["application_log", "metrics_export"]))
        topology.add_component(ComponentInfo(name="app2", boundary_layers=["application_log", "metrics_export"]))
        topology.add_component(ComponentInfo(name="db", boundary_layers=["application_log", "metrics_export", "infrastructure_log"]))
        topology.add_causal_edge(CausalEdge(source="app1", target="db", latency_ms=2.0))
        topology.add_causal_edge(CausalEdge(source="app2", target="db", latency_ms=2.0))

        duration = 60_000_000_000

        component_states = {
            "app1": {"cpu_pressure": 0.4, "memory_pressure": 0.3, "resource_contention": 0.8, "error_rate": 0.15},
            "app2": {"cpu_pressure": 0.5, "memory_pressure": 0.4, "resource_contention": 0.9, "error_rate": 0.25},
            "db": {"cpu_pressure": 0.7, "memory_pressure": 0.6, "resource_contention": 0.95, "network_latency": 0.6},
        }

        ground_truth = GroundTruthState(
            component_states=component_states,
            network_states={},
            root_cause="db",
            root_cause_dimension="resource_contention",
            incident_type=IncidentType.RESOURCE_CONTENTION,
            start_time_ns=15_000_000_000,
            end_time_ns=duration,
        )

        timeline = self._ground_truth_to_timeline(topology, ground_truth, duration)
        heus = convert_timeline_to_heus(timeline, {}, duration)

        return SyntheticIncident(
            topology=topology,
            timeline=timeline,
            ground_truth=ground_truth,
            heus=heus,
            incident_id=f"SYNTH_CONTEND_{self.rng.integers(1000, 9999)}",
        )

    def _generate_silent_data_corruption(self, **kwargs) -> SyntheticIncident:
        """Silent data corruption - no errors, wrong results. Hardest to detect."""
        topology = SystemTopology()
        topology.add_component(ComponentInfo(name="api", boundary_layers=["application_log", "metrics_export", "distributed_trace"]))
        topology.add_component(ComponentInfo(name="processor", boundary_layers=["application_log", "metrics_export"]))
        topology.add_component(ComponentInfo(name="storage", boundary_layers=["application_log", "infrastructure_log"]))
        topology.add_causal_edge(CausalEdge(source="api", target="processor"))
        topology.add_causal_edge(CausalEdge(source="processor", target="storage"))

        duration = 300_000_000_000  # 5 min - long duration for silent issue

        # Ground truth: all metrics look normal, but logical errors occur
        component_states = {
            "api": {"cpu_pressure": 0.3, "memory_pressure": 0.3, "error_rate": 0.01, "config_change": 0.0},
            "processor": {"cpu_pressure": 0.4, "memory_pressure": 0.3, "error_rate": 0.001, "config_change": 0.0},  # Very low error rate!
            "storage": {"cpu_pressure": 0.3, "memory_pressure": 0.4, "error_rate": 0.0},
        }

        ground_truth = GroundTruthState(
            component_states=component_states,
            network_states={},
            root_cause="processor",
            root_cause_dimension="config_change",  # Logic bug in config
            incident_type=IncidentType.SILENT_DATA_CORRUPTION,
            start_time_ns=0,
            end_time_ns=duration,
        )

        timeline = self._ground_truth_to_timeline(topology, ground_truth, duration)
        heus = convert_timeline_to_heus(timeline, {}, duration)

        return SyntheticIncident(
            topology=topology,
            timeline=timeline,
            ground_truth=ground_truth,
            heus=heus,
            incident_id=f"SYNTH_SILENT_{self.rng.integers(1000, 9999)}",
        )

    def _ground_truth_to_timeline(
        self,
        topology: SystemTopology,
        ground_truth: GroundTruthState,
        duration_ns: int,
    ) -> List[Dict[str, Any]]:
        """Convert ground truth internal state to observable timeline events."""
        timeline = []
        event_id = 0

        # Sample at intervals
        n_samples = 50
        time_points = np.linspace(0, duration_ns, n_samples, dtype=int)

        for t_ns in time_points:
            for comp_name, comp_state in ground_truth.component_states.items():
                # Determine if this component is affected at this time
                affected = t_ns >= ground_truth.start_time_ns and t_ns <= ground_truth.end_time_ns

                # Application log events
                if "application_log" in topology.components[comp_name].boundary_layers:
                    event_id += 1
                    log_event = self._create_log_event(
                        comp_name, comp_state, affected, t_ns, ground_truth
                    )
                    timeline.append(log_event)

                # Metrics export
                if "metrics_export" in topology.components[comp_name].boundary_layers:
                    event_id += 1
                    metric_event = self._create_metric_event(
                        comp_name, comp_state, affected, t_ns
                    )
                    timeline.append(metric_event)

                # Distributed trace
                if "distributed_trace" in topology.components[comp_name].boundary_layers:
                    event_id += 1
                    trace_event = self._create_trace_event(
                        comp_name, comp_state, affected, t_ns, topology
                    )
                    timeline.append(trace_event)

                # Infrastructure log
                if "infrastructure_log" in topology.components[comp_name].boundary_layers:
                    event_id += 1
                    infra_event = self._create_infra_event(
                        comp_name, comp_state, affected, t_ns
                    )
                    timeline.append(infra_event)

                # Deployment event
                if "deployment_event" in topology.components[comp_name].boundary_layers:
                    if ground_truth.incident_type == IncidentType.DEPLOYMENT_ROLLBACK:
                        event_id += 1
                        deploy_event = self._create_deploy_event(
                            comp_name, t_ns, ground_truth
                        )
                        timeline.append(deploy_event)

        return timeline

    def _create_log_event(self, comp: str, state: Dict, affected: bool, t_ns: int, gt: GroundTruthState) -> Dict:
        """Create application log event."""
        if not affected:
            msg = f"Normal operation in {comp}"
            attrs = {"cpu_usage": state.get("cpu_pressure", 0.3), "memory_usage": state.get("memory_pressure", 0.3)}
            status = "ok"
        else:
            # Generate realistic log based on root cause
            if comp == gt.root_cause and "cpu_pressure" in state and state["cpu_pressure"] > 0.8:
                msg = f"CRITICAL: CPU utilization at {int(state['cpu_pressure']*100)}%"
                attrs = {"cpu_usage": state["cpu_pressure"], "thread_count": int(state["cpu_pressure"]*100)}
                status = "critical"
            elif "error_rate" in state and state["error_rate"] > 0.2:
                msg = f"ERROR: High error rate detected"
                attrs = {"error_rate": state["error_rate"], "service": comp}
                status = "error"
            elif "memory_pressure" in state and state["memory_pressure"] > 0.7:
                msg = f"WARN: Memory pressure high"
                attrs = {"memory_usage": state["memory_pressure"]}
                status = "warning"
            else:
                msg = f"Operation in degraded state"
                attrs = {k: v for k, v in state.items() if v > 0.1}
                status = "warning"

        return {
            "event_id": str(t_ns),
            "timestamp_ns": t_ns,
            "source_type": "jsonl_log",
            "message": msg,
            "attributes": {"service": comp, **attrs},
            "status": status,
        }

    def _create_metric_event(self, comp: str, state: Dict, affected: bool, t_ns: int) -> Dict:
        """Create metrics export event."""
        return {
            "event_id": f"m_{t_ns}",
            "timestamp_ns": t_ns,
            "source_type": "csv_metrics",
            "message": "Prometheus scrape",
            "attributes": {
                "service": comp,
                "cpu_usage": state.get("cpu_pressure", 0.3),
                "memory_usage": state.get("memory_pressure", 0.3),
                "latency_p99": int(50 + state.get("network_latency", 0.1) * 1000),
                "error_rate": state.get("error_rate", 0.01),
            },
            "status": "ok" if not affected else "warning",
        }

    def _create_trace_event(self, comp: str, state: Dict, affected: bool, t_ns: int, topo: SystemTopology) -> Dict:
        """Create distributed trace event."""
        # Pick a random trace span
        trace_id = f"trace_{t_ns % 1000}"
        span_id = f"span_{t_ns % 100}"
        parent_span = f"span_{(t_ns - 1000000) % 100}" if t_ns > 10_000_000 else ""

        latency = int(5_000_000 + state.get("network_latency", 0.1) * 50_000_000)
        if comp != list(topo.components.keys())[0]:
            parent_span = f"span_{(t_ns - 1000000) % 100}"

        return {
            "event_id": f"t_{t_ns}",
            "timestamp_ns": t_ns,
            "source_type": "otel_trace",
            "message": "Trace span",
            "attributes": {
                "service": comp,
                "trace_id": trace_id,
                "span_id": span_id,
                "parent_span_id": parent_span,
                "duration_ns": latency,
                "status": "error" if affected and state.get("error_rate", 0) > 0.1 else "ok",
            },
            "status": "error" if affected and state.get("error_rate", 0) > 0.1 else "ok",
        }

    def _create_infra_event(self, comp: str, state: Dict, affected: bool, t_ns: int) -> Dict:
        """Create infrastructure log event."""
        return {
            "event_id": f"i_{t_ns}",
            "timestamp_ns": t_ns,
            "source_type": "syslog",
            "message": f"System metric for {comp}",
            "attributes": {
                "service": comp,
                "cpu_usage": state.get("cpu_pressure", 0.3),
                "memory_usage": state.get("memory_pressure", 0.3),
                "disk_io": np.random.uniform(0.1, 0.5),
            },
            "status": "ok" if not affected else "warning",
        }

    def _create_deploy_event(self, comp: str, t_ns: int, gt: GroundTruthState) -> Dict:
        """Create deployment event."""
        is_root = comp == gt.root_cause
        return {
            "event_id": f"d_{t_ns}",
            "timestamp_ns": t_ns if is_root else t_ns + 5_000_000_000,
            "source_type": "deployment_event",
            "message": f"{'Rollback' if is_root else 'Deploy'} of {comp}",
            "attributes": {
                "service": comp,
                "version": "v2.3.1" if is_root else "v2.3.0",
                "config_version": "config_42" if is_root else "config_41",
            },
            "status": "warning" if is_root else "ok",
        }


def generate_all_incident_types() -> List[SyntheticIncident]:
    """Generate one of each incident type for comprehensive testing."""
    generator = SyntheticIncidentGenerator()
    return [
        generator.generate(IncidentType.CPU_SPIKE_CASCADE),
        generator.generate(IncidentType.MEMORY_LEAK),
        generator.generate(IncidentType.NETWORK_PARTITION),
        generator.generate(IncidentType.DEPLOYMENT_ROLLBACK),
        generator.generate(IncidentType.DEPENDENCY_FAILURE),
        generator.generate(IncidentType.RESOURCE_CONTENTION),
        generator.generate(IncidentType.SILENT_DATA_CORRUPTION),
    ]


def validate_reconstruction(
    incident: SyntheticIncident,
    reconstruction: HolographicReconstruction,
    tolerance: float = 0.2,
) -> Dict[str, Any]:
    """
    Validate a reconstruction against ground truth.

    Returns:
        Dict with fidelity scores, root cause accuracy, per-component errors.
    """
    gt = incident.ground_truth
    results = {
        "incident_id": incident.incident_id,
        "incident_type": gt.incident_type.value,
        "root_cause_correct": False,
        "root_cause_dimension_correct": False,
        "per_component_fidelity": {},
        "overall_fidelity": 0.0,
        "detailed_errors": {},
    }

    # Check root cause identification
    recon_root = ""
    max_pressure = 0
    for svc, sstate in reconstruction.reconstructed_services.items():
        # Find the dimension with highest pressure
        for dim, val in sstate.__dict__.items():
            if val > max_pressure:
                max_pressure = val
                recon_root = f"{svc}/{dim}"

    gt_root = f"{gt.root_cause}/{gt.root_cause_dimension}"
    results["root_cause_correct"] = recon_root == gt_root
    results["reconstructed_root_cause"] = recon_root
    results["expected_root_cause"] = gt_root

    # Per-component fidelity (cosine similarity of state vectors)
    total_similarity = 0
    count = 0

    for comp, gt_state in gt.component_states.items():
        if comp not in reconstruction.reconstructed_services:
            results["per_component_fidelity"][comp] = 0.0
            continue

        recon_state = reconstruction.reconstructed_services[comp]

        # Build state vectors in same order
        dims = sorted(gt_state.keys())
        gt_vec = np.array([gt_state[d] for d in dims])
        recon_vec = np.array([getattr(recon_state, d, 0) for d in dims])

        # Cosine similarity
        norm_gt = np.linalg.norm(gt_vec)
        norm_recon = np.linalg.norm(recon_vec)
        if norm_gt > 0 and norm_recon > 0:
            sim = np.dot(gt_vec, recon_vec) / (norm_gt * norm_recon)
        else:
            sim = 0.0

        results["per_component_fidelity"][comp] = float(sim)
        total_similarity += sim
        count += 1

    # Network fidelity
    for (src, dst), gt_net in gt.network_states.items():
        if src in reconstruction.network_edges and dst in reconstruction.network_edges:
            edge = next((e for e in reconstruction.network_edges.values()
                        if e.source == src and e.target == dst), None)
            if edge:
                gt_lat = gt_net.get("latency", 0)
                gt_loss = gt_net.get("loss", 0)
                recon_lat = edge.latency
                recon_loss = edge.packet_loss

                lat_sim = 1 - min(abs(gt_lat - recon_lat) / max(gt_lat, 1), 1)
                loss_sim = 1 - min(abs(gt_loss - recon_loss), 1)
                net_sim = (lat_sim + loss_sim) / 2

                results["per_component_fidelity"][f"net_{src}_{dst}"] = float(net_sim)
                total_similarity += net_sim
                count += 1

    results["overall_fidelity"] = total_similarity / count if count > 0 else 0.0

    return results


if __name__ == "__main__":
    # Demo: Generate all incident types
    incidents = generate_all_incident_types()
    print(f"Generated {len(incidents)} synthetic incidents:")
    for inc in incidents:
        print(f"  {inc.incident_id}: {inc.ground_truth.incident_type.value}")
        print(f"    Root cause: {inc.ground_truth.root_cause}/{inc.ground_truth.root_cause_dimension}")
        print(f"    HEUs: {len(inc.heus)}")
        print(f"    Components: {list(inc.ground_truth.component_states.keys())}")