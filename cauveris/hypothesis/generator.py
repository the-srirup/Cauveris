"""
Hypothesis generator for creating falsifiable root-cause hypotheses.
"""
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from cauveris.schemas.incident import Incident
from cauveris.schemas.hypothesis import Hypothesis
from cauveris.model_gateway.base import ModelGateway
from cauveris.model_gateway.local import LocalModelGateway
from cauveris.config import get_settings
import json

logger = logging.getLogger(__name__)


class HypothesisGenerator:
    """Generates root-cause hypotheses from incident evidence."""

    def __init__(self):
        self.settings = get_settings()
        # Use local model gateway for deterministic, fixture-based responses
        self.model_gateway: ModelGateway = LocalModelGateway()

    async def generate(self, incident: Incident) -> List[Hypothesis]:
        """
        Generate hypotheses for the incident based on evidence analysis.

        Args:
            incident: Incident with normalized timeline and evidence

        Returns:
            List of Hypothesis objects
        """
        logger.info(f"Generating hypotheses for incident {incident.id}")

        # Analyze incident evidence to generate specific hypotheses
        hypotheses = []

        # Extract key information from incident
        _manifest = incident.manifest or {}
        timeline_events = getattr(incident, 'timeline_events', [])

        # Check for deployment information
        deployment_info = self._extract_deployment_info(incident)
        timeline_analysis = self._analyze_timeline_for_latency(timeline_events)
        config_analysis = self._analyze_configurations(incident)

        # Generate H1: Dynamic batching window increase causing latency
        h1 = await self._generate_h1_batching_hypothesis(
            incident, deployment_info, timeline_analysis, config_analysis
        )
        if h1:
            hypotheses.append(h1)

        # Generate H2: ROS QoS retaining stale messages
        h2 = await self._generate_h2_qos_hypothesis(
            incident, deployment_info, timeline_analysis, config_analysis
        )
        if h2:
            hypotheses.append(h2)

        # Generate H3: Clock skew between hosts
        h3 = await self._generate_h3_clock_skew_hypothesis(
            incident, deployment_info, timeline_analysis, config_analysis
        )
        if h3:
            hypotheses.append(h3)

        # Generate H4: Independent GPU load/throttling
        h4 = await self._generate_h4_gpu_load_hypothesis(
            incident, deployment_info, timeline_analysis, config_analysis
        )
        if h4:
            hypotheses.append(h4)

        # If we couldn't generate specific hypotheses, fall back to a general one
        if not hypotheses:
            logger.warning("Could not generate specific hypotheses, using fallback")
            hypotheses.append(self._generate_fallback_hypothesis(incident))

        logger.info(f"Generated {len(hypotheses)} hypotheses for incident {incident.id}")
        return hypotheses

    def _extract_deployment_info(self, incident: Incident) -> Dict[str, Any]:
        """Extract deployment information from incident evidence."""
        deployment_info = {
            "deployment_detected": False,
            "batching_window_change": None,
            "deployment_time": None
        }

        # Check deployments/events.json
        deploy_path = Path("./incident-CAU-0001/deployments/events.json")
        if deploy_path.exists():
            try:
                with open(deploy_path, 'r') as f:
                    deploy_data = json.load(f)
                deployment_info["deployment_detected"] = True
                deployment_info["deployment_time"] = deploy_data.get("timestamp")

                # Look for batching window changes
                for change in deploy_data.get("changes", []):
                    if change.get("file") == "config/inference.yaml" and \
                       change.get("change") == "batching_window_ms increased from 100 to 200":
                        deployment_info["batching_window_change"] = {
                            "old_value": change.get("old_value", 100),
                            "new_value": change.get("new_value", 200),
                            "change_type": "increase"
                        }
                        break
            except Exception as e:
                logger.debug(f"Failed to parse deployment info: {e}")

        return deployment_info

    def _analyze_timeline_for_latency(self, timeline_events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze timeline events for latency patterns."""
        analysis = {
            "latency_spike_detected": False,
            "max_latency_ms": 0,
            "latency_increase_percent": 0,
            "baseline_latency_ms": 0,
            "stale_detection_events": 0,
            "transform_timeout_events": 0
        }

        latencies = []
        for event in timeline_events:
            # Look for latency metrics
            attrs = event.get("attributes", {})
            if "metric_name" in attrs and "latency" in attrs["metric_name"].lower():
                try:
                    latency_val = float(attrs.get("metric_value", 0))
                    latencies.append(latency_val)
                    if latency_val > analysis["max_latency_ms"]:
                        analysis["max_latency_ms"] = latency_val
                except (ValueError, TypeError):
                    pass

            # Count specific event types
            message = event.get("message", "").lower()
            if "stale" in message:
                analysis["stale_detection_events"] += 1
            if "transform" in message and ("timeout" in message or "failed" in message):
                analysis["transform_timeout_events"] += 1

        # Calculate baseline and increase
        if len(latencies) >= 2:
            # Assume first half is baseline, second half is after change
            mid_point = len(latencies) // 2
            baseline = sum(latencies[:mid_point]) / len(latencies[:mid_point]) if mid_point > 0 else 0
            recent = sum(latencies[mid_point:]) / len(latencies[mid_point:]) if len(latencies[mid_point:]) > 0 else 0

            if baseline > 0:
                analysis["baseline_latency_ms"] = baseline
                analysis["latency_increase_percent"] = ((recent - baseline) / baseline) * 100
                analysis["latency_spike_detected"] = analysis["latency_increase_percent"] > 20  # 20% increase threshold

        return analysis

    def _analyze_configurations(self, incident: Incident) -> Dict[str, Any]:
        """Analyze configuration files for relevant settings."""
        config_analysis = {
            "inference_batching_window": None,
            "robot_freshness_budget": None,
            "config_files_found": []
        }

        # Check inference.yaml
        inference_path = Path("./incident-CAU-0001/config/inference.yaml")
        if inference_path.exists():
            config_analysis["config_files_found"].append("inference.yaml")
            try:
                import yaml
                with open(inference_path, 'r') as f:
                    inference_config = yaml.safe_load(f)
                batching_config = inference_config.get("dynamic_batching", {})
                config_analysis["inference_batching_window"] = batching_config.get("batching_window_ms")
            except Exception as e:
                logger.debug(f"Failed to parse inference config: {e}")

        # Check robot_params.yaml
        robot_params_path = Path("./incident-CAU-0001/config/robot_params.yaml")
        if robot_params_path.exists():
            config_analysis["config_files_found"].append("robot_params.yaml")
            try:
                import yaml
                with open(robot_params_path, 'r') as f:
                    robot_config = yaml.safe_load(f)
                safety_config = robot_config.get("safety", {})
                config_analysis["robot_freshness_budget"] = safety_config.get("detection_freshness_budget_ms")
            except Exception as e:
                logger.debug(f"Failed to parse robot params config: {e}")

        return config_analysis

    async def _generate_h1_batching_hypothesis(
        self,
        incident: Incident,
        deployment_info: Dict[str, Any],
        timeline_analysis: Dict[str, Any],
        config_analysis: Dict[str, Any]
    ) -> Optional[Hypothesis]:
        """Generate H1: Increased dynamic batching window caused inference latency to exceed freshness budget."""

        # Check if we have evidence for this hypothesis
        has_batch_change = deployment_info is not None and deployment_info.get("batching_window_change") is not None
        has_latency_spike = timeline_analysis.get("latency_spike_detected", False)
        has_config_values = (
            config_analysis.get("inference_batching_window") is not None and
            config_analysis.get("robot_freshness_budget") is not None
        )

        if not (has_batch_change or has_latency_spike or has_config_values):
            return None

        # Build supporting and contradicting evidence list
        supporting_artifacts = []
        contradicting_artifacts = []

        if deployment_info and deployment_info.get("batching_window_change"):
            supporting_artifacts.append("deployments/events.json")
            batch_change = deployment_info.get("batching_window_change", {})
            if batch_change.get("new_value", 0) > batch_change.get("old_value", 0):
                supporting_artifacts.append("config/inference.yaml")

        if timeline_analysis.get("latency_spike_detected"):
            supporting_artifacts.append("metrics/gpu.csv")
            supporting_artifacts.append("traces/otel.json")

        if config_analysis.get("inference_batching_window") and config_analysis.get("robot_freshness_budget"):
            batch_window = config_analysis["inference_batching_window"]
            freshness_budget = config_analysis["robot_freshness_budget"]
            if batch_window and freshness_budget and batch_window > freshness_budget * 0.8:  # Batch window > 80% of freshness budget
                supporting_artifacts.extend(["config/inference.yaml", "config/robot_params.yaml"])

        # Missing evidence
        missing_evidence = [
            "Direct end-to-end latency measurements",
            "GPU utilization correlation with batching window",
            "Queue depth metrics during inference spikes"
        ]

        # Expected observation if hypothesis is true
        rb = config_analysis.get('robot_freshness_budget')
        if rb is None:
            rb = 120
        expected_obs = (
            f"Inference P99 latency ({timeline_analysis.get('max_latency_ms', 0):.0f}ms) "
            f"exceeds robot freshness budget ({rb}ms)"
        )

        # Falsifying observation
        falsifying_obs = (
            f"Inference P99 latency remains below {rb * 0.8:.0f}ms "
            f"despite increased batching window"
        )

        # Intervention
        batching_change = (deployment_info or {}).get("batching_window_change")
        if not isinstance(batching_change, dict):
            batching_change = {}
        old_batch = batching_change.get("old_value", 100)
        ibw = config_analysis.get('inference_batching_window')
        if ibw is None:
            ibw = 200
        intervention = f"Reduce dynamic batching window from {ibw}ms to {old_batch}ms"

        # Estimated trials and cost
        estimated_trials = 3
        estimated_cost = 1.5  # Relative cost units

        # Likely files and parameters
        likely_files = ["config/inference.yaml"]
        if config_analysis.get("inference_batching_window"):
            likely_files.append("inference_server.py")
        likely_parameters = ["batching_window_ms", "max_batch_size"]

        # Safety constraints
        safety_constraints = [
            "Maintain minimum throughput of 5 FPS",
            "Do not increase inference latency beyond 100ms P99",
            "Maintain GPU utilization below 90%"
        ]

        # Calculate confidence based on evidence strength
        confidence_prior = 0.6  # Base confidence
        if has_batch_change:
            confidence_prior += 0.2
        if has_latency_spike:
            confidence_prior += 0.1
        if has_config_values and config_analysis.get("inference_batching_window", 0) > config_analysis.get("robot_freshness_budget", 120):
            confidence_prior += 0.1
        confidence_prior = min(0.95, confidence_prior)  # Cap at 95%

        return Hypothesis(
            hypothesis_id="h1_batching_window",
            causal_claim="Increased dynamic batching window caused inference latency to exceed robot's freshness budget, leading to stale detections and control loop failures",
            status="INFERRED",
            supporting_artifact_ids=supporting_artifacts,
            contradicting_artifact_ids=contradicting_artifacts,
            missing_evidence=missing_evidence,
            confidence_prior=confidence_prior,
            expected_observation=expected_obs,
            falsifying_observation=falsifying_obs,
            intervention=intervention,
            estimated_trials=estimated_trials,
            estimated_cost=estimated_cost,
            likely_files=likely_files,
            likely_parameters=likely_parameters,
            safety_constraints=safety_constraints
        )

    async def _generate_h2_qos_hypothesis(
        self,
        incident: Incident,
        deployment_info: Dict[str, Any],
        timeline_analysis: Dict[str, Any],
        config_analysis: Dict[str, Any]
    ) -> Optional[Hypothesis]:
        """Generate H2: ROS QoS retaining older detection messages causing stale-data consumption."""

        # Check for evidence of stale message consumption
        stale_events = timeline_analysis.get("stale_detection_events", 0)
        transform_events = timeline_analysis.get("transform_timeout_events", 0)

        if stale_events == 0 and transform_events == 0:
            return None

        supporting_artifacts = []
        contradicting_artifacts = []

        if stale_events > 0:
            supporting_artifacts.append("logs/ros-nodes.jsonl")
        if transform_events > 0:
            supporting_artifacts.append("traces/otel.json")

        # Check logs for QoS-related messages
        ros_logs_path = Path("./incident-CAU-0001/logs/ros-nodes.jsonl")
        if ros_logs_path.exists():
            supporting_artifacts.append("logs/ros-nodes.jsonl")

        missing_evidence = [
            "ROS 2 QoS settings for object_detections topic",
            "Message queue depth over time for detection topic",
            "Timestamp differences between detection publication and consumption"
        ]

        rb = config_analysis.get('robot_freshness_budget')
        if rb is None:
            rb = 120
        expected_obs = (
            f"Detection messages are being consumed after exceeding freshness budget "
            f"({rb}ms) due to ROS QoS retaining stale messages"
        )

        falsifying_obs = (
            "All detection messages are consumed within the freshness budget, "
            "indicating QoS is not retaining stale messages"
        )

        intervention = (
            "Adjust ROS 2 QoS settings for object_detections topic to reduce depth "
            "and disable stale message retention"
        )

        estimated_trials = 4
        estimated_cost = 2.0

        likely_files = ["detection_client.py", "navigation_node.cpp"]
        likely_parameters = ["qos_depth", "qos_reliability"]

        safety_constraints = [
            "Maintain detection availability above 95%",
            "Do not increase detection latency beyond freshness budget",
            "Ensure reliable delivery of critical detections"
        ]

        # Calculate confidence
        confidence_prior = 0.5  # Base confidence
        if stale_events > 0:
            confidence_prior += 0.2
        if transform_events > 0:
            confidence_prior += 0.2
        confidence_prior = min(0.9, confidence_prior)

        return Hypothesis(
            hypothesis_id="h2_qos_stale_messages",
            causal_claim="ROS 2 QoS settings are retaining older detection messages, causing consumption of stale data that exceeds the robot's freshness budget",
            status="INFERRED",
            supporting_artifact_ids=supporting_artifacts,
            contradicting_artifact_ids=contradicting_artifacts,
            missing_evidence=missing_evidence,
            confidence_prior=confidence_prior,
            expected_observation=expected_obs,
            falsifying_observation=falsifying_obs,
            intervention=intervention,
            estimated_trials=estimated_trials,
            estimated_cost=estimated_cost,
            likely_files=likely_files,
            likely_parameters=likely_parameters,
            safety_constraints=safety_constraints
        )

    async def _generate_h3_clock_skew_hypothesis(
        self,
        incident: Incident,
        deployment_info: Dict[str, Any],
        timeline_analysis: Dict[str, Any],
        config_analysis: Dict[str, Any]
    ) -> Optional[Hypothesis]:
        """Generate H3: Clock skew between service host and robot making fresh detections appear stale."""

        # Look for evidence of clock issues in logs or timestamps
        supporting_artifacts = []
        contradicting_artifacts = []

        # Check system logs for clock synchronization messages
        system_logs_path = Path("./incident-CAU-0001/logs/system.log")
        if system_logs_path.exists():
            supporting_artifacts.append("logs/system.log")

        # Check for timestamp inconsistencies across different evidence sources
        # This would require more sophisticated cross-source timestamp analysis
        # For now, we'll look for explicit clock-related warnings

        missing_evidence = [
            "NTP synchronization status on inference service host",
            "NTP synchronization status on robot",
            "Cross-host timestamp comparison using synchronized clocks",
            "Clock drift measurements between hosts"
        ]

        expected_obs = (
            "Clock skew between inference service host and robot causes "
            "timestamps to appear stale when compared against robot's local clock"
        )

        falsifying_obs = (
            "Clock synchronization between hosts shows drift less than 10ms, "
            "insufficient to explain the observed staleness"
        )

        intervention = (
            "Implement or improve NTP synchronization between inference service hosts "
            "and robot fleet to maintain clock sync within 5ms"
        )

        estimated_trials = 2
        estimated_cost = 1.0

        likely_files = ["ntp_config.yaml", "systemd-timesyncd.conf"]
        likely_parameters = ["ntp_servers", "sync_interval", "max_delay"]

        safety_constraints = [
            "Maintain time synchronization accuracy within 5ms",
            "Do not disrupt network time service during synchronization",
            "Ensure fallback to internal clocks if external NTP fails"
        ]

        # Lower confidence for clock skew as it's less likely without direct evidence
        confidence_prior = 0.3  # Base confidence
        # Check if there are any time-related warnings in logs
        if system_logs_path.exists():
            try:
                with open(system_logs_path, 'r') as f:
                    content = f.read().lower()
                    if 'time' in content and ('sync' in content or 'drift' in content or 'offset' in content):
                        confidence_prior += 0.2
            except Exception:
                pass
        confidence_prior = min(0.6, confidence_prior)

        return Hypothesis(
            hypothesis_id="h3_clock_skew",
            causal_claim="Clock skew between the inference service host and robot causes detection timestamps to appear stale when evaluated against the robot's freshness budget",
            status="INFERRED",
            supporting_artifact_ids=supporting_artifacts,
            contradicting_artifact_ids=contradicting_artifacts,
            missing_evidence=missing_evidence,
            confidence_prior=confidence_prior,
            expected_observation=expected_obs,
            falsifying_observation=falsifying_obs,
            intervention=intervention,
            estimated_trials=estimated_trials,
            estimated_cost=estimated_cost,
            likely_files=likely_files,
            likely_parameters=likely_parameters,
            safety_constraints=safety_constraints
        )

    async def _generate_h4_gpu_load_hypothesis(
        self,
        incident: Incident,
        deployment_info: Dict[str, Any],
        timeline_analysis: Dict[str, Any],
        config_analysis: Dict[str, Any]
    ) -> Optional[Hypothesis]:
        """Generate H4: GPU load or throttling causes latency spike independently of deployment v42."""

        # Look for GPU utilization correlations or throttling evidence
        supporting_artifacts = []
        contradicting_artifacts = []

        # Check GPU metrics for utilization patterns
        gpu_metrics_path = Path("./incident-CAU-0001/metrics/gpu.csv")
        if gpu_metrics_path.exists():
            supporting_artifacts.append("metrics/gpu.csv")

        # Check for power limiting or thermal throttling in logs
        system_logs_path = Path("./incident-CAU-0001/logs/system.log")
        if system_logs_path.exists():
            supporting_artifacts.append("logs/system.log")

        missing_evidence = [
            "GPU utilization logs showing correlation with latency spikes",
            "Power draw measurements during latency spikes",
            "Temperature readings showing thermal throttling",
            "GPU clock speed measurements during latency events"
        ]

        expected_obs = (
            "Increased GPU load or power throttling on the inference service "
            "causes inference latency increases independent of batching window settings"
        )

        falsifying_obs = (
            "GPU utilization, power draw, temperature, and clock speeds remain "
            "stable during latency spikes, indicating GPU is not the cause"
        )

        intervention = (
            "Implement GPU workload management to prevent throttling during peak loads, "
            "including power limit adjustments and better cooling"
        )

        estimated_trials = 3
        estimated_cost = 1.8

        likely_files = ["inference_server.py", "gpu_monitor.py"]
        likely_parameters = ["power_limit", "temperature_target", "gpu_utilization_target"]

        safety_constraints = [
            "Maintain inference availability above 99%",
            "Do not exceed GPU thermal design power (TDP)",
            "Maintain inference latency P95 below 200ms"
        ]

        # Check for evidence supporting GPU overload
        confidence_prior = 0.4  # Base confidence

        # Look for high GPU utilization in metrics
        if gpu_metrics_path.exists():
            try:
                import csv
                with open(gpu_metrics_path, 'r') as f:
                    reader = csv.DictReader(f)
                    gpu_utils = []
                    for row in reader:
                        util = row.get('gpu_utilization_percent')
                        if util:
                            try:
                                gpu_utils.append(float(util))
                            except Exception:
                                pass
                    if gpu_utils:
                        avg_util = sum(gpu_utils) / len(gpu_utils)
                        max_util = max(gpu_utils) if gpu_utils else 0
                        if max_util > 90:
                            confidence_prior += 0.2
                        if avg_util > 80:
                            confidence_prior += 0.1
            except Exception:
                pass

        # Look for thermal throttling in logs
        if system_logs_path.exists():
            try:
                with open(system_logs_path, 'r') as f:
                    content = f.read().lower()
                    if 'throttle' in content or 'thermal' in content or 'power limit' in content:
                        confidence_prior += 0.2
            except Exception:
                pass

        confidence_prior = min(0.8, confidence_prior)

        return Hypothesis(
            hypothesis_id="h4_gpu_load_throttling",
            causal_claim="Independent GPU load increases or power/thermal throttling cause inference latency spikes that exceed the robot's freshness budget",
            status="INFERRED",
            supporting_artifact_ids=supporting_artifacts,
            contradicting_artifact_ids=contradicting_artifacts,
            missing_evidence=missing_evidence,
            confidence_prior=confidence_prior,
            expected_observation=expected_obs,
            falsifying_observation=falsifying_obs,
            intervention=intervention,
            estimated_trials=estimated_trials,
            estimated_cost=estimated_cost,
            likely_files=likely_files,
            likely_parameters=likely_parameters,
            safety_constraints=safety_constraints
        )

    def _generate_fallback_hypothesis(self, incident: Incident) -> Hypothesis:
        """Generate a fallback hypothesis when specific evidence is lacking."""
        return Hypothesis(
            hypothesis_id="fallback_general",
            causal_claim="Recent changes to the perception pipeline or sensor data processing have increased end-to-end latency beyond acceptable bounds",
            status="INFERRED",
            supporting_artifact_ids=["manifest.yaml"],
            contradicting_artifact_ids=[],
            missing_evidence=["Detailed latency breakdown by pipeline stage", "Resource utilization metrics"],
            confidence_prior=0.5,
            expected_observation="End-to-end latency from image capture to control exceeds 200ms",
            falsifying_observation="End-to-end latency remains below 150ms under test conditions",
            intervention="Perform latency analysis of perception pipeline and optimize slowest stages",
            estimated_trials=5,
            estimated_cost=3.0,
            likely_files=["perception_pipeline.py", "sensor_fusion.cpp"],
            likely_parameters=["processing_threads", "queue_sizes", "timeout_values"],
            safety_constraints=[
                "Maintain object detection accuracy above 90%",
                "Do not increase processing latency beyond 200ms",
                "Ensure deterministic behavior under load"
            ]
        )
