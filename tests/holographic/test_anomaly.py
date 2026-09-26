"""Tests for holographic anomaly detection (Phase 4)."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from synthetic import SyntheticIncidentGenerator, IncidentType

from cauveris.holographic.anomaly import (
    HolographicAnomalyDetector,
    Anomaly,
    AnomalyReport,
    AnomalyType,
    AnomalySeverity,
    create_anomaly_detector,
    NORMAL_RANGES,
)
from cauveris.holographic.reconstruction import (
    HolographicReconstruction,
    ReconstructedServiceState,
    ReconstructedNetworkState,
    NetworkEdge,
    AmbiguityRegion,
)
from cauveris.holographic.topology import (
    SystemTopology,
    ComponentInfo,
    CausalEdge,
    ResourceCapacity,
)
from cauveris.holographic.heu import BoundaryLayer as HeuBoundaryLayer


def make_topology(n=3, component_type="service"):
    """Build a simple linear topology of n services."""
    topo = SystemTopology()
    for i in range(n):
        topo.components[f"svc_{i}"] = ComponentInfo(
            name=f"svc_{i}",
            instance_ids=[f"svc_{i}-1"],
            component_type=component_type,
            capacity=ResourceCapacity(cpu_cores=4.0, memory_gb=8.0),
            boundary_layers=[
                HeuBoundaryLayer.APPLICATION_LOG.value,
                HeuBoundaryLayer.METRICS_EXPORT.value,
            ],
        )
    for i in range(n - 1):
        topo.causal_edges.append(
            CausalEdge(
                source=f"svc_{i}",
                target=f"svc_{i+1}",
                edge_type="dependency",
                latency_ms=10.0,
                confidence=0.8,
            )
        )
    return topo


def make_recon(topology, **overrides):
    """Build a healthy reconstruction, with per-component overrides."""
    recon = HolographicReconstruction(
        incident_id="test",
        reconstruction_timestamp_ns=1000,
        time_window_ns=(0, 1000),
    )
    for name in topology.components:
        vals = overrides.get(name, {})
        recon.reconstructed_services[name] = ReconstructedServiceState(
            component_name=name,
            instance_id=f"{name}-1",
            **vals,
        )
    return recon


class TestAnomalyDataclasses:
    def test_anomaly_to_dict(self):
        a = Anomaly(
            anomaly_type=AnomalyType.CPU_SATURATION,
            severity=AnomalySeverity.HIGH,
            component="svc_0",
            dimension="cpu_usage",
            value=0.95,
            expected_range=(0.0, 0.7),
            confidence=0.9,
            description="test",
        )
        d = a.to_dict()
        assert d["type"] == "cpu_saturation"
        assert d["severity"] == "HIGH"
        assert d["expected_range"] == [0.0, 0.7]

    def test_report_filters_by_severity(self):
        report = AnomalyReport()
        report.anomalies = [
            Anomaly(AnomalyType.CPU_SATURATION, AnomalySeverity.CRITICAL, "a", "cpu_usage", 1.0, (0, 1), 1.0, ""),
            Anomaly(AnomalyType.ERROR_SPIKE, AnomalySeverity.HIGH, "b", "error_rate", 0.5, (0, 1), 1.0, ""),
            Anomaly(AnomalyType.MEMORY_EXHAUSTION, AnomalySeverity.LOW, "c", "memory_usage", 0.5, (0, 1), 1.0, ""),
        ]
        assert len(report.get_critical_anomalies()) == 1
        assert len(report.get_high_anomalies()) == 2

    def test_report_to_dict_shape(self):
        report = AnomalyReport(incident_id="inc", summary="s")
        report.severity_counts[AnomalySeverity.HIGH] = 2
        d = report.to_dict()
        assert d["incident_id"] == "inc"
        assert d["severity_counts"]["HIGH"] == 2


class TestThresholdDetection:
    def test_healthy_system_has_no_threshold_anomalies(self):
        topo = make_topology(3)
        recon = make_recon(topo)
        detector = create_anomaly_detector(topo)
        report = detector.detect(recon)
        threshold_anomalies = [
            a for a in report.anomalies
            if a.anomaly_type in (
                AnomalyType.CPU_SATURATION,
                AnomalyType.MEMORY_EXHAUSTION,
                AnomalyType.ERROR_SPIKE,
                AnomalyType.LATENCY_DEGRADATION,
            )
        ]
        assert threshold_anomalies == []

    def test_detects_cpu_saturation(self):
        topo = make_topology(3)
        recon = make_recon(topo, svc_1={"cpu_usage": 0.95})
        detector = create_anomaly_detector(topo)
        report = detector.detect(recon)
        cpu = [a for a in report.anomalies if a.anomaly_type == AnomalyType.CPU_SATURATION]
        assert len(cpu) >= 1
        assert any(a.component == "svc_1" for a in cpu)

    def test_detects_memory_exhaustion(self):
        topo = make_topology(3)
        recon = make_recon(topo, svc_2={"memory_usage": 0.97})
        report = create_anomaly_detector(topo).detect(recon)
        mem = [a for a in report.anomalies if a.anomaly_type == AnomalyType.MEMORY_EXHAUSTION]
        assert len(mem) >= 1

    def test_detects_error_spike(self):
        topo = make_topology(3)
        recon = make_recon(topo, svc_0={"error_rate": 0.6})
        report = create_anomaly_detector(topo).detect(recon)
        errs = [a for a in report.anomalies if a.anomaly_type == AnomalyType.ERROR_SPIKE]
        assert len(errs) >= 1
        assert errs[0].severity == AnomalySeverity.CRITICAL

    def test_severity_scales_with_magnitude(self):
        topo = make_topology(2)
        low = make_recon(topo, svc_0={"cpu_usage": 0.75})
        high = make_recon(topo, svc_0={"cpu_usage": 0.95})

        det = create_anomaly_detector(topo)
        low_anoms = [a for a in det.detect(low).anomalies if a.component == "svc_0"]
        high_anoms = [a for a in det.detect(high).anomalies if a.component == "svc_0"]

        if low_anoms and high_anoms:
            assert max(a.severity.value for a in high_anoms) >= max(
                a.severity.value for a in low_anoms
            )

    def test_baseline_comparison_flags_shift(self):
        topo = make_topology(2)
        baseline = make_recon(topo, svc_0={"cpu_usage": 0.2})
        current = make_recon(topo, svc_0={"cpu_usage": 0.6})
        report = create_anomaly_detector(topo).detect(current, baseline=baseline)
        shifts = [a for a in report.anomalies if a.anomaly_type == AnomalyType.SUDDEN_SHIFT]
        assert len(shifts) >= 1
        assert any(a.component == "svc_0" for a in shifts)

    def test_sensitivity_increases_detections(self):
        topo = make_topology(2)
        recon = make_recon(topo, svc_0={"cpu_usage": 0.75})
        low_sens = HolographicAnomalyDetector(topo, sensitivity=0.5).detect(recon)
        high_sens = HolographicAnomalyDetector(topo, sensitivity=2.0).detect(recon)
        assert len(high_sens.anomalies) >= len(low_sens.anomalies)


class TestSignatureDetection:
    def test_detects_throughput_collapse(self):
        topo = make_topology(2)
        recon = make_recon(topo, svc_0={"cpu_usage": 0.9, "error_rate": 0.5})
        report = create_anomaly_detector(topo).detect(recon)
        collapses = [
            a for a in report.anomalies
            if a.anomaly_type == AnomalyType.THROUGHPUT_COLLAPSE
        ]
        assert len(collapses) >= 1
        assert collapses[0].severity == AnomalySeverity.CRITICAL

    def test_detects_cascading_failure(self):
        topo = make_topology(4)
        recon = make_recon(
            topo,
            svc_0={"error_rate": 0.3},
            svc_1={"error_rate": 0.3},
            svc_2={"error_rate": 0.3},
        )
        report = create_anomaly_detector(topo).detect(recon)
        cascades = [
            a for a in report.anomalies
            if a.anomaly_type == AnomalyType.CASCADING_FAILURE
        ]
        assert len(cascades) >= 1

    def test_detects_resource_starvation_on_edge(self):
        topo = make_topology(2)
        # svc_0 starved, svc_1 idle
        recon = make_recon(topo, svc_0={"cpu_usage": 0.9}, svc_1={"cpu_usage": 0.1})
        report = create_anomaly_detector(topo).detect(recon)
        starv = [
            a for a in report.anomalies
            if a.anomaly_type == AnomalyType.RESOURCE_STARVATION
            and a.dimension == "starvation"
        ]
        assert len(starv) >= 1

    def test_detects_config_mismatch(self):
        topo = make_topology(2)
        recon = make_recon(
            topo,
            svc_0={"config_changed_recently": True, "error_rate": 0.2},
        )
        report = create_anomaly_detector(topo).detect(recon)
        mismatches = [
            a for a in report.anomalies if a.anomaly_type == AnomalyType.CONFIG_MISMATCH
        ]
        assert len(mismatches) >= 1

    def test_detects_network_congestion(self):
        topo = make_topology(2)
        recon = make_recon(topo)
        recon.reconstructed_network = ReconstructedNetworkState()
        recon.reconstructed_network.add_edge(
            "svc_0", "svc_1",
            NetworkEdge(source="svc_0", target="svc_1", latency_ms=800.0, loss_rate=0.15),
        )
        report = create_anomaly_detector(topo).detect(recon)
        net = [
            a for a in report.anomalies if a.anomaly_type == AnomalyType.NETWORK_CONGESTION
        ]
        assert len(net) >= 1

    def test_healthy_network_no_congestion(self):
        topo = make_topology(2)
        recon = make_recon(topo)
        recon.reconstructed_network = ReconstructedNetworkState()
        recon.reconstructed_network.add_edge(
            "svc_0", "svc_1",
            NetworkEdge(source="svc_0", target="svc_1", latency_ms=5.0, loss_rate=0.0),
        )
        report = create_anomaly_detector(topo).detect(recon)
        net = [
            a for a in report.anomalies if a.anomaly_type == AnomalyType.NETWORK_CONGESTION
        ]
        assert net == []


class TestStructuralDetection:
    def test_isolated_high_load_component(self):
        topo = SystemTopology()
        topo.components["orphan"] = ComponentInfo(
            name="orphan",
            instance_ids=["orphan-1"],
            component_type="service",
            capacity=ResourceCapacity(cpu_cores=2.0),
            boundary_layers=[HeuBoundaryLayer.APPLICATION_LOG.value],
        )
        recon = HolographicReconstruction(
            incident_id="t", reconstruction_timestamp_ns=0, time_window_ns=(0, 1)
        )
        recon.reconstructed_services["orphan"] = ReconstructedServiceState(
            component_name="orphan", instance_id="orphan-1", cpu_usage=0.9
        )
        report = create_anomaly_detector(topo).detect(recon)
        starv = [
            a for a in report.anomalies
            if a.dimension == "isolated_high_load"
        ]
        assert len(starv) >= 1

    def test_correlated_high_load_on_edge_flags_cascade(self):
        topo = make_topology(2)
        recon = make_recon(topo, svc_0={"cpu_usage": 0.9}, svc_1={"cpu_usage": 0.9})
        report = create_anomaly_detector(topo).detect(recon)
        cascades = [
            a for a in report.anomalies
            if a.anomaly_type == AnomalyType.CASCADING_FAILURE
        ]
        assert len(cascades) >= 1


class TestAmbiguityDetection:
    def test_wide_confidence_interval_flagged(self):
        topo = make_topology(2)
        recon = make_recon(topo)
        recon.ambiguity_regions.append(
            AmbiguityRegion(
                component="svc_0",
                time_range_ns=(0, 1_000_000_000),
                affected_dimensions=["cpu_usage", "memory_usage"],
                ambiguity_score=0.8,
                missing_layers=["network_flow", "distributed_trace"],
                description="Wide confidence interval due to missing boundary layers",
            )
        )
        report = create_anomaly_detector(topo).detect(recon)
        amb = [a for a in report.anomalies if a.dimension == "ambiguity"]
        assert len(amb) >= 1
        # ambiguity_score=0.8 > 0.75 triggers MEDIUM severity
        assert amb[0].severity == AnomalySeverity.MEDIUM


class TestReportAggregation:
    def test_component_scores_computed(self):
        topo = make_topology(3)
        recon = make_recon(topo, svc_1={"cpu_usage": 0.95, "error_rate": 0.5})
        report = create_anomaly_detector(topo).detect(recon)
        assert set(report.component_scores.keys()) == set(topo.components.keys())
        assert report.component_scores["svc_1"] > report.component_scores["svc_0"]

    def test_severity_counts_populated(self):
        topo = make_topology(2)
        recon = make_recon(topo, svc_0={"cpu_usage": 0.95})
        report = create_anomaly_detector(topo).detect(recon)
        assert sum(report.severity_counts.values()) == len(report.anomalies)

    def test_summary_mentions_components(self):
        topo = make_topology(2)
        recon = make_recon(topo, svc_0={"cpu_usage": 0.95})
        report = create_anomaly_detector(topo).detect(recon)
        assert "anomalies" in report.summary

    def test_healthy_summary(self):
        topo = make_topology(2)
        recon = make_recon(topo)
        report = create_anomaly_detector(topo).detect(recon)
        assert report.summary == "No anomalies detected."

    def test_incident_id_propagated(self):
        topo = make_topology(2)
        recon = make_recon(topo)
        recon.incident_id = "INC-42"
        report = create_anomaly_detector(topo).detect(recon)
        assert report.incident_id == "INC-42"


class TestAgainstSyntheticIncidents:
    @pytest.mark.parametrize("incident_type", [
        IncidentType.CPU_SPIKE_CASCADE,
        IncidentType.NETWORK_PARTITION,
        IncidentType.MEMORY_LEAK,
    ])
    def test_detects_anomalies_in_injected_incidents(self, incident_type):
        """Synthetic incidents have injected faults, so anomalies must appear."""
        generator = SyntheticIncidentGenerator(seed=42)
        incident = generator.generate(incident_type)

        from cauveris.holographic.integration import (
            HolographicAnalyzer,
            HolographicConfig,
        )

        analyzer = HolographicAnalyzer(
            HolographicConfig(enable_multiscale=False, enable_compression=False)
        )
        result = analyzer.analyze_incident(
            incident_id=incident.incident_id,
            timeline=incident.timeline,
            topology=incident.topology,
        )

        assert result.anomaly_report is not None
        assert len(result.anomaly_report.anomalies) > 0
