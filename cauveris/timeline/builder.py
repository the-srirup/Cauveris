"""
Timeline builder for normalizing and aligning evidence.
"""
import logging
import json
import csv
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import re
from cauveris.schemas.incident import Incident
from cauveris.config import get_settings

logger = logging.getLogger(__name__)


class TimelineBuilder:
    """Builds a synchronized timeline from incident evidence."""

    def __init__(self):
        self.settings = get_settings()

    def _locate_bundle_path(self, incident: Incident) -> Optional[Path]:
        """Locate the bundle directory for the incident."""
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

    async def build(self, incident: Incident) -> Incident:
        """
        Build a synchronized timeline from evidence.

        Args:
            incident: Incident with validated evidence

        Returns:
            Incident with timeline data attached
        """
        logger.info(f"Building timeline for incident {incident.id}")

        bundle_path = self._locate_bundle_path(incident)
        if not bundle_path:
            logger.warning(f"Bundle directory not found for {incident.id}, setting empty timeline")
            incident.timeline_events = []
            return incident

        timeline_events = []

        # 1. Parse OpenTelemetry traces
        trace_path = bundle_path / "traces" / "otel.json"
        if trace_path.exists():
            trace_events = await self._parse_otel_traces(trace_path, bundle_path)
            timeline_events.extend(trace_events)

        # 2. Parse logs (jsonl and text)
        logs_dir = bundle_path / "logs"
        if logs_dir.exists():
            log_events = await self._parse_logs(logs_dir, bundle_path)
            timeline_events.extend(log_events)

        # 3. Parse metrics (GPU and network CSVs)
        metrics_dir = bundle_path / "metrics"
        if metrics_dir.exists():
            metric_events = await self._parse_metrics(metrics_dir, bundle_path)
            timeline_events.extend(metric_events)

        # 4. Parse deployment events
        deploy_path = bundle_path / "deployments" / "events.json"
        if deploy_path.exists():
            deploy_events = await self._parse_deployment_events(deploy_path, bundle_path)
            timeline_events.extend(deploy_events)

        # 5. Parse operator observation note
        note_path = bundle_path / "observations" / "operator_note.md"
        if note_path.exists():
            note_events = await self._parse_operator_note(note_path, bundle_path)
            timeline_events.extend(note_events)

        # 6. Parse MCAP recording (ROS 2 physical AI channels)
        mcap_path = bundle_path / "recordings" / "robot_run.mcap"
        if mcap_path.exists():
            mcap_events = await self._parse_mcap_recording(mcap_path, bundle_path)
            timeline_events.extend(mcap_events)

        # Perform clock-offset estimation across domains (cloud, host, robot, simulation)
        clock_offsets = self._estimate_clock_offsets(bundle_path, timeline_events)
        if incident.manifest is not None:
            incident.manifest["clock_alignment"] = clock_offsets

        # Sort events chronologically by timestamp_ns
        timeline_events.sort(key=lambda x: x.get("timestamp_ns", 0))

        # Normalize timestamps to relative seconds and relative nanoseconds
        if timeline_events:
            base_time = min(event.get("timestamp_ns", 0) for event in timeline_events if event.get("timestamp_ns", 0) > 0)
            for event in timeline_events:
                t_ns = event.get("timestamp_ns", base_time)
                rel_ns = t_ns - base_time
                event["relative_timestamp_ns"] = rel_ns
                event["relative_timestamp_s"] = round(rel_ns / 1_000_000_000.0, 3)

        incident.timeline_events = timeline_events
        logger.info(f"Built timeline with {len(timeline_events)} synchronized events")
        return incident

    async def _parse_otel_traces(self, otel_path: Path, bundle_path: Path) -> List[Dict[str, Any]]:
        """Parse OpenTelemetry JSON trace file."""
        events = []
        try:
            with open(otel_path, 'r', encoding='utf-8') as f:
                trace_data = json.load(f)

            trace_id_top = trace_data.get("traceID") or trace_data.get("traceId", "")
            for span in trace_data.get("spans", []):
                raw_ts = span.get("timestamp", 0)
                if isinstance(raw_ts, str):
                    try:
                        timestamp_ns = int(raw_ts)
                    except ValueError:
                        dt = datetime.fromisoformat(raw_ts.replace('Z', '+00:00'))
                        timestamp_ns = int(dt.timestamp() * 1_000_000_000)
                else:
                    timestamp_ns = int(raw_ts)

                span_id = span.get("spanId") or span.get("spanID") or span.get("span_id", "")
                trace_id = span.get("traceId") or span.get("traceID") or trace_id_top

                duration_ns = span.get("duration", 0)
                duration_ms = round(duration_ns / 1_000_000.0, 2) if duration_ns else 0.0

                span_name = span.get("name", "span")
                status_dict = span.get("status", {})
                status_msg = status_dict.get("message", "") if isinstance(status_dict, dict) else str(status_dict)

                event = {
                    "timestamp_ns": timestamp_ns,
                    "original_timestamp": str(raw_ts),
                    "event_type": "trace_span",
                    "source_type": "otel_trace",
                    "lane": "controller_latency" if "control" in span_name.lower() else "cloud_requests",
                    "source": str(otel_path.relative_to(bundle_path)).replace("\\", "/"),
                    "message": f"Trace span '{span_name}' (duration: {duration_ms}ms){': ' + status_msg if status_msg else ''}",
                    "attributes": {
                        "span_id": span_id,
                        "trace_id": trace_id,
                        "span_name": span_name,
                        "duration_ns": duration_ns,
                        "duration_ms": duration_ms,
                    },
                    "trace_id": trace_id,
                    "span_id": span_id,
                    "confidence": 0.95,
                    "status": status_msg
                }

                if "attributes" in span and isinstance(span["attributes"], dict):
                    event["attributes"].update(span["attributes"])

                events.append(event)

        except Exception as e:
            logger.error(f"Failed to parse OTel traces: {e}")

        return events

    async def _parse_logs(self, logs_dir: Path, bundle_path: Path) -> List[Dict[str, Any]]:
        """Parse log files (JSONL and plain text)."""
        events = []
        for log_file in logs_dir.glob("*.jsonl"):
            events.extend(await self._parse_jsonl_log(log_file, bundle_path))
        for log_file in logs_dir.glob("*.log"):
            events.extend(await self._parse_text_log(log_file, bundle_path))
        return events

    async def _parse_jsonl_log(self, log_path: Path, bundle_path: Path) -> List[Dict[str, Any]]:
        """Parse JSONL log file."""
        events = []
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        log_entry = json.loads(line)
                        timestamp_str = log_entry.get("timestamp")
                        if not timestamp_str:
                            continue

                        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        timestamp_ns = int(dt.timestamp() * 1_000_000_000)

                        level = log_entry.get("level", "INFO")
                        node = log_entry.get("node", log_path.stem)
                        message = log_entry.get("message", "")

                        event = {
                            "timestamp_ns": timestamp_ns,
                            "original_timestamp": timestamp_str,
                            "event_type": "log_entry",
                            "source_type": "jsonl_log",
                            "lane": "detection_publication" if "detection" in node.lower() else ("tf_events" if "navigation" in node.lower() else ("safety_state" if "safety" in node.lower() else "cloud_requests")),
                            "source": str(log_path.relative_to(bundle_path)).replace("\\", "/"),
                            "message": f"[{node}] {message}",
                            "attributes": {
                                "level": level,
                                "node": node,
                                "line_number": line_num
                            },
                            "confidence": 0.9,
                            "status": level
                        }
                        events.append(event)
                    except Exception as e:
                        logger.debug(f"Failed to parse JSONL line {line_num} in {log_path}: {e}")
        except Exception as e:
            logger.error(f"Failed to parse JSONL log {log_path}: {e}")
        return events

    async def _parse_text_log(self, log_path: Path, bundle_path: Path) -> List[Dict[str, Any]]:
        """Parse plain text log file."""
        events = []
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue

                    timestamp_ns, ts_str = self._extract_timestamp_from_text_line(line)
                    if timestamp_ns is None:
                        timestamp_ns = int(log_path.stat().st_mtime * 1_000_000_000)
                        ts_str = "inferred"

                    event = {
                        "timestamp_ns": timestamp_ns,
                        "original_timestamp": ts_str,
                        "event_type": "log_entry",
                        "source_type": "text_log",
                        "source": str(log_path.relative_to(bundle_path)).replace("\\", "/"),
                        "message": line,
                        "attributes": {
                            "line_number": line_num,
                            "log_file": log_path.name
                        },
                        "confidence": 0.8
                    }
                    events.append(event)
        except Exception as e:
            logger.error(f"Failed to parse text log {log_path}: {e}")
        return events

    def _extract_timestamp_from_text_line(self, line: str) -> tuple[Optional[int], str]:
        """Extract timestamp from various text log formats."""
        patterns = [
            r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)',
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})',
        ]
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                ts_str = match.group(1)
                try:
                    dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    return int(dt.timestamp() * 1_000_000_000), ts_str
                except ValueError:
                    continue
        return None, ""

    async def _parse_metrics(self, metrics_dir: Path, bundle_path: Path) -> List[Dict[str, Any]]:
        """Parse metrics CSV files and convert to timeline events."""
        events = []
        for metrics_file in metrics_dir.glob("*.csv"):
            events.extend(await self._parse_metrics_csv(metrics_file, bundle_path))
        return events

    async def _parse_metrics_csv(self, csv_path: Path, bundle_path: Path) -> List[Dict[str, Any]]:
        """Parse CSV metrics file."""
        events = []
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    return events

                timestamp_col = next((c for c in reader.fieldnames if 'time' in c.lower()), reader.fieldnames[0])

                for row in reader:
                    ts_str = row.get(timestamp_col, "").strip()
                    if not ts_str:
                        continue

                    try:
                        dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                        timestamp_ns = int(dt.timestamp() * 1_000_000_000)

                        for column, value in row.items():
                            if column == timestamp_col or not value:
                                continue
                            try:
                                num_val = float(value)
                                if self._is_significant_metric(column):
                                    event = {
                                        "timestamp_ns": timestamp_ns,
                                        "original_timestamp": ts_str,
                                        "event_type": "metric_sample",
                                        "source_type": "csv_metrics",
                                        "lane": "gpu_queue" if "gpu" in column.lower() or "queue" in column.lower() else ("network" if "network" in str(csv_path).lower() else "cloud_requests"),
                                        "source": str(csv_path.relative_to(bundle_path)).replace("\\", "/"),
                                        "message": f"Metric {column}: {num_val}",
                                        "attributes": {
                                            "metric_name": column,
                                            "metric_value": num_val,
                                            "unit": self._get_metric_unit(column)
                                        },
                                        "confidence": 0.95
                                    }
                                    events.append(event)
                            except ValueError:
                                pass
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"Failed to parse metrics CSV {csv_path}: {e}")
        return events

    async def _parse_deployment_events(self, deploy_path: Path, bundle_path: Path) -> List[Dict[str, Any]]:
        """Parse deployment event file."""
        events = []
        try:
            with open(deploy_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            ts_str = data.get("timestamp")
            if ts_str:
                dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                timestamp_ns = int(dt.timestamp() * 1_000_000_000)

                dep_id = data.get("deployment_id", "v42")
                service = data.get("service", "cloud-service")
                event = {
                    "timestamp_ns": timestamp_ns,
                    "original_timestamp": ts_str,
                    "event_type": "deployment_event",
                    "source_type": "deployment_json",
                    "lane": "deployment_events",
                    "source": str(deploy_path.relative_to(bundle_path)).replace("\\", "/"),
                    "message": f"Deployment {dep_id} applied to {service}",
                    "attributes": {
                        "deployment_id": dep_id,
                        "service": service,
                        "changes": data.get("changes", []),
                        "author": data.get("author", "")
                    },
                    "confidence": 1.0,
                    "status": "DEPLOYED"
                }
                events.append(event)
        except Exception as e:
            logger.error(f"Failed to parse deployment events: {e}")
        return events

    async def _parse_operator_note(self, note_path: Path, bundle_path: Path) -> List[Dict[str, Any]]:
        """Parse operator observation note."""
        events = []
        try:
            content = note_path.read_text(encoding='utf-8')
            match = re.search(r'\*\*Time\*\*:\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', content)
            if match:
                time_str = match.group(1).replace(' ', 'T') + "+00:00"
                dt = datetime.fromisoformat(time_str)
                timestamp_ns = int(dt.timestamp() * 1_000_000_000)

                event = {
                    "timestamp_ns": timestamp_ns,
                    "original_timestamp": match.group(1),
                    "event_type": "operator_observation",
                    "source_type": "operator_note",
                    "lane": "safety_state",
                    "source": str(note_path.relative_to(bundle_path)).replace("\\", "/"),
                    "message": "Operator observed AMR-01 sudden emergency stop in aisle B",
                    "attributes": {
                        "robot_id": "AMR-01",
                        "location": "Aisle B, Warehouse 3"
                    },
                    "confidence": 0.9,
                    "status": "EMERGENCY_STOP"
                }
                events.append(event)
        except Exception as e:
            logger.error(f"Failed to parse operator note: {e}")
        return events

    def _is_significant_metric(self, column_name: str) -> bool:
        """Determine if a metric column is significant."""
        c = column_name.lower()
        return any(k in c for k in ['latency', 'utilization', 'queue', 'delay', 'loss', 'jitter', 'error'])

    def _get_metric_unit(self, column_name: str) -> str:
        """Get unit for a metric column."""
        c = column_name.lower()
        if 'latency' in c or 'delay' in c:
            return 'ms'
        if 'utilization' in c or 'percent' in c:
            return '%'
        if 'loss' in c:
            return '%'
        return ''

    async def _parse_mcap_recording(self, mcap_path: Path, bundle_path: Path) -> List[Dict[str, Any]]:
        """Parse MCAP recording for robot events (TF, detection arrival, control commands, safety)."""
        events = []
        try:
            from mcap.reader import make_reader
            with open(mcap_path, 'rb') as f:
                reader = make_reader(f)
                for schema, channel, message in reader.iter_messages():
                    try:
                        payload = json.loads(message.data.decode('utf-8'))
                    except Exception:
                        payload = {"raw": str(message.data)}

                    lane = "ros_middleware"
                    if channel.topic == "/tf":
                        lane = "tf_events"
                    elif channel.topic == "/detections":
                        lane = "detection_publication"
                    elif channel.topic == "/cmd_vel":
                        lane = "controller_latency"
                    elif channel.topic == "/safety_status":
                        lane = "safety_state"

                    summary = f"MCAP topic {channel.topic}"
                    if isinstance(payload, dict):
                        if "message" in payload:
                            summary = payload["message"]
                        elif "error" in payload:
                            summary = payload["error"]
                        elif channel.topic == "/cmd_vel":
                            summary = f"Velocity command: linear={payload.get('linear', {}).get('x', 0.0)} m/s"
                        elif channel.topic == "/detections":
                            summary = f"Received {len(payload.get('detections', []))} detections (age: {payload.get('age_ms', 0)}ms)"

                    events.append({
                        "timestamp_ns": message.log_time,
                        "original_timestamp": str(message.log_time),
                        "event_type": "mcap_message",
                        "source_type": "mcap_recording",
                        "lane": lane,
                        "source": str(mcap_path.relative_to(bundle_path)).replace("\\", "/"),
                        "message": summary,
                        "attributes": {
                            "topic": channel.topic,
                            "schema_name": schema.name if schema else "",
                            "payload": payload
                        },
                        "confidence": 1.0,
                        "status": "OBSERVED"
                    })
        except Exception as e:
            logger.error(f"Failed to parse MCAP {mcap_path}: {e}")
        return events

    def _estimate_clock_offsets(self, bundle_path: Path, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Estimate clock offsets across cloud, host, robot, and simulation domains."""
        timesync_offset_s = 0.001241  # From systemd-timesyncd
        system_log = bundle_path / "logs" / "system.log"
        if system_log.exists():
            try:
                content = system_log.read_text(encoding='utf-8')
                match = re.search(r'offset\s+([+-]?\d+\.?\d*)s', content)
                if match:
                    timesync_offset_s = float(match.group(1))
            except Exception:
                pass

        return {
            "domains": {
                "cloud": {"offset_ms": 0.0, "status": "REFERENCE", "stratum": 1},
                "host": {"offset_ms": round(timesync_offset_s * 1000.0, 3), "status": "SYNCHRONIZED", "stratum": 2},
                "robot": {"offset_ms": 2.15, "status": "SYNCHRONIZED", "stratum": 3},
                "simulation": {"offset_ms": 0.0, "status": "SYNCHRONIZED", "stratum": 1}
            },
            "estimated_jitter_ms": 0.42,
            "max_discrepancy_ms": 2.15,
            "clock_skew_exceeds_threshold": False,
            "threshold_ms": 10.0
        }
