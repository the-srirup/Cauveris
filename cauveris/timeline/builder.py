"""
Timeline builder for normalizing and aligning evidence.
"""
import logging
import json
import csv
from datetime import datetime, timezone
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

    async def build(self, incident: Incident) -> Incident:
        """
        Build a synchronized timeline from evidence.

        Args:
            incident: Incident with validated evidence

        Returns:
            Incident with timeline data attached
        """
        logger.info(f"Building timeline for incident {incident.id}")

        # Find the bundle directory
        bundle_path = Path("./incident-CAU-0001")
        if not bundle_path.exists():
            logger.warning("Bundle directory not found, returning incident with empty timeline")
            # DEBUG: Add information about the incident object
            logger.error(f"DEBUG: Incident type: {type(incident)}")
            logger.error(f"DEBUG: Incident module: {type(incident).__module__}")
            logger.error(f"DEBUG: Has timeline_events: {hasattr(incident, 'timeline_events')}")
            if hasattr(incident, '__dict__'):
                logger.error(f"DEBUG: Incident __dict__ keys: {list(incident.__dict__.keys())}")
            logger.error(f"DEBUG: Dir contains timeline_events: {'timeline_events' in dir(incident)}")
            incident.timeline_events = []
            return incident

        # Parse all available evidence sources
        timeline_events = []

        # Parse OpenTelemetry traces
        trace_events = await self._parse_otel_traces(bundle_path / "traces" / "otel.json")
        timeline_events.extend(trace_events)

        # Parse logs
        log_events = await self._parse_logs(bundle_path / "logs")
        timeline_events.extend(log_events)

        # Parse metrics (convert to events at sample points)
        metric_events = await self._parse_metrics(bundle_path / "metrics")
        timeline_events.extend(metric_events)

        # Sort events by timestamp
        timeline_events.sort(key=lambda x: x.get("timestamp_ns", 0))

        # Normalize timestamps to a common base (use earliest event as base)
        if timeline_events:
            base_time = min(event.get("timestamp_ns", 0) for event in timeline_events)
            for event in timeline_events:
                if "timestamp_ns" in event:
                    # Convert to relative nanoseconds from base
                    event["relative_timestamp_ns"] = event["timestamp_ns"] - base_time

        incident.timeline_events = timeline_events
        logger.info(f"Built timeline with {len(timeline_events)} events")
        return incident

    async def _parse_otel_traces(self, otel_path: Path) -> List[Dict[str, Any]]:
        """Parse OpenTelemetry JSON trace file."""
        events = []
        if not otel_path.exists():
            return events

        try:
            with open(otel_path, 'r') as f:
                trace_data = json.load(f)

            for span in trace_data.get("spans", []):
                # Convert timestamp to nanoseconds
                timestamp_ns = int(span.get("timestamp", "0"))

                event = {
                    "timestamp_ns": timestamp_ns,
                    "original_timestamp": span.get("timestamp"),
                    "event_type": "trace_span",
                    "source_type": "otel_trace",
                    "source": str(otel_path.relative_to(Path("./incident-CAU-0001"))),
                    "message": span.get("name", ""),
                    "attributes": {
                        "span_id": span.get("spanID"),
                        "trace_id": span.get("traceID"),
                        "parent_span_id": span.get("parentSpanID"),
                        "kind": span.get("kind"),
                        "duration": span.get("duration"),
                    },
                    "trace_id": span.get("traceID"),
                    "span_id": span.get("spanID"),
                    "confidence": 0.9,  # High confidence for trace data
                    "status": span.get("status", {}).get("message", "") if isinstance(span.get("status"), dict) else ""
                }

                # Add any attributes from the span
                if "attributes" in span:
                    event["attributes"].update(span["attributes"])

                # Add events within the span
                for span_event in span.get("events", []):
                    event_timestamp = timestamp_ns + int(span_event.get("timestamp", "0"))
                    sub_event = event.copy()
                    sub_event["timestamp_ns"] = event_timestamp
                    sub_event["message"] = f"{event['message']}: {span_event.get('name', '')}"
                    sub_event["attributes"].update(span_event.get("attributes", {}))
                    events.append(sub_event)

                events.append(event)

        except Exception as e:
            logger.error(f"Failed to parse OTel traces: {e}")

        return events

    async def _parse_logs(self, logs_dir: Path) -> List[Dict[str, Any]]:
        """Parse log files (JSONL and plain text)."""
        events = []
        if not logs_dir.exists():
            return events

        # Process JSONL logs
        for log_file in logs_dir.glob("*.jsonl"):
            events.extend(await self._parse_jsonl_log(log_file))

        # Process plain text logs
        for log_file in logs_dir.glob("*.log"):
            events.extend(await self._parse_text_log(log_file))

        return events

    async def _parse_jsonl_log(self, log_path: Path) -> List[Dict[str, Any]]:
        """Parse JSONL log file."""
        events = []
        try:
            with open(log_path, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        log_entry = json.loads(line)
                        timestamp_str = log_entry.get("timestamp")
                        if not timestamp_str:
                            continue

                        # Parse ISO timestamp
                        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        timestamp_ns = int(dt.timestamp() * 1_000_000_000)

                        event = {
                            "timestamp_ns": timestamp_ns,
                            "original_timestamp": timestamp_str,
                            "event_type": "log_entry",
                            "source_type": "jsonl_log",
                            "source": str(log_path.relative_to(Path("./incident-CAU-0001"))),
                            "message": log_entry.get("message", ""),
                            "attributes": {
                                "level": log_entry.get("level", ""),
                                "line_number": line_num
                            },
                            "confidence": 0.8,
                            "status": log_entry.get("level", "")
                        }
                        events.append(event)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSONL line {line_num} in {log_path}")
                    except Exception as e:
                        logger.warning(f"Failed to parse log line {line_num} in {log_path}: {e}")
        except Exception as e:
            logger.error(f"Failed to parse JSONL log {log_path}: {e}")

        return events

    async def _parse_text_log(self, log_path: Path) -> List[Dict[str, Any]]:
        """Parse plain text log file."""
        events = []
        try:
            with open(log_path, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue

                    # Try to extract timestamp from common log formats
                    timestamp_ns = self._extract_timestamp_from_text_line(line)
                    if timestamp_ns is None:
                        # If no timestamp found, use file modification time as fallback
                        timestamp_ns = int(log_path.stat().st_mtime * 1_000_000_000)

                    event = {
                        "timestamp_ns": timestamp_ns,
                        "original_timestamp": line[:50] + "..." if len(line) > 50 else line,
                        "event_type": "log_entry",
                        "source_type": "text_log",
                        "source": str(log_path.relative_to(Path("./incident-CAU-0001"))),
                        "message": line,
                        "attributes": {
                            "line_number": line_num,
                            "log_file": log_path.name
                        },
                        "confidence": 0.6 if timestamp_ns == int(log_path.stat().st_mtime * 1_000_000_000) else 0.7
                    }
                    events.append(event)
        except Exception as e:
            logger.error(f"Failed to parse text log {log_path}: {e}")

        return events

    def _extract_timestamp_from_text_line(self, line: str) -> Optional[int]:
        """Extract timestamp from various text log formats."""
        # Common timestamp patterns
        patterns = [
            r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.?\d*)',  # ISO format
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})',       # Space-separated
            r'(\d{2}:\d{2}:\d{2}\.\d+)',                    # HH:MM:SS.mmm
        ]

        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                try:
                    timestamp_str = match.group(1)
                    # Try parsing as ISO format first
                    if 'T' in timestamp_str or '-' in timestamp_str:
                        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    else:
                        # Assume it's HH:MM:SS and today's date
                        today = datetime.now(timezone.utc).date()
                        time_part = datetime.strptime(timestamp_str, '%H:%M:%S.%f' if '.' in timestamp_str else '%H:%M:%S')
                        dt = datetime.combine(today, time_part.time()).replace(tzinfo=timezone.utc)

                    return int(dt.timestamp() * 1_000_000_000)
                except ValueError:
                    continue

        return None

    async def _parse_metrics(self, metrics_dir: Path) -> List[Dict[str, Any]]:
        """Parse metrics CSV files and convert to timeline events."""
        events = []
        if not metrics_dir.exists():
            return events

        for metrics_file in metrics_dir.glob("*.csv"):
            events.extend(await self._parse_metrics_csv(metrics_file))

        return events

    async def _parse_metrics_csv(self, csv_path: Path) -> List[Dict[str, Any]]:
        """Parse CSV metrics file."""
        events = []
        try:
            with open(csv_path, 'r') as f:
                # Sniff the dialect
                sample = f.read(1024)
                f.seek(0)
                sniffer = csv.Sniffer()
                delimiter = sniffer.sniff(sample).delimiter if sniffer.has_header(sample) else ','

                reader = csv.DictReader(f, delimiter=delimiter)
                if not reader.fieldnames:
                    return events

                # Find timestamp column
                timestamp_col = None
                for col in reader.fieldnames:
                    if 'time' in col.lower() or 'timestamp' in col.lower():
                        timestamp_col = col
                        break

                if not timestamp_col:
                    # Use first column as timestamp
                    timestamp_col = reader.fieldnames[0] if reader.fieldnames else None

                if not timestamp_col:
                    return events

                for row_num, row in enumerate(reader, 1):
                    try:
                        timestamp_str = row.get(timestamp_col, "").strip()
                        if not timestamp_str:
                            continue

                        # Parse timestamp
                        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        timestamp_ns = int(dt.timestamp() * 1_000_000_000)

                        # Create events for key metrics
                        for column, value in row.items():
                            if column == timestamp_col:
                                continue

                            # Skip empty values
                            if not value or value.strip() == '':
                                continue

                            # Try to convert to numeric for meaningful events
                            try:
                                numeric_value = float(value)
                                # Only create events for significant changes or key metrics
                                if self._is_significant_metric(column, numeric_value):
                                    event = {
                                        "timestamp_ns": timestamp_ns,
                                        "original_timestamp": timestamp_str,
                                        "event_type": "metric_sample",
                                        "source_type": "csv_metrics",
                                        "source": str(csv_path.relative_to(Path("./incident-CAU-0001"))),
                                        "message": f"{column}: {value}",
                                        "attributes": {
                                            "metric_name": column,
                                            "metric_value": numeric_value,
                                            "unit": self._get_metric_unit(column)
                                        },
                                        "confidence": 0.9
                                    }
                                    events.append(event)
                            except ValueError:
                                # Non-numeric metric, still create event if it seems important
                                if self._is_important_string_metric(column, value):
                                    event = {
                                        "timestamp_ns": timestamp_ns,
                                        "original_timestamp": timestamp_str,
                                        "event_type": "metric_sample",
                                        "source_type": "csv_metrics",
                                        "source": str(csv_path.relative_to(Path("./incident-CAU-0001"))),
                                        "message": f"{column}: {value}",
                                        "attributes": {
                                            "metric_name": column,
                                            "metric_value": value
                                        },
                                        "confidence": 0.8
                                    }
                                    events.append(event)

                    except Exception as e:
                        logger.debug(f"Failed to parse metrics row {row_num} in {csv_path}: {e}")
                        continue

        except Exception as e:
            logger.error(f"Failed to parse metrics CSV {csv_path}: {e}")

        return events

    def _is_significant_metric(self, column_name: str, value: float) -> bool:
        """Determine if a metric value is significant enough to create an event."""
        column_lower = column_name.lower()

        # Always include latency and utilization metrics
        if any(key in column_lower for key in ['latency', 'utilization', 'usage', 'percent']):
            return True

        # Include error rates and counts
        if any(key in column_lower for key in ['error', 'count', 'drop', 'fail']):
            return True

        # Include temperature and power
        if any(key in column_lower for key in ['temp', 'power', 'voltage', 'current']):
            return True

        # For GPU metrics, include key ones
        if 'gpu' in column_lower:
            return True

        return False

    def _is_important_string_metric(self, column_name: str, value: str) -> bool:
        """Determine if a string metric is important enough to create an event."""
        column_lower = column_name.lower()
        _value_lower = value.lower()

        # Include status changes
        if any(key in column_lower for key in ['status', 'state', 'mode']):
            return True

        # Include version info
        if any(key in column_lower for key in ['version', 'build', 'commit']):
            return True

        return False

    def _get_metric_unit(self, column_name: str) -> str:
        """Get unit for a metric column."""
        column_lower = column_name.lower()

        if 'latency' in column_lower or 'delay' in column_lower:
            return 'ms'
        elif 'utilization' in column_lower or 'usage' in column_lower or 'percent' in column_lower:
            return '%'
        elif 'temp' in column_lower:
            return '°C'
        elif 'power' in column_lower:
            return 'W'
        elif 'voltage' in column_lower:
            return 'V'
        elif 'current' in column_lower:
            return 'A'
        elif 'frequency' in column_lower or 'hz' in column_lower:
            return 'Hz'
        elif 'bytes' in column_lower:
            return 'bytes'
        elif 'count' in column_lower:
            return 'count'
        else:
            return ''
