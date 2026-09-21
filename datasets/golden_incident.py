"""
Golden incident generator for CAU-0001: Warehouse robot inference latency incident.
"""
import yaml
import json
import csv
import hashlib
from pathlib import Path
from cauveris.schemas.incident import Incident, EvidenceItem
from cauveris.config import get_settings
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class GoldenIncidentGenerator:
    """Generates the CAU-0001 golden incident bundle."""

    def __init__(self):
        self.settings = get_settings()
        self.bundle_path = Path("./incident-CAU-0001")
        self.incident_id = "CAU-0001"

    def generate(self) -> Incident:
        """Generate the complete CAU-0001 incident bundle."""
        logger.info(f"Generating golden incident {self.incident_id}")

        # Clean and create directory structure
        self._create_bundle_structure()

        # Create all evidence files with meaningful content
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

        # Build incident object
        incident = self._build_incident_object()

        logger.info(f"Generated golden incident {self.incident_id} with {incident.evidence_count} evidence items")
        return incident

    def _create_bundle_structure(self):
        """Create the directory structure for the incident bundle."""
        # Remove existing bundle if present
        if self.bundle_path.exists():
            import shutil
            shutil.rmtree(self.bundle_path)

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
        """Write manifest.yaml with incident metadata."""
        manifest = {
            "incident_id": self.incident_id,
            "title": "Warehouse Robot Emergency Stop - Inference Latency",
            "description": "Autonomous mobile robot emergency stop due to stale object detection from GPU inference service",
            "system_name": "warehouse-robot-flotilla",
            "approximate_time": "2026-09-20T10:30:00Z",
            "source_repositories": [
                "github.com/cauveris/robot-stack",
                "github.com/cauveris/inference-service"
            ],
            "commit_hash": "a1b2c3d4e5f6789012345678901234567890abcd",
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
                "observations/operator_note.md"
            ],
            "evidence_schema_version": "1.0.0"
        }

        manifest_path = self.bundle_path / "manifest.yaml"
        with open(manifest_path, 'w') as f:
            yaml.dump(manifest, f, default_flow_style=False)
        logger.debug(f"Written manifest to {manifest_path}")

    def _write_source_files(self):
        """Write source code files."""
        # Cloud service Dockerfile
        dockerfile_content = '''FROM nvidia/cuda:12.1-runtime-ubuntu22.04
RUN apt-get update && apt-get install -y python3-pip
WORKDIR /app
COPY requirements.txt .
RUN pip3 install -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["python3", "inference_server.py"]
'''
        dockerfile_path = self.bundle_path / "source/cloud-service/Dockerfile"
        with open(dockerfile_path, 'w') as f:
            f.write(dockerfile_content)

        # Robot stack main.cpp
        main_cpp_content = '''/**
 * Warehouse robot navigation stack
 * Subscribes to object detections and controls robot movement
 */
#include <rclcpp/rclcpp.hpp>
#include <object_detection_msgs/msg/object_array.hpp>
#include <tf2_ros/buffer.h>
#include <tf2_ros/transform_listener.hpp>
#include <chrono>

using namespace std::chrono_literals;

class NavigationNode : public rclcpp::Node {
public:
    NavigationNode() : Node("navigation_node") {
        // Subscription to object detections
        detection_sub_ = this->create_subscription<object_detection_msgs::msg::ObjectArray>(
            "object_detections", 10,
            std::bind(&NavigationNode::detection_callback, this, std::placeholders::_1));

        // TF buffer for coordinate transformations
        tf_buffer_ = std::make_unique<tf2_ros::Buffer>(this->get_clock());
        tf_listener_ = std::make_shared<tf2_ros::TransformListener>(*tf_buffer_);

        // Control loop timer (10Hz)
        control_timer_ = this->create_wall_timer(
            100ms, std::bind(&NavigationNode::control_loop, this));

        // Declare parameters
        this->declare_parameter("detection_freshness_budget_ms", 120);
    }

private:
    void detection_callback(const object_detection_msgs::msg::ObjectArray::SharedPtr msg) {
        last_detection_time_ = this->now();
        latest_detections_ = msg;
    }

    void control_loop() {
        // Check detection freshness
        auto now = this->now();
        auto detection_age = (now - last_detection_time_).milliseconds();
        int freshness_budget_ms;
        this->get_parameter("detection_freshness_budget_ms", freshness_budget_ms);

        if (detection_age > freshness_budget_ms) {
            RCLCPP_WARN(this->get_logger(), "Stale detection: age=%d ms, budget=%d ms",
                       detection_age, freshness_budget_ms);
            // In real implementation, would trigger safety stop here
            return;
        }

        // Check for required transforms
        try {
            // Lookup transform from camera to base_link
            auto transform = tf_buffer_->lookupTransform(
                "base_link", "camera_optical_frame",
                tf2::TimePointZero);
            // Process detections and compute control commands...
        } catch (tf2::TransformException &ex) {
            RCLCPP_ERROR(this->get_logger(), "Transform lookup failed: %s", ex.what());
            // Trigger safety stop due to missing transform
            trigger_emergency_stop();
            return;
        }

        // Normal control processing...
    }

    void trigger_emergency_stop() {
        RCLCPP_ERROR(this->get_logger(), "EMERGENCY STOP TRIGGERED");
        # Publish zero velocity command, activate safety systems, etc.
    }

    rclcpp::Subscription<object_detection_msgs::msg::ObjectArray>::SharedPtr detection_sub_;
    std::unique_ptr<tf2_ros::Buffer> tf_buffer_;
    std::shared_ptr<tf2_ros::TransformListener> tf_listener_;
    rclcpp::TimerBase::SharedPtr control_timer_;
    rclcpp::Time last_detection_time_;
    object_detection_msgs::msg::ObjectArray::SharedPtr latest_detections_;
};

int main(int argc, char ** argv) {
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<NavigationNode>());
    rclcpp::shutdown();
    return 0;
}
'''
        main_cpp_path = self.bundle_path / "source/robot-stack/src/main.cpp"
        with open(main_cpp_path, 'w') as f:
            f.write(main_cpp_content)

        logger.debug(f"Written source files to {self.bundle_path}/source/")

    def _write_traces(self):
        """Write OpenTelemetry trace file."""
        otel_trace = {
            "traceID": "a1b2c3d4e5f678901234567890123456",
            "spans": [
                {
                    "spanID": "1111111111111111",
                    "traceID": "a1b2c3d4e5f678901234567890123456",
                    "parentSpanID": "",
                    "name": "HTTP POST /detect",
                    "kind": "SERVER",
                    "timestamp": "1663657800000000000",  # 2022-09-20T10:30:00Z in nanoseconds
                    "duration": "150000000",  # 150ms
                    "attributes": {
                        "http.method": "POST",
                        "http.url": "/detect",
                        "http.status_code": 200,
                        "net.peer.ip": "10.0.1.100",
                        "net.peer.port": "8080"
                    },
                    "events": [
                        {
                            "timestamp": "1663657800000000000",
                            "name": "message.received",
                            "attributes": {
                                "message.size": "2048"
                            }
                        },
                        {
                            "timestamp": "1663657800100000000",
                            "name": "inference.start",
                            "attributes": {},
                        }
                    ]
                },
                {
                    "spanID": "2222222222222222",
                    "traceID": "a1b2c3d4e5f678901234567890123456",
                    "parentSpanID": "1111111111111111",
                    "name": "object_detection_publish",
                    "kind": "PRODUCER",
                    "timestamp": "1663657800200000000",  # 150ms after request start
                    "duration": "5000000",  # 5ms
                    "attributes": {
                        "messaging.system": "ros2",
                        "messaging.destination": "object_detections",
                        "messaging.destination_kind": "topic"
                    }
                },
                {
                    "spanID": "3333333333333333",
                    "traceID": "a1b2c3d4e5f678901234567890123456",
                    "parentSpanID": "2222222222222222",
                    "name": "tf2_buffer_lookup_transform",
                    "kind": "CLIENT",
                    "timestamp": "1663657800300000000",  # 100ms after detection published
                    "duration": "200000000",  # 200ms (exceeds freshness budget!)
                    "attributes": {
                        "tf2.frame_id": "base_link",
                        "tf2.child_frame_id": "camera_optical_frame"
                    },
                    "events": [
                        {
                            "timestamp": "1663657800400000000",
                            "name": "transform.timeout",
                            "attributes": {
                                "error": "Lookup would exceed timeout",
                                "timeout_ms": "120"
                            }
                        }
                    ]
                }
            ]
        }

        otel_path = self.bundle_path / "traces/otel.json"
        with open(otel_path, 'w') as f:
            json.dump(otel_trace, f, indent=2)
        logger.debug(f"Written OTel trace to {otel_path}")

    def _write_logs(self):
        """Write log files."""
        # Cloud service logs
        cloud_logs = [
            {"timestamp": "2026-09-20T10:29:58.123Z", "level": "INFO", "message": "Deployment v42 started, batching_window_ms=200"},
            {"timestamp": "2026-09-20T10:29:59.456Z", "level": "INFO", "message": "Received inference request from 10.0.1.100"},
            {"timestamp": "2026-09-20T10:30:00.000Z", "level": "INFO", "message": "Inference started (batch size: 8)"},
            {"timestamp": "2026-09-20T10:30:00.150Z", "level": "INFO", "message": "Inference completed, returning results"},
            {"timestamp": "2026-09-20T10:30:00.200Z", "level": "INFO", "message": "Published detection to ROS topic"},
            {"timestamp": "2026-09-20T10:30:00.350Z", "level": "WARN", "message": "Detection queue depth increasing: 5->12"},
            {"timestamp": "2026-09-20T10:30:00.500Z", "level": "ERROR", "message": "TF lookup timeout in robot transformation"},
        ]

        cloud_log_path = self.bundle_path / "logs/cloud-service.jsonl"
        with open(cloud_log_path, 'w') as f:
            for log_entry in cloud_logs:
                f.write(json.dumps(log_entry) + '\n')

        # ROS nodes logs
        ros_logs = [
            {"timestamp": "2026-09-20T10:29:59.000Z", "level": "INFO", "message": "navigation_node: Subscribed to object_detections"},
            {"timestamp": "2026-09-20T10:30:00.250Z", "level": "INFO", "message": "navigation_node: Detection received, age=50ms"},
            {"timestamp": "2026-09-20T10:30:00.400Z", "level": "WARN", "message": "navigation_node: Detection age approaching limit: 110ms"},
            {"timestamp": "2026-09-20T10:30:00.550Z", "level": "ERROR", "message": "navigation_node: Transform lookup failed - timeout"},
            {"timestamp": "2026-09-20T10:30:00.600Z", "level": "ERROR", "message": "navigation_node: EMERGENCY STOP TRIGGERED"},
        ]

        ros_log_path = self.bundle_path / "logs/ros-nodes.jsonl"
        with open(ros_log_path, 'w') as f:
            for log_entry in ros_logs:
                f.write(json.dumps(log_entry) + '\n')

        # System logs
        system_logs = [
            "2026-09-20 10:29:58 INFO  systemd[1]: Started Warehouse Robot Services.",
            "2026-09-20 10:29:59 INFO  kernel: nvidia-gpu 0000:00:04.0: enabling device (0000 -> 0002)",
            "2026-09-20 10:30:00 INFO  robot-hw: Camera IMX214 initialized",
            "2026-09-20 10:30:00 WARN  robot-hw: Network latency increasing (avg: 45ms -> 78ms)",
            "2026-09-20 10:30:01 ERROR safety-monitor: Emergency stop activated - control deadline missed",
            "2026-09-20 10:30:01 INFO  motor-controller: All motors commanded to zero velocity",
        ]

        system_log_path = self.bundle_path / "logs/system.log"
        with open(system_log_path, 'w') as f:
            f.write('\n'.join(system_logs))

        logger.debug(f"Written log files to {self.bundle_path}/logs/")

    def _write_metrics(self):
        """Write metrics CSV files."""
        # GPU metrics - showing increasing latency
        gpu_metrics = [
            ["timestamp", "gpu_utilization_percent", "memory_utilization_percent", "temperature_celsius", "power_watts", "inference_latency_ms"],
            ["2026-09-20T10:29:58Z", "45", "60", "65", "120", "85"],
            ["2026-09-20T10:29:59Z", "52", "65", "67", "125", "92"],
            ["2026-09-20T10:30:00Z", "78", "80", "72", "150", "150"],  # Spike in latency
            ["2026-09-20T10:30:01Z", "85", "85", "75", "160", "180"],
            ["2026-09-20T10:30:02Z", "82", "82", "73", "155", "165"],
        ]

        gpu_path = self.bundle_path / "metrics/gpu.csv"
        with open(gpu_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(gpu_metrics)

        # Network metrics - showing increasing queue depth/latency
        network_metrics = [
            ["timestamp", "rx_bytes_per_sec", "tx_bytes_per_sec", "rx_drop_percent", "tx_drop_percent", "latency_ms", "queue_depth"],
            ["2026-09-20T10:29:58Z", "1000000", "800000", "0.0", "0.0", "5", "2"],
            ["2026-09-20T10:29:59Z", "1200000", "900000", "0.1", "0.0", "8", "4"],
            ["2026-09-20T10:30:00Z", "1500000", "1000000", "0.2", "0.1", "15", "8"],  # Increasing
            ["2026-09-20T10:30:01Z", "1800000", "1100000", "0.3", "0.2", "25", "15"],
            ["2026-09-20T10:30:02Z", "1600000", "1000000", "0.2", "0.1", "20", "12"],
        ]

        network_path = self.bundle_path / "metrics/network.csv"
        with open(network_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(network_metrics)

        # CPU metrics
        cpu_metrics = [
            ["timestamp", "cpu_utilization_percent", "load_avg_1m", "load_avg_5m", "load_avg_15m", "temperature_celsius"],
            ["2026-09-20T10:29:58Z", "35", "0.8", "0.9", "1.0", "55"],
            ["2026-09-20T10:29:59Z", "42", "1.0", "1.1", "1.2", "57"],
            ["2026-09-20T10:30:00Z", "68", "1.5", "1.6", "1.7", "62"],
            ["2026-09-20T10:30:01Z", "72", "1.8", "1.9", "2.0", "65"],
            ["2026-09-20T10:30:02Z", "65", "1.5", "1.6", "1.7", "60"],
        ]

        cpu_path = self.bundle_path / "metrics/cpu.csv"
        with open(cpu_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(cpu_metrics)

        # Memory metrics
        memory_metrics = [
            ["timestamp", "memory_total_mb", "memory_used_mb", "memory_free_mb", "memory_utilization_percent", "swap_used_mb"],
            ["2026-09-20T10:29:58Z", "8192", "2048", "6144", "25", "512"],
            ["2026-09-20T10:29:59Z", "8192", "2560", "5632", "31", "512"],
            ["2026-09-20T10:30:00Z", "8192", "3072", "5120", "37", "512"],
            ["2026-09-20T10:30:01Z", "8192", "3584", "4608", "44", "512"],
            ["2026-09-20T10:30:02Z", "8192", "3328", "4864", "41", "512"],
        ]

        memory_path = self.bundle_path / "metrics/memory.csv"
        with open(memory_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(memory_metrics)

        logger.debug(f"Written metrics files to {self.bundle_path}/metrics/")

    def _write_recordings(self):
        """Write a minimal MCAP recording file."""
        # Create a minimal valid MCAP file (just the header for demo purposes)
        # Real MCAP is complex, so we'll create a placeholder that validates as having MCAP structure
        mcap_header = bytearray([
            0x89, 0x4D, 0x43, 0x41, 0x50,  # Magic: "MCAP"
            0x0D, 0x0A,                  # Newline
            0x1A, 0x0A,                  # More newline
            0x00, 0x00, 0x00, 0x00,      # TODO: Library/version
            0x00, 0x00, 0x00, 0x00,      # TODO: Header length
            0x00, 0x00, 0x00, 0x00,      # TODO: Footer start offset
            0x00, 0x00, 0x00, 0x00,      # TODO: Header CRC
        ])

        # Add some minimal content to make it look more realistic
        mcap_content = mcap_header
        mcap_content.extend(b'\x00' * 1000)  # Padding

        recording_path = self.bundle_path / "recordings/robot_run.mcap"
        with open(recording_path, 'wb') as f:
            f.write(mcap_content)

        logger.debug(f"Written MCAP recording to {recording_path}")

    def _write_configs(self):
        """Write configuration files."""
        # Inference configuration
        inference_config = {
            "model_name": "yolov8n",
            "input_width": 640,
            "input_height": 640,
            "confidence_threshold": 0.5,
            "nms_threshold": 0.4,
            "dynamic_batching": {
                "enabled": True,
                "max_batch_size": 8,
                "batching_window_ms": 200,  # This is the key problematic value
                "timeout_ms": 500
            },
            "device": "cuda:0",
            "precision": "fp16"
        }

        inference_path = self.bundle_path / "config/inference.yaml"
        with open(inference_path, 'w') as f:
            yaml.dump(inference_config, f, default_flow_style=False)

        # Robot parameters
        robot_params = {
            "robot_name": "warehouse-flotilla-01",
            "navigation": {
                "max_speed_mps": 2.0,
                "min_speed_mps": 0.1,
                "acceleration_limit_mps2": 0.5,
                "deceleration_limit_mps2": 0.8
            },
            "safety": {
                "detection_freshness_budget_ms": 120,  # Robot's freshness budget
                "transform_timeout_ms": 100,
                "control_loop_deadline_ms": 100,
                "emergency_stop_on_transform_fail": True,
                "emergency_stop_on_stale_data": True
            },
            "perception": {
                "detection_topics": ["object_detections"],
                "required_detection_frequency_hz": 10
            }
        }

        robot_params_path = self.bundle_path / "config/robot_params.yaml"
        with open(robot_params_path, 'w') as f:
            yaml.dump(robot_params, f, default_flow_style=False)

        # Launch snapshot
        launch_snapshot = {
            "launch_file": "warehouse_robot.launch.py",
            "arguments": {
                "use_sim_time": "false",
                "robot_namespace": "flotilla_01",
                "enable_safety_monitoring": "true"
            },
            "nodes": [
                {"package": "robot_navigation", "executable": "navigation_node", "name": "navigation_node"},
                {"package": "object_detection", "executable": "detection_client", "name": "detection_client"},
                {"package": "tf2_ros", "executable": "buffer_server", "name": "tf_buffer"}
            ],
            "timestamp": "2026-09-20T10:29:50Z"
        }

        launch_path = self.bundle_path / "config/launch_snapshot.json"
        with open(launch_path, 'w') as f:
            json.dump(launch_snapshot, f, indent=2)

        # Environment
        environment = {
            "ROS_VERSION": "2",
            "ROS_DISTRO": "humble",
            "CUDA_VISIBLE_DEVICES": "0",
            "PYTHONPATH": "/opt/ros/humble/lib/python3.10/site-packages:/app",
            "LD_LIBRARY_PATH": "/usr/local/cuda/lib64:/usr/lib/x86_64-linux-gnu",
            "GAZEBO_MODEL_PATH": "/opt/ros/huble/share/gazebo-11/models",
            "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp"
        }

        env_path = self.bundle_path / "config/environment.json"
        with open(env_path, 'w') as f:
            json.dump(environment, f, indent=2)

        logger.debug(f"Written config files to {self.bundle_path}/config/")

    def _write_deployments(self):
        """Write deployment events."""
        deployment_events = {
            "deployment_id": "deploy-v42",
            "timestamp": "2026-09-20T10:29:58Z",
            "repository": "github.com/cauveris/inference-service",
            "commit_from": "a1b2c3d4e5f6789012345678901234567890abcd",  # v41
            "commit_to": "a1b2c3d4e5f6789012345678901234567890abce",  # v42
            "changes": [
                {
                    "type": "configuration",
                    "file": "config/inference.yaml",
                    "change": "batching_window_ms increased from 100 to 200",
                    "old_value": 100,
                    "new_value": 200,
                    "reason": "Increase throughput for handling peak load"
                }
            ],
            "approval": {
                "approved_by": "ml-platform-team",
                "approved_at": "2026-09-20T10:00:00Z",
                "rollout_strategy": "rolling",
                "health_checks_passed": True
            }
        }

        deploy_path = self.bundle_path / "deployments/events.json"
        with open(deploy_path, 'w') as f:
            json.dump(deployment_events, f, indent=2)

        logger.debug(f"Written deployment events to {deploy_path}")

    def _write_observations(self):
        """Write operator observations."""
        operator_note = '''# Operator Observation Log
## Incident Report: Warehouse Robot Emergency Stop

**Date/Time:** 2026-09-20 10:30:00 UTC
**Location:** Aisle B, Sector 3
**Robot ID:** warehouse-flotilla-01
**Operator:** J. Chen (ID: OP-042)

### Description:
At approximately 10:30 AM, robot warehouse-flotilla-01 came to a sudden stop in the middle of Aisle B while attempting to navigate to pick location B-14. The robot exhibited the following behavior:
- Sudden deceleration from 1.5 m/s to 0 m/s over approximately 0.5 seconds
- All wheel motors commanded to zero torque
- Safety indicator lights flashing red
- Audible emergency alarm activated
- Diagnostic display showing "EMERGENCY STOP - CONTROL DEADLINE MISSED"

### Preceding Events:
- Robot had been operating normally for approximately 2 hours
- Recently completed pick operation at location A-07
- Was in transit to next pick location when incident occurred
- No obstacles detected in immediate vicinity via lidar

### Preliminary Diagnosis:
Based on telemetry data and operator experience, this appears to be related to:
1. Stale sensor data causing navigation transform failures
2. Possible perception pipeline latency increase
3. Safety system functioning correctly by stopping when transform data unavailable

### Actions Taken:
1. Robot placed in manual mode for safety inspection
2. Diagnostic logs collected from robot and cloud services
3. Deployment history checked - inference service updated to v42 approximately 2 minutes prior
4. Network connectivity verified as nominal

### Recommendations:
1. Rollback inference service to v41 to test if issue resolves
2. Increase robot detection freshness budget if perception latency is expected to increase
3. Add better diagnostic reporting for perception pipeline latency
4. Review deployment v42 changes for potential performance impacts

**Signature:** ___________________
**Time:** 10:35 AM
'''

        obs_path = self.bundle_path / "observations/operator_note.md"
        with open(obs_path, 'w') as f:
            f.write(operator_note)

        logger.debug(f"Written operator note to {obs_path}")

    def _write_media(self):
        """Write a placeholder media file."""
        # Create a minimal MP4-like file (just header for demo)
        # Real MP4 is complex, so we'll create a placeholder
        mp4_header = bytearray([
            0x00, 0x00, 0x00, 0x18,  # Size
            0x66, 0x74, 0x79, 0x70,  # "ftyp"
            0x6D, 0x70, 0x34, 0x31,  # "mp41"
            0x00, 0x00, 0x00, 0x00,
            0x6D, 0x70, 0x34, 0x31,  # "mp41"
            0x69, 0x73, 0x6F, 0x6D,   # "isom"
            0x69, 0x73, 0x6F, 0x32,   # "iso2"
            0x61, 0x76, 0x63, 0x31,   # "avc1"
            0x6D, 0x70, 0x34, 0x32,   # "mp42"
        ])

        # Add some minimal content
        mp4_content = mp4_header
        mp4_content.extend(b'\x00' * 5000)  # Reasonable size for demo

        media_path = self.bundle_path / "media/incident.mp4"
        with open(media_path, 'wb') as f:
            f.write(mp4_content)

        logger.debug(f"Written media file to {media_path}")

    def _build_incident_object(self) -> Incident:
        """Build the Incident object from the generated evidence files."""
        evidence_items = []

        # Define all evidence files with their properties
        evidence_definitions = [
            # Manifest
            ("manifest.yaml", "text/yaml", True),

            # Source files
            ("source/cloud-service/Dockerfile", "text/dockerfile", True),
            ("source/robot-stack/src/main.cpp", "text/xc++src", True),

            # Traces
            ("traces/otel.json", "application/json", True),

            # Logs
            ("logs/cloud-service.jsonl", "application/jsonlines", True),
            ("logs/ros-nodes.jsonl", "application/jsonlines", True),
            ("logs/system.log", "text/plain", True),

            # Metrics
            ("metrics/gpu.csv", "text/csv", True),
            ("metrics/cpu.csv", "text/csv", True),
            ("metrics/memory.csv", "text/csv", True),
            ("metrics/network.csv", "text/csv", True),

            # Recordings
            ("recordings/robot_run.mcap", "application/octet-stream", True),

            # Configs
            ("config/inference.yaml", "text/yaml", True),
            ("config/robot_params.yaml", "text/yaml", True),
            ("config/launch_snapshot.json", "application/json", True),
            ("config/environment.json", "application/json", True),

            # Deployments
            ("deployments/events.json", "application/json", True),

            # Observations
            ("observations/operator_note.md", "text/markdown", True),

            # Media
            ("media/incident.mp4", "video/mp4", False),  # Not required for processing
        ]

        for file_path, file_type, is_required in evidence_definitions:
            full_path = self.bundle_path / file_path

            # Calculate actual file size and checksum
            size_bytes = full_path.stat().st_size if full_path.exists() else 0

            # Calculate SHA-256 checksum
            checksum_sha256 = ""
            if full_path.exists():
                with open(full_path, 'rb') as f:
                    content = f.read()
                    checksum_sha256 = hashlib.sha256(content).hexdigest()

            evidence = EvidenceItem(
                file_path=file_path,
                file_type=file_type,
                size_bytes=size_bytes,
                checksum_sha256=checksum_sha256,
                status="OBSERVED" if full_path.exists() else "MISSING",
                is_required=is_required,
                metadata={"generated": True, "source": "golden_incident_generator"}
            )

            evidence_items.append(evidence)

        # Create incident
        incident = Incident(
            title="Warehouse Robot Emergency Stop - Inference Latency",
            description="Autonomous mobile robot emergency stop due to stale object detection from GPU inference service following deployment v42 that increased dynamic batching window",
            system_name="warehouse-robot-flotilla",
            approximate_time=datetime.fromisoformat("2026-09-20T10:30:00"),
            source_repositories=[
                "github.com/cauveris/robot-stack",
                "github.com/cauveris/inference-service"
            ],
            commit_hash="a1b2c3d4e5f6789012345678901234567890abcd",
            evidence_items=evidence_items,
            manifest={},  # Will be populated by validation
        )

        # Update counts
        incident.update_counts()

        return incident
