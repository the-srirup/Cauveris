"""
Golden incident dataset generator for CAU-0001.
"""
import json
import yaml
import hashlib
from pathlib import Path
from cauveris.schemas.incident import Incident, EvidenceItem
from cauveris.config import get_settings
import logging

logger = logging.getLogger(__name__)


class GoldenIncidentGenerator:
    """Generates the golden CAU-0001 incident bundle."""

    def __init__(self):
        self.settings = get_settings()
        self.bundle_path = Path("./incident-CAU-0001")
        self.bundle_path.mkdir(parents=True, exist_ok=True)

    def generate(self) -> Incident:
        """
        Generate the golden incident bundle on disk and return an Incident object.

        Returns:
            Incident representing the golden CAU-0001 incident
        """
        logger.info("Generating golden CAU-0001 incident")
        self._create_bundle_structure()
        self._write_manifest()
        self._write_source_files()
        self._write_traces()
        self._write_logs()
        self._write_metrics()
        self._write_recordings()
        self._write_configs()
        self._write_deployments()
        self._write_observations()
        self._write_media()

        incident = self._build_incident_object()
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

    def _write_manifest(self):
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
        with open(manifest_path, 'w') as f:
            yaml.dump(manifest, f, default_flow_style=False)
        logger.debug(f"Wrote manifest to {manifest_path}")

    def _write_source_files(self):
        """Write placeholder source files."""
        # Cloud service Dockerfile
        dockerfile_content = """FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04
RUN apt-get update && apt-get install -y python3-pip
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
CMD ["python3", "inference_server.py"]
"""
        (self.bundle_path / "source/cloud-service/Dockerfile").write_text(dockerfile_content)

        # Robot stack main.cpp
        main_cpp = """#include <rclcpp/rclcpp.hpp>
#include <message_filters/subscriber.h>
#include <message_filters/time_synchronizer.h>
#include <std_msgs/Header.h>

int main(int argc, char ** argv) {
  rclcpp::init(argc, argv);
  auto node = std::make_shared<rclcpp::Node>("detection_listener");
  // Simplified detection listener
  RCLCPP_INFO(node->get_logger(), "Detection listener started");
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
"""
        (self.bundle_path / "source/robot-stack/src/main.cpp").write_text(main_cpp)

    def _write_traces(self):
        """Write OpenTelemetry trace file."""
        otel_content = {
            "traceID": "0af7651916cd43dd8448eb211c80819c",
            "spans": [
                {
                    "traceId": "0af7651916cd43dd8448eb211c80819c",
                    "spanId": "023e1fd95803323b",
                    "name": "inference_request",
                    "timestamp": 1726823400000000000,  # nanoseconds
                    "duration": 150000000,  # 150ms
                    "attributes": {
                        "http.method": "POST",
                        "http.url": "/v1/models/objdet:predict",
                        "http.status_code": 200
                    }
                },
                {
                    "traceId": "0af7651916cd43dd8448eb211c80819c",
                    "spanId": "0456a2b3c4d5e6f7",
                    "name": "robot_control_loop",
                    "timestamp": 1726823400200000000,  # 200ms later
                    "duration": 50000000,  # 50ms
                    "status": {
                        "code": 2,  # ERROR
                        "message": "Control deadline missed"
                    }
                }
            ]
        }
        otel_path = self.bundle_path / "traces/otel.json"
        with open(otel_path, 'w') as f:
            json.dump(otel_content, f, indent=2)
        logger.debug(f"Wrote OTel traces to {otel_path}")

    def _write_logs(self):
        """Write log files."""
        # Cloud service logs
        cloud_logs = [
            {"timestamp": "2026-09-20T10:29:50Z", "level": "INFO", "message": "Received inference request"},
            {"timestamp": "2026-09-20T10:29:50.150Z", "level": "INFO", "message": "Inference completed in 150ms"},
            {"timestamp": "2026-09-20T10:29:50.200Z", "level": "WARN", "message": "Queue depth increasing"},
        ]
        cloud_logs_path = self.bundle_path / "logs/cloud-service.jsonl"
        with open(cloud_logs_path, 'w') as f:
            for entry in cloud_logs:
                f.write(json.dumps(entry) + "\n")

        # ROS nodes logs
        ros_logs = [
            {"timestamp": "2026-09-20T10:29:50.210Z", "node": "detection_listener", "level": "INFO", "message": "Received detection"},
            {"timestamp": "2026-09-20T10:29:50.260Z", "node": "navigation_controller", "level": "ERROR", "message": "Transform lookup failed: stale data"},
            {"timestamp": "2026-09-20T10:29:50.270Z", "node": "safety_monitor", "level": "CRITICAL", "message": "Emergency stop triggered: control deadline missed"},
        ]
        ros_logs_path = self.bundle_path / "logs/ros-nodes.jsonl"
        with open(ros_logs_path, 'w') as f:
            for entry in ros_logs:
                f.write(json.dumps(entry) + "\n")

        logger.debug("Wrote log files")

    def _write_metrics(self):
        """Write metric CSV files."""
        # GPU metrics
        gpu_csv = """timestamp,gpu_utilization,memory_utilization,queue_depth,inference_latency_ms
2026-09-20T10:29:50Z,45,60,5,80
2026-09-20T10:29:50.1Z,50,65,8,95
2026-09-20T10:29:50.2Z,80,70,15,150
2026-09-20T10:29:50.3Z,90,75,25,200
"""
        (self.bundle_path / "metrics/gpu.csv").write_text(gpu_csv)

        # Network metrics
        network_csv = """timestamp,latency_ms,packet_loss,jitter
2026-09-20T10:29:50Z,10,0.0,1
2026-09-20T10:29:50.1Z,12,0.0,2
2026-09-20T10:29:50.2Z,15,0.0,3
2026-09-20T10:29:50.3Z,20,0.0,5
"""
        (self.bundle_path / "metrics/network.csv").write_text(network_csv)

        logger.debug("Wrote metric files")

    def _write_recordings(self):
        """Write placeholder MCAP file (just a small binary header for validity)."""
        # MCAP files have a specific header. We'll write a minimal valid one for placeholder.
        # In reality, we would use the mcap library to write a proper file.
        mcap_header = b'\x89MCAP\r\n\x0a\n\x1a\n' + \
                      b'\x04\x00\x00\x00' + \
                      b'\x00\x00\x00\x00' + \
                      b'\x00\x00\x00\x00' + \
                      b'\x00\x00\x00\x00'
        mcap_path = self.bundle_path / "recordings/robot_run.mcap"
        with open(mcap_path, 'wb') as f:
            f.write(mcap_header)
            f.write(b'\x00' * 100)  # Some dummy data
        logger.debug(f"Wrote placeholder MCAP to {mcap_path}")

    def _write_configs(self):
        """Write configuration files."""
        # Inference config
        inference_yaml = """model_name: objdet
version: v42
dynamic_batching:
  enabled: true
  max_batch_size: 32
  batching_window_ms: 200  # Increased in v42
  timeout_ms: 500
"""
        (self.bundle_path / "config/inference.yaml").write_text(inference_yaml)

        # Robot params
        robot_params_yaml = """robot_name: warehouse-amr-01
detection_freshness_budget_ms: 120
control_loop_period_ms: 50
safety_watchdog_timeout_ms: 100
"""
        (self.bundle_path / "config/robot_params.yaml").write_text(robot_params_yaml)

        logger.debug("Wrote config files")

    def _write_deployments(self):
        """Write deployment events."""
        events_content = {
            "deployment_id": "v42",
            "timestamp": "2026-09-20T08:00:00Z",
            "service": "inference-service",
            "image": "inference-service:v42",
            "changes": {
                "config": {
                    "dynamic_batching.window_ms": {"from": 100, "to": 200}
                }
            },
            "author": "ml-team@example.com"
        }
        events_path = self.bundle_path / "deployments/events.json"
        with open(events_path, 'w') as f:
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
- Checked robot logs: detection listener received stale object data
- Network latency appeared normal
- Inference service metrics showed increased queue depth
- Correlated with deployment v42 rolled out 2 hours prior

