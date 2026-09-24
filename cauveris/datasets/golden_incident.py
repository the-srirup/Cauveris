"""
Golden incident dataset generator for CAU-0001.
"""
import json
import yaml
import hashlib
from pathlib import Path
from typing import Optional
from cauveris.schemas.incident import Incident, EvidenceItem
from cauveris.schemas.base import StatusLabel
from cauveris.config import get_settings
import logging

logger = logging.getLogger(__name__)


class GoldenIncidentGenerator:
    """Generates the golden CAU-0001 incident bundle."""

    def __init__(self, bundle_path: Optional[Path] = None):
        self.settings = get_settings()
        if bundle_path is not None:
            self.bundle_path = Path(bundle_path)
        else:
            self.bundle_path = Path("./incident-CAU-0001")
        self.bundle_path.mkdir(parents=True, exist_ok=True)

    def generate(self) -> Incident:
        """
        Generate the golden incident bundle on disk and return an Incident object.

        Returns:
            Incident representing the golden CAU-0001 incident
        """
        logger.info(f"Generating golden CAU-0001 incident at {self.bundle_path}")
        self._create_bundle_structure()
        manifest_data = self._write_manifest()
        self._write_readme()
        self._write_source_files()
        self._write_traces()
        self._write_logs()
        self._write_metrics()
        self._write_recordings()
        self._write_configs()
        self._write_deployments()
        self._write_observations()
        self._write_media()

        incident = self._build_incident_object(manifest_data)
        logger.info(f"Generated incident {incident.id} with {len(incident.evidence_items)} evidence items")
        return incident

    def _create_bundle_structure(self):
        """Create the directory structure for the incident bundle."""
        dirs = [
            "source/cloud-service",
            "source/robot-stack/src",
            "traces",
            "logs",
            "metrics",
            "recordings",
            "config",
            "deployments",
            "observations",
            "media",
        ]
        for dir_path in dirs:
            (self.bundle_path / dir_path).mkdir(parents=True, exist_ok=True)

    def _write_manifest(self) -> dict:
        """Write manifest.yaml."""
        manifest = {
            "incident_id": "CAU-0001",
            "title": "Warehouse robot emergency stop after deployment v42",
            "description": "Autonomous mobile robot consumes stale object detections from remote GPU inference service after deployment v42 increases dynamic batching window, causing P99 latency to exceed freshness budget.",
            "system_name": "warehouse-amr-01",
            "approximate_time": "2026-09-20T10:30:00Z",
            "source_repositories": [
                "https://github.com/example/inference-service",
                "https://github.com/example/robot-navigation"
            ],
            "commit_hash": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0",
            "required_evidence": [
                "manifest.yaml",
                "source/cloud-service/Dockerfile",
                "source/robot-stack/src/main.cpp",
                "traces/otel.json",
                "logs/cloud-service.jsonl",
                "logs/ros-nodes.jsonl",
                "metrics/gpu.csv",
                "metrics/network.csv",
                "recordings/robot_run.mcap",
                "config/inference.yaml",
                "config/robot_params.yaml",
                "deployments/events.json",
                "observations/operator_note.md",
                "media/incident.mp4"
            ]
        }
        manifest_path = self.bundle_path / "manifest.yaml"
        with open(manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(manifest, f, default_flow_style=False)
        logger.debug(f"Wrote manifest to {manifest_path}")
        return manifest

    def _write_readme(self):
        """Write README.md in incident bundle."""
        readme_content = """# Incident Bundle CAU-0001

## Incident Summary
Warehouse Autonomous Mobile Robot (AMR-01) performed an uncommanded emergency stop in aisle B at 10:30:00 UTC.

## System Context
- System: warehouse-amr-01
- Target deployment: v42 (applied 2026-09-20T08:00:00Z)
- Suspected components: cloud GPU inference service & robot navigation stack
"""
        (self.bundle_path / "README.md").write_text(readme_content, encoding='utf-8')

    def _write_source_files(self):
        """Write source files for cloud-service and robot-stack."""
        # Cloud service Dockerfile
        dockerfile_content = """FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04
RUN apt-get update && apt-get install -y python3-pip
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
CMD ["python3", "inference_server.py"]
"""
        (self.bundle_path / "source/cloud-service/Dockerfile").write_text(dockerfile_content, encoding='utf-8')

        # Cloud service inference_server.py
        inference_server_py = '''"""
Object Detection GPU Inference Service.
"""
import time
import yaml
from pathlib import Path

class InferenceServer:
    def __init__(self, config_path="config/inference.yaml"):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)
        self.batching_window_ms = self.config.get("dynamic_batching", {}).get("batching_window_ms", 200)
        self.max_batch_size = self.config.get("dynamic_batching", {}).get("max_batch_size", 8)

    def predict(self, frame_batch):
        # Simulates dynamic batch accumulation and GPU execution
        accum_delay = self.batching_window_ms / 1000.0
        gpu_exec_delay = 0.030 + (len(frame_batch) * 0.005)
        time.sleep(accum_delay + gpu_exec_delay)
        return [{"class": "obstacle", "bbox": [100, 100, 50, 50], "score": 0.95} for _ in frame_batch]

if __name__ == "__main__":
    server = InferenceServer()
    print(f"Inference server running. Dynamic batching window: {server.batching_window_ms}ms")
'''
        (self.bundle_path / "source/cloud-service/inference_server.py").write_text(inference_server_py, encoding='utf-8')

        # Robot stack main.cpp
        main_cpp = """#include <rclcpp/rclcpp.hpp>
#include <message_filters/subscriber.h>
#include <message_filters/time_synchronizer.h>
#include <std_msgs/msg/string.hpp>

int main(int argc, char ** argv) {
  rclcpp::init(argc, argv);
  auto node = std::make_shared<rclcpp::Node>("detection_listener");
  RCLCPP_INFO(node->get_logger(), "Detection listener started for warehouse AMR");
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
"""
        (self.bundle_path / "source/robot-stack/src/main.cpp").write_text(main_cpp, encoding='utf-8')

        # Robot stack detection_client.py
        detection_client_py = '''"""
ROS 2 Detection Client with QoS Subscription.
"""
class DetectionClient:
    def __init__(self, freshness_budget_ms=120):
        self.freshness_budget_ms = freshness_budget_ms
        self.qos_depth = 10
        self.keep_last = True

    def validate_freshness(self, timestamp_ms, current_time_ms):
        age_ms = current_time_ms - timestamp_ms
        if age_ms > self.freshness_budget_ms:
            return False, f"Detection stale by {age_ms - self.freshness_budget_ms}ms"
        return True, "Fresh"
'''
        (self.bundle_path / "source/robot-stack/src/detection_client.py").write_text(detection_client_py, encoding='utf-8')

    def _write_traces(self):
        """Write OpenTelemetry trace file."""
        otel_content = {
            "traceID": "0af7651916cd43dd8448eb211c80819c",
            "traceId": "0af7651916cd43dd8448eb211c80819c",
            "spans": [
                {
                    "traceID": "0af7651916cd43dd8448eb211c80819c",
                    "traceId": "0af7651916cd43dd8448eb211c80819c",
                    "spanID": "023e1fd95803323b",
                    "spanId": "023e1fd95803323b",
                    "name": "inference_request",
                    "timestamp": 1789900190100000000,
                    "duration": 155000000,
                    "attributes": {
                        "http.method": "POST",
                        "http.url": "/v1/models/objdet:predict",
                        "http.status_code": 200,
                        "batch.window_ms": 200,
                        "queue.wait_ms": 115
                    }
                },
                {
                    "traceID": "0af7651916cd43dd8448eb211c80819c",
                    "traceId": "0af7651916cd43dd8448eb211c80819c",
                    "spanID": "0456a2b3c4d5e6f7",
                    "spanId": "0456a2b3c4d5e6f7",
                    "name": "robot_control_loop",
                    "timestamp": 1789900190260000000,
                    "duration": 50000000,
                    "status": {
                        "code": 2,
                        "message": "Control deadline missed: detection latency exceeded freshness budget"
                    },
                    "attributes": {
                        "freshness_budget_ms": 120,
                        "observed_latency_ms": 155
                    }
                }
            ]
        }
        otel_path = self.bundle_path / "traces/otel.json"
        with open(otel_path, 'w', encoding='utf-8') as f:
            json.dump(otel_content, f, indent=2)
        logger.debug(f"Wrote OTel traces to {otel_path}")

    def _write_logs(self):
        """Write log files."""
        # Cloud service logs
        cloud_logs = [
            {"timestamp": "2026-09-20T10:29:50.000Z", "level": "INFO", "message": "Inference worker batch window set to 200ms by deployment v42"},
            {"timestamp": "2026-09-20T10:29:50.150Z", "level": "INFO", "message": "Batch filled with 4 frames, inference completed in 155ms"},
            {"timestamp": "2026-09-20T10:29:50.200Z", "level": "WARN", "message": "Queue depth increasing: 15 frames pending"},
        ]
        cloud_logs_path = self.bundle_path / "logs/cloud-service.jsonl"
        with open(cloud_logs_path, 'w', encoding='utf-8') as f:
            for entry in cloud_logs:
                f.write(json.dumps(entry) + "\n")

        # ROS nodes logs
        ros_logs = [
            {"timestamp": "2026-09-20T10:29:50.210Z", "node": "detection_listener", "level": "INFO", "message": "Received detection message from cloud inference"},
            {"timestamp": "2026-09-20T10:29:50.260Z", "node": "navigation_controller", "level": "ERROR", "message": "Transform lookup failed: stale detection age 155ms exceeds freshness budget 120ms"},
            {"timestamp": "2026-09-20T10:29:50.270Z", "node": "safety_monitor", "level": "CRITICAL", "message": "Emergency stop triggered: control deadline missed due to stale perception data"},
        ]
        ros_logs_path = self.bundle_path / "logs/ros-nodes.jsonl"
        with open(ros_logs_path, 'w', encoding='utf-8') as f:
            for entry in ros_logs:
                f.write(json.dumps(entry) + "\n")

        # System text log
        system_log_content = """2026-09-20T10:25:00Z systemd-timesyncd[412]: Synchronized to time server ntp.ubuntu.com (offset +0.001241s)
2026-09-20T10:28:00Z nvidia-smi[812]: GPU 0: NVIDIA A10G, Util 82%, Temp 68C, Power 142W / 150W
2026-09-20T10:29:50Z kernel: [10421.11] warehouse-amr-01 safety relay tripped
"""
        (self.bundle_path / "logs/system.log").write_text(system_log_content, encoding='utf-8')
        logger.debug("Wrote log files")

    def _write_metrics(self):
        """Write metric CSV files."""
        # GPU metrics
        gpu_csv = """timestamp,gpu_utilization,gpu_utilization_percent,memory_utilization,queue_depth,inference_latency_ms
2026-09-20T10:29:50.000Z,45,45,60,5,80
2026-09-20T10:29:50.100Z,50,50,65,8,95
2026-09-20T10:29:50.200Z,80,80,70,15,155
2026-09-20T10:29:50.300Z,90,90,75,25,190
"""
        (self.bundle_path / "metrics/gpu.csv").write_text(gpu_csv, encoding='utf-8')

        # Network metrics
        network_csv = """timestamp,latency_ms,packet_loss,jitter
2026-09-20T10:29:50.000Z,10,0.0,1
2026-09-20T10:29:50.100Z,12,0.0,2
2026-09-20T10:29:50.200Z,15,0.0,3
2026-09-20T10:29:50.300Z,18,0.0,4
"""
        (self.bundle_path / "metrics/network.csv").write_text(network_csv, encoding='utf-8')
        logger.debug("Wrote metric files")

    def _write_recordings(self):
        """Write a real, valid MCAP recording using the mcap library."""
        from mcap.writer import Writer

        mcap_path = self.bundle_path / "recordings/robot_run.mcap"
        with open(mcap_path, 'wb') as f:
            writer = Writer(f)
            writer.start()

            tf_schema = writer.register_schema(
                name="geometry_msgs/msg/TransformStamped",
                encoding="jsonschema",
                data=json.dumps({"type": "object", "properties": {"frame_id": {"type": "string"}, "child_frame_id": {"type": "string"}}}).encode('utf-8')
            )
            tf_chan = writer.register_channel(topic="/tf", message_encoding="json", schema_id=tf_schema)

            cmd_schema = writer.register_schema(
                name="geometry_msgs/msg/Twist",
                encoding="jsonschema",
                data=json.dumps({"type": "object", "properties": {"linear": {"type": "object"}, "angular": {"type": "object"}}}).encode('utf-8')
            )
            cmd_chan = writer.register_channel(topic="/cmd_vel", message_encoding="json", schema_id=cmd_schema)

            det_schema = writer.register_schema(
                name="vision_msgs/msg/Detection2DArray",
                encoding="jsonschema",
                data=json.dumps({"type": "object", "properties": {"detections": {"type": "array"}}}).encode('utf-8')
            )
            det_chan = writer.register_channel(topic="/detections", message_encoding="json", schema_id=det_schema)

            safety_schema = writer.register_schema(
                name="diagnostic_msgs/msg/DiagnosticStatus",
                encoding="jsonschema",
                data=json.dumps({"type": "object", "properties": {"level": {"type": "integer"}, "message": {"type": "string"}}}).encode('utf-8')
            )
            safety_chan = writer.register_channel(topic="/safety_status", message_encoding="json", schema_id=safety_schema)

            base_ns = 1789900190000000000

            # 1. Normal driving down aisle B
            writer.add_message(
                channel_id=tf_chan,
                log_time=base_ns,
                publish_time=base_ns,
                data=json.dumps({"frame_id": "odom", "child_frame_id": "base_link", "translation": {"x": 10.2, "y": 4.5, "z": 0.0}}).encode('utf-8')
            )
            writer.add_message(
                channel_id=cmd_chan,
                log_time=base_ns + 50000000,
                publish_time=base_ns + 50000000,
                data=json.dumps({"linear": {"x": 0.8, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": 0.0}}).encode('utf-8')
            )

            # 2. Delayed detection arriving with age 155ms (exceeding 120ms budget)
            det_time = base_ns + 210000000
            writer.add_message(
                channel_id=det_chan,
                log_time=det_time,
                publish_time=det_time,
                data=json.dumps({
                    "header": {"stamp_ns": base_ns + 55000000},
                    "detections": [{"id": "pallet_obstacle_1", "bbox": [120, 80, 45, 60], "score": 0.96}],
                    "inference_latency_ms": 155.0,
                    "age_ms": 155.0,
                    "freshness_budget_ms": 120.0,
                    "status": "STALE_DETECTION"
                }).encode('utf-8')
            )

            # 3. Transform lookup fails due to stale perception
            tf_fail_time = base_ns + 260000000
            writer.add_message(
                channel_id=tf_chan,
                log_time=tf_fail_time,
                publish_time=tf_fail_time,
                data=json.dumps({
                    "error": "ExtrapolationException: Transform lookup from base_link to odom failed: detection age 155ms exceeds buffer threshold",
                    "frame_id": "odom",
                    "child_frame_id": "base_link"
                }).encode('utf-8')
            )

            # 4. Emergency stop trigger & zero velocity command
            estop_time = base_ns + 270000000
            writer.add_message(
                channel_id=cmd_chan,
                log_time=estop_time,
                publish_time=estop_time,
                data=json.dumps({"linear": {"x": 0.0, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": 0.0}, "brake": True}).encode('utf-8')
            )
            writer.add_message(
                channel_id=safety_chan,
                log_time=estop_time,
                publish_time=estop_time,
                data=json.dumps({
                    "level": 2,
                    "name": "safety_monitor",
                    "message": "EMERGENCY_STOP_TRIGGERED: control deadline missed due to stale perception data (>120ms)",
                    "hardware_relay_tripped": True
                }).encode('utf-8')
            )

            writer.finish()

        logger.debug(f"Wrote valid MCAP recording with 6 messages to {mcap_path}")

    def _write_configs(self):
        """Write configuration files."""
        # Inference config
        inference_yaml = """model_name: objdet
version: v42
dynamic_batching:
  enabled: true
  max_batch_size: 8
  batching_window_ms: 200  # Increased from 100 in v42
  timeout_ms: 500
"""
        (self.bundle_path / "config/inference.yaml").write_text(inference_yaml, encoding='utf-8')

        # Robot params
        robot_params_yaml = """robot_name: warehouse-amr-01
safety:
  detection_freshness_budget_ms: 120
  control_loop_deadline_ms: 100
  transform_timeout_ms: 100
  emergency_stop_on_stale_data: true
  emergency_stop_on_transform_fail: true
perception:
  detection_topics:
    - object_detections
  required_detection_frequency_hz: 10
"""
        (self.bundle_path / "config/robot_params.yaml").write_text(robot_params_yaml, encoding='utf-8')
        logger.debug("Wrote config files")

    def _write_deployments(self):
        """Write deployment events."""
        events_content = {
            "deployment_id": "v42",
            "timestamp": "2026-09-20T08:00:00Z",
            "service": "inference-service",
            "image": "inference-service:v42",
            "changes": [
                {
                    "file": "config/inference.yaml",
                    "change": "batching_window_ms increased from 100 to 200",
                    "old_value": 100,
                    "new_value": 200
                }
            ],
            "config": {
                "dynamic_batching.window_ms": {"from": 100, "to": 200}
            },
            "author": "ml-team@example.com"
        }
        events_path = self.bundle_path / "deployments/events.json"
        with open(events_path, 'w', encoding='utf-8') as f:
            json.dump(events_content, f, indent=2)
        logger.debug(f"Wrote deployment events to {events_path}")

    def _write_observations(self):
        """Write operator notes."""
        note_content = """# Operator Incident Report

**Time**: 2026-09-20 10:30:00 UTC
**Location**: Aisle B, Warehouse 3
**Robot ID**: AMR-01
**Observation**: Robot came to a sudden halt in aisle B after completing a pick operation. No obstacles in path. Safety indicator showed emergency stop activated.

**Preliminary Analysis**:
- Checked robot logs: detection listener received stale object data (latency > 150ms)
- Network latency appeared normal (12-18ms)
- Inference service metrics showed increased queue depth
- Correlated with deployment v42 rolled out 2 hours prior

**Action Taken**: Manual override to clear emergency stop, robot resumed operation. Recommended rollback of inference service to v41.
"""
        note_path = self.bundle_path / "observations/operator_note.md"
        with open(note_path, 'w', encoding='utf-8') as f:
            f.write(note_content)
        logger.debug(f"Wrote operator note to {note_path}")

    def _write_media(self):
        """Write placeholder media file."""
        media_path = self.bundle_path / "media/incident.mp4"
        with open(media_path, 'wb') as f:
            f.write(b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom')
            f.write(b'\x00' * 512)
        logger.debug(f"Wrote placeholder media to {media_path}")

    def _build_incident_object(self, manifest: dict) -> Incident:
        """Build the Incident object from the generated bundle."""
        incident = Incident(
            id="CAU-0001",
            title=manifest.get("title", "Warehouse robot emergency stop after deployment v42"),
            description=manifest.get("description", "Autonomous mobile robot consumes stale object detections."),
            system_name=manifest.get("system_name", "warehouse-amr-01"),
            approximate_time=manifest.get("approximate_time", "2026-09-20T10:30:00Z"),
            source_repositories=manifest.get("source_repositories", []),
            commit_hash=manifest.get("commit_hash", ""),
            manifest=manifest,
            status=StatusLabel.OBSERVED
        )

        evidence_paths = [
            ("manifest.yaml", True),
            ("source/cloud-service/Dockerfile", True),
            ("source/cloud-service/inference_server.py", False),
            ("source/robot-stack/src/main.cpp", True),
            ("source/robot-stack/src/detection_client.py", False),
            ("traces/otel.json", True),
            ("logs/cloud-service.jsonl", True),
            ("logs/ros-nodes.jsonl", True),
            ("logs/system.log", False),
            ("metrics/gpu.csv", True),
            ("metrics/network.csv", True),
            ("recordings/robot_run.mcap", True),
            ("config/inference.yaml", True),
            ("config/robot_params.yaml", True),
            ("deployments/events.json", True),
            ("observations/operator_note.md", True),
            ("media/incident.mp4", True),
            ("README.md", False),
        ]

        for rel_path, required in evidence_paths:
            abs_path = self.bundle_path / rel_path
            if abs_path.exists():
                content = abs_path.read_bytes()
                checksum = hashlib.sha256(content).hexdigest()
                size_bytes = len(content)

                # Determine MIME type
                ext = abs_path.suffix.lower()
                if ext in ['.yaml', '.yml']:
                    mime_type = "text/yaml"
                elif ext == '.json':
                    mime_type = "application/json"
                elif ext == '.jsonl':
                    mime_type = "application/x-jsonlines"
                elif ext == '.csv':
                    mime_type = "text/csv"
                elif ext == '.md':
                    mime_type = "text/markdown"
                elif ext in ['.cpp', '.h', '.py', '.txt']:
                    mime_type = "text/plain"
                elif ext == '.mcap':
                    mime_type = "application/octet-stream"
                elif ext == '.mp4':
                    mime_type = "video/mp4"
                else:
                    mime_type = "application/octet-stream"

                evidence = EvidenceItem(
                    file_path=rel_path,
                    file_type=mime_type,
                    size_bytes=size_bytes,
                    checksum_sha256=checksum,
                    status=StatusLabel.OBSERVED,
                    is_required=required,
                )
                incident.evidence_items.append(evidence)
            else:
                logger.warning(f"Expected evidence file not found: {abs_path}")

        incident.update_counts()
        return incident
