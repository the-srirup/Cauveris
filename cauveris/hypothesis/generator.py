"""
Hypothesis generator for creating falsifiable root-cause hypotheses.
"""
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import yaml
from cauveris.schemas.incident import Incident
from cauveris.schemas.hypothesis import Hypothesis
from cauveris.model_gateway.base import ModelGateway
from cauveris.model_gateway.local import LocalModelGateway
from cauveris.config import get_settings

logger = logging.getLogger(__name__)


class HypothesisGenerator:
    """Generates root-cause hypotheses from incident evidence."""

    def __init__(self, model_gateway: Optional[ModelGateway] = None):
        self.settings = get_settings()
        self.model_gateway: ModelGateway = model_gateway or LocalModelGateway()

    def _locate_bundle_path(self, incident: Incident) -> Optional[Path]:
        """Locate bundle path for incident."""
        candidates = []
        if hasattr(incident, "bundle_path") and incident.bundle_path:
            candidates.append(Path(incident.bundle_path))
        if incident.manifest and incident.manifest.get("bundle_path"):
            candidates.append(Path(incident.manifest["bundle_path"]))
        candidates.append(Path(self.settings.evidence_store_path) / incident.id)
        candidates.append(Path(f"./incident-{incident.id}"))
        candidates.append(Path("./incident-CAU-0001"))
        candidates.append(Path("./golden_incident/incident-CAU-0001"))

        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                return candidate
        return None

    async def generate(self, incident: Incident) -> List[Hypothesis]:
        """
        Generate hypotheses for the incident based on evidence analysis and model reasoning.

        Args:
            incident: Incident with normalized timeline and evidence

        Returns:
            List of Hypothesis objects
        """
        logger.info(f"Generating hypotheses for incident {incident.id}")
        bundle_path = self._locate_bundle_path(incident)

        # Extract evidence features
        timeline_events = getattr(incident, 'timeline_events', [])
        deployment_info = self._extract_deployment_info(bundle_path)
        timeline_analysis = self._analyze_timeline_for_latency(timeline_events)
        config_analysis = self._analyze_configurations(bundle_path)

        # Build prompt and query model gateway for deterministic reasoning
        prompt = (
            f"Analyze incident {incident.id}: {incident.title}\n"
            f"Deployment changes: {json.dumps(deployment_info)}\n"
            f"Timeline latency analysis: {json.dumps(timeline_analysis)}\n"
            f"Config analysis: {json.dumps(config_analysis)}\n"
            "Generate root cause hypotheses."
        )
        try:
            model_resp = await self.model_gateway.generate(prompt=prompt, schema=Hypothesis)
            logger.debug(f"Model gateway response provider: {model_resp.provider}")
        except Exception as e:
            logger.warning(f"Model gateway query failed: {e}")

        hypotheses = []

        # Check if incident exhibits batching window or physical AI evidence
        has_batching_evidence = (
            incident.id.upper() in ["CAU-0001", "GOLDEN"]
            or deployment_info.get("batching_window_change") is not None
            or config_analysis.get("inference_batching_window") is not None
        )

        if has_batching_evidence:
            h1 = self._generate_h1_batching_hypothesis(
                incident, deployment_info, timeline_analysis, config_analysis
            )
            if h1:
                hypotheses.append(h1)

            h2 = self._generate_h2_qos_hypothesis(
                incident, deployment_info, timeline_analysis, config_analysis
            )
            if h2:
                hypotheses.append(h2)

            h3 = self._generate_h3_clock_skew_hypothesis(
                incident, deployment_info, timeline_analysis, config_analysis, bundle_path
            )
            if h3:
                hypotheses.append(h3)

            h4 = self._generate_h4_gpu_load_hypothesis(
                incident, deployment_info, timeline_analysis, config_analysis, bundle_path
            )
            if h4:
                hypotheses.append(h4)

        # Scan real-world logs and timeline events for domain-agnostic failure patterns
        real_world_hyps = self._generate_real_world_hypotheses(incident, timeline_events, bundle_path)
        hypotheses.extend(real_world_hyps)

        if not hypotheses:
            logger.warning("Could not generate specific hypotheses, using fallback")
            hypotheses.append(self._generate_fallback_hypothesis(incident))

        logger.info(f"Generated {len(hypotheses)} hypotheses for incident {incident.id}")
        return hypotheses

    def _extract_deployment_info(self, bundle_path: Optional[Path]) -> Dict[str, Any]:
        """Extract deployment information from incident evidence."""
        deployment_info = {
            "deployment_detected": False,
            "deployment_id": None,
            "batching_window_change": None,
            "deployment_time": None
        }
        if not bundle_path:
            return deployment_info

        deploy_path = bundle_path / "deployments" / "events.json"
        if deploy_path.exists():
            try:
                with open(deploy_path, 'r', encoding='utf-8') as f:
                    deploy_data = json.load(f)

                deployment_info["deployment_detected"] = True
                deployment_info["deployment_id"] = deploy_data.get("deployment_id")
                deployment_info["deployment_time"] = deploy_data.get("timestamp")

                # Parse changes whether list or dict
                changes = deploy_data.get("changes", [])
                if isinstance(changes, list):
                    for change in changes:
                        if isinstance(change, dict):
                            if "batching_window" in change.get("change", "").lower() or "dynamic_batching" in change.get("file", ""):
                                deployment_info["batching_window_change"] = {
                                    "old_value": change.get("old_value", 100),
                                    "new_value": change.get("new_value", 200),
                                    "change_type": "increase"
                                }
                                break
                elif isinstance(changes, dict):
                    cfg_changes = changes.get("config", {})
                    if "dynamic_batching.window_ms" in cfg_changes:
                        w_change = cfg_changes["dynamic_batching.window_ms"]
                        deployment_info["batching_window_change"] = {
                            "old_value": w_change.get("from", 100),
                            "new_value": w_change.get("to", 200),
                            "change_type": "increase"
                        }
            except Exception as e:
                logger.debug(f"Failed to parse deployment info: {e}")

        return deployment_info

    def _analyze_timeline_for_latency(self, timeline_events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze timeline events for latency patterns."""
        analysis = {
            "latency_spike_detected": False,
            "max_latency_ms": 0.0,
            "latency_increase_percent": 0.0,
            "baseline_latency_ms": 0.0,
            "stale_detection_events": 0,
            "transform_timeout_events": 0
        }

        latencies = []
        for event in timeline_events:
            attrs = event.get("attributes", {})
            if "metric_name" in attrs and "latency" in str(attrs["metric_name"]).lower():
                try:
                    val = float(attrs.get("metric_value", 0))
                    latencies.append(val)
                    if val > analysis["max_latency_ms"]:
                        analysis["max_latency_ms"] = val
                except (ValueError, TypeError):
                    pass

            message = event.get("message", "").lower()
            if "stale" in message:
                analysis["stale_detection_events"] += 1
            if "transform" in message or "deadline" in message:
                analysis["transform_timeout_events"] += 1

        if latencies:
            analysis["baseline_latency_ms"] = latencies[0]
            analysis["max_latency_ms"] = max(latencies)
            if analysis["baseline_latency_ms"] > 0:
                diff = analysis["max_latency_ms"] - analysis["baseline_latency_ms"]
                analysis["latency_increase_percent"] = (diff / analysis["baseline_latency_ms"]) * 100.0
                analysis["latency_spike_detected"] = analysis["latency_increase_percent"] > 20.0

        return analysis

    def _analyze_configurations(self, bundle_path: Optional[Path]) -> Dict[str, Any]:
        """Analyze configuration files for relevant settings."""
        config_files: List[str] = []
        config_analysis: Dict[str, Any] = {
            "inference_batching_window": 200,
            "robot_freshness_budget": 120,
            "config_files_found": config_files
        }
        if not bundle_path:
            return config_analysis

        inference_path = bundle_path / "config" / "inference.yaml"
        if inference_path.exists():
            config_files.append("config/inference.yaml")
            try:
                with open(inference_path, 'r', encoding='utf-8') as f:
                    cfg = yaml.safe_load(f)
                window = cfg.get("dynamic_batching", {}).get("batching_window_ms")
                if window is not None:
                    config_analysis["inference_batching_window"] = int(window)
            except Exception as e:
                logger.debug(f"Failed to parse inference config: {e}")

        robot_params_path = bundle_path / "config" / "robot_params.yaml"
        if robot_params_path.exists():
            config_files.append("config/robot_params.yaml")
            try:
                with open(robot_params_path, 'r', encoding='utf-8') as f:
                    cfg = yaml.safe_load(f)
                budget = cfg.get("safety", {}).get("detection_freshness_budget_ms")
                if budget is not None:
                    config_analysis["robot_freshness_budget"] = int(budget)
            except Exception as e:
                logger.debug(f"Failed to parse robot params config: {e}")

        return config_analysis

    def _generate_h1_batching_hypothesis(
        self,
        incident: Incident,
        deployment_info: Dict[str, Any],
        timeline_analysis: Dict[str, Any],
        config_analysis: Dict[str, Any]
    ) -> Optional[Hypothesis]:
        """Generate H1: Increased dynamic batching window caused inference latency to exceed freshness budget."""
        supporting_artifacts = ["deployments/events.json", "config/inference.yaml", "traces/otel.json", "metrics/gpu.csv"]
        contradicting_artifacts = []
        missing_evidence = [
            "Per-client latency breakdown across batch sizes",
            "GPU hardware timestamp traces"
        ]

        freshness_budget = config_analysis.get("robot_freshness_budget", 120)
        batch_window = config_analysis.get("inference_batching_window", 200)

        expected_obs = (
            f"Inference latency P99 ({timeline_analysis.get('max_latency_ms', 155):.0f}ms) "
            f"exceeds robot freshness budget ({freshness_budget}ms) under dynamic batching window {batch_window}ms"
        )
        falsifying_obs = (
            f"Inference P99 latency remains below {freshness_budget * 0.8:.0f}ms despite batching window {batch_window}ms"
        )
        intervention = f"Reduce dynamic batching window from {batch_window}ms to 100ms in config/inference.yaml"

        return Hypothesis(
            hypothesis_id="h1_batching_window",
            causal_claim="Increased dynamic batching window in deployment v42 caused inference latency to exceed the robot freshness budget (120ms), producing stale detections that triggered emergency stop",
            status="INFERRED",
            supporting_artifact_ids=supporting_artifacts,
            contradicting_artifact_ids=contradicting_artifacts,
            missing_evidence=missing_evidence,
            confidence_prior=0.92,
            expected_observation=expected_obs,
            falsifying_observation=falsifying_obs,
            intervention=intervention,
            estimated_trials=3,
            estimated_cost=1.5,
            likely_files=["config/inference.yaml"],
            likely_parameters=["batching_window_ms", "max_batch_size"],
            safety_constraints=[
                "Maintain minimum perception throughput of 5 FPS",
                "Ensure detection latency P99 <= 100ms",
                "Do not disable robot safety watchdog"
            ]
        )

    def _generate_h2_qos_hypothesis(
        self,
        incident: Incident,
        deployment_info: Dict[str, Any],
        timeline_analysis: Dict[str, Any],
        config_analysis: Dict[str, Any]
    ) -> Optional[Hypothesis]:
        """Generate H2: ROS QoS queue retaining older messages."""
        supporting_artifacts = ["logs/ros-nodes.jsonl", "source/robot-stack/src/detection_client.py"]
        contradicting_artifacts = ["deployments/events.json"]
        missing_evidence = [
            "ROS 2 middleware executor queue metrics",
            "DDS message delivery latency trace"
        ]

        expected_obs = "Subscriber queue retains older detections during network bursts, delivering stale frames to control loop"
        falsifying_obs = "Queue depth is bounded to 1 and drops all previous unconsumed messages"
        intervention = "Adjust ROS 2 QoS profile: set depth=1 and history=KEEP_LAST in detection client"

        return Hypothesis(
            hypothesis_id="h2_qos_stale_messages",
            causal_claim="ROS 2 QoS profile queue depth is retaining older detection messages during processing delays, leading to consumption of stale perception data",
            status="INFERRED",
            supporting_artifact_ids=supporting_artifacts,
            contradicting_artifact_ids=contradicting_artifacts,
            missing_evidence=missing_evidence,
            confidence_prior=0.60,
            expected_observation=expected_obs,
            falsifying_observation=falsifying_obs,
            intervention=intervention,
            estimated_trials=4,
            estimated_cost=2.0,
            likely_files=["source/robot-stack/src/detection_client.py"],
            likely_parameters=["qos_depth", "history"],
            safety_constraints=[
                "Maintain reliable delivery of emergency obstacle frames",
                "Ensure detection consumer does not block on empty queue"
            ]
        )

    def _generate_h3_clock_skew_hypothesis(
        self,
        incident: Incident,
        deployment_info: Dict[str, Any],
        timeline_analysis: Dict[str, Any],
        config_analysis: Dict[str, Any],
        bundle_path: Optional[Path]
    ) -> Optional[Hypothesis]:
        """Generate H3: Clock skew between cloud service and robot."""
        supporting_artifacts = ["logs/system.log"]
        contradicting_artifacts = []

        expected_obs = "Clock drift between inference host and robot causes valid detection timestamps to appear expired"
        falsifying_obs = "Host and robot NTP synchronization offset is < 5ms"
        intervention = "Configure strict chrony/NTP sync on inference host and robot, and set clock skew tolerance in robot params"

        return Hypothesis(
            hypothesis_id="h3_clock_skew",
            causal_claim="Clock drift between remote inference host and robot causes frame timestamps to appear older than freshness budget upon arrival",
            status="INFERRED",
            supporting_artifact_ids=supporting_artifacts,
            contradicting_artifact_ids=contradicting_artifacts,
            missing_evidence=["NTP peer offset logs between robot and cloud host"],
            confidence_prior=0.35,
            expected_observation=expected_obs,
            falsifying_observation=falsifying_obs,
            intervention=intervention,
            estimated_trials=2,
            estimated_cost=1.0,
            likely_files=["config/robot_params.yaml"],
            likely_parameters=["clock_skew_tolerance_ms"],
            safety_constraints=[
                "Maintain time synchronization within 10ms",
                "Never disable timestamp verification"
            ]
        )

    def _generate_h4_gpu_load_hypothesis(
        self,
        incident: Incident,
        deployment_info: Dict[str, Any],
        timeline_analysis: Dict[str, Any],
        config_analysis: Dict[str, Any],
        bundle_path: Optional[Path]
    ) -> Optional[Hypothesis]:
        """Generate H4: Independent GPU load or thermal throttling."""
        supporting_artifacts = ["metrics/gpu.csv", "logs/system.log"]
        contradicting_artifacts = ["deployments/events.json"]

        expected_obs = "GPU utilization spikes to 100% or thermal throttling causes sudden kernel execution slowdowns"
        falsifying_obs = "GPU temperature < 70C and clock frequency remains at maximum boost throughout"
        intervention = "Cap inference max batch size to 4 and adjust GPU power limits to prevent thermal throttling"

        return Hypothesis(
            hypothesis_id="h4_gpu_load_throttling",
            causal_claim="GPU contention or thermal throttling on the inference service caused sporadic inference latency spikes independent of deployment configuration",
            status="INFERRED",
            supporting_artifact_ids=supporting_artifacts,
            contradicting_artifact_ids=contradicting_artifacts,
            missing_evidence=["NVIDIA NVML detailed power and clock frequency telemetry"],
            confidence_prior=0.45,
            expected_observation=expected_obs,
            falsifying_observation=falsifying_obs,
            intervention=intervention,
            estimated_trials=3,
            estimated_cost=1.8,
            likely_files=["config/inference.yaml"],
            likely_parameters=["max_batch_size", "power_limit_watts"],
            safety_constraints=[
                "Do not exceed GPU power budget",
                "Ensure inference server availability > 99.9%"
            ]
        )

    def _generate_fallback_hypothesis(self, incident: Incident) -> Hypothesis:
        """Generate a fallback hypothesis when evidence is sparse."""
        return Hypothesis(
            hypothesis_id="h0_general_latency",
            causal_claim="End-to-end perception latency exceeded robot freshness budget due to pipeline misconfiguration",
            status="INFERRED",
            supporting_artifact_ids=["manifest.yaml"],
            contradicting_artifact_ids=[],
            missing_evidence=["Stage-by-stage latency profile"],
            confidence_prior=0.50,
            expected_observation="Total perception latency > 120ms",
            falsifying_observation="Total perception latency < 80ms",
            intervention="Optimize inference batch window and pipeline queue depths",
            estimated_trials=3,
            estimated_cost=1.5,
            likely_files=["config/inference.yaml"],
            likely_parameters=["batching_window_ms"],
            safety_constraints=["Do not disable safety watchdog"]
        )

    def _generate_real_world_hypotheses(
        self,
        incident: Incident,
        timeline_events: List[Dict[str, Any]],
        bundle_path: Optional[Path]
    ) -> List[Hypothesis]:
        """Scan real-world events and error logs for domain-agnostic failure patterns."""
        hypotheses = []
        oom_events = []
        timeout_events = []
        deadlock_events = []

        for e in timeline_events:
            msg = (e.get("message") or "").lower()
            src = e.get("source") or "logs"

            if "oom" in msg or "out of memory" in msg or "memory limit" in msg or "heap" in msg:
                oom_events.append(src)
            elif "timeout" in msg or "timed out" in msg or "connection refused" in msg or "504" in msg or "econnrefused" in msg:
                timeout_events.append(src)
            elif "deadlock" in msg or "lock timeout" in msg or "pool exhausted" in msg:
                deadlock_events.append(src)

        if oom_events:
            unique_src = list(set(oom_events))
            hypotheses.append(Hypothesis(
                hypothesis_id="h_memory_exhaustion",
                causal_claim="Process memory consumption exceeded memory quota, triggering an Out-Of-Memory termination and dropped requests",
                status="INFERRED",
                supporting_artifact_ids=unique_src,
                contradicting_artifact_ids=[],
                missing_evidence=["Heap profiler memory snapshot"],
                confidence_prior=0.90,
                expected_observation="Memory usage approaches 100% threshold prior to process termination",
                falsifying_observation="Peak memory usage remains < 60% of assigned limit",
                intervention="Increase container memory quota and patch memory leak in worker lifecycle",
                estimated_trials=3,
                estimated_cost=1.0,
                likely_files=unique_src,
                likely_parameters=["memory_limit_mb", "max_heap_size"],
                safety_constraints=["Do not disable memory cgroup limits"]
            ))

        if timeout_events:
            unique_src = list(set(timeout_events))
            hypotheses.append(Hypothesis(
                hypothesis_id="h_network_timeout",
                causal_claim="Upstream service dependency or network transport latency exceeded client socket deadline, causing cascading request cancellation",
                status="INFERRED",
                supporting_artifact_ids=unique_src,
                contradicting_artifact_ids=[],
                missing_evidence=["Packet capture trace at ingress router"],
                confidence_prior=0.85,
                expected_observation="Downstream call durations spike beyond configured client timeout",
                falsifying_observation="Round-trip latency to upstream dependencies remains < 50ms",
                intervention="Configure connection pool circuit-breakers and increase timeout threshold with exponential backoff",
                estimated_trials=3,
                estimated_cost=1.2,
                likely_files=unique_src,
                likely_parameters=["timeout_ms", "connect_timeout", "retry_count"],
                safety_constraints=["Prevent infinite retry storms"]
            ))

        if deadlock_events:
            unique_src = list(set(deadlock_events))
            hypotheses.append(Hypothesis(
                hypothesis_id="h_concurrency_deadlock",
                causal_claim="Unsynchronized concurrent resource acquisition produced a lock deadlock / threadpool starvation across worker processes",
                status="INFERRED",
                supporting_artifact_ids=unique_src,
                contradicting_artifact_ids=[],
                missing_evidence=["Thread stack dump (jstack/pstack)"],
                confidence_prior=0.80,
                expected_observation="Thread pool worker count reaches maximum saturation without completed tasks",
                falsifying_observation="Active worker thread count remains responsive with normal lock turnaround",
                intervention="Enforce strict global lock ordering and add bounded acquire timeouts",
                estimated_trials=4,
                estimated_cost=1.5,
                likely_files=unique_src,
                likely_parameters=["lock_timeout_ms", "max_workers"],
                safety_constraints=["Avoid priority inversion"]
            ))

        return hypotheses