**Action Taken**: Manual override to clear emergency stop, robot resumed operation. Recommended rollback of inference service to v41.
"""
        note_path = self.bundle_path / "observations/operator_note.md"
        with open(note_path, 'w') as f:
            f.write(note_content)
        logger.debug(f"Wrote operator note to {note_path}")

    def _write_media(self):
        """Write placeholder media file."""
        # Just a small binary file to represent the video
        media_path = self.bundle_path / "media/incident.mp4"
        with open(media_path, 'wb') as f:
            f.write(b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom')  # Minimal MP4 header
            f.write(b'\x00' * 1000)  # Dummy data
        logger.debug(f"Wrote placeholder media to {media_path}")

    def _build_incident_object(self) -> Incident:
        """Build the Incident object from the generated bundle."""
        incident = Incident(
            title="Warehouse robot emergency stop after deployment v42",
            description="Autonomous mobile robot consumes stale object detections from remote GPU inference service after deployment v42 increases dynamic batching window, causing P99 latency to exceed freshness budget.",
            system_name="warehouse-amr-01",
            approximate_time="2026-09-20T10:30:00Z",
            source_repositories=[
                "https://github.com/example/inference-service",
                "https://github.com/example/robot-navigation"
            ],
            commit_hash="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0",
        )

        # Add evidence items from the bundle
        evidence_paths = [
            # Required evidence from manifest
            ("manifest.yaml", True),
            ("source/cloud-service/Dockerfile", True),
            ("source/robot-stack/src/main.cpp", True),
            ("traces/otel.json", True),
            ("logs/cloud-service.jsonl", True),
            ("logs/ros-nodes.jsonl", True),
            ("metrics/gpu.csv", True),
            ("metrics/network.csv", True),
            ("recordings/robot_run.mcap", True),
            ("config/inference.yaml", True),
            ("config/robot_params.yaml", True),
            ("deployments/events.json", True),
            ("observations/operator_note.md", True),
            ("media/incident.mp4", True),
            # Additional optional evidence
            ("README.md", False),
        ]

        for rel_path, required in evidence_paths:
            abs_path = self.bundle_path / rel_path
            if abs_path.exists():
                # Compute a simple checksum (in reality, we'd use the security module)
                content = abs_path.read_bytes()
                checksum = hashlib.sha256(content).hexdigest()
                # For text files, also get the string content for size calculation
                if abs_path.suffix not in ['.mcap', '.mp4']:
                    try:
                        text_content = content.decode('utf-8')
                        size_bytes = len(text_content.encode('utf-8'))
                    except UnicodeDecodeError:
                        size_bytes = len(content)
                else:
                    size_bytes = len(content)
                evidence = EvidenceItem(
                    file_path=rel_path,
                    file_type="application/octet-dir",  # Simplified
                    size_bytes=size_bytes,
                    checksum_sha256=checksum,
                    status="OBSERVED",
                    is_required=required,
                )
                incident.evidence_items.append(evidence)
            else:
                logger.warning(f"Expected evidence file not found: {abs_path}")

        incident.update_counts()
        return incident
