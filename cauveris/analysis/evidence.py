"""
Evidence loading and normalisation.

Everything Cauveris knows about an incident is read from the incident bundle.
This module turns the raw, heterogeneous bundle contents (manifest, YAML/JSON
configuration, deployment records, JSONL and syslog logs, CSV metric series,
OpenTelemetry traces, MCAP recordings, operator notes and source trees) into
typed records that the analysis layer can reason over.

Nothing in here is incident-specific: the bundle layout is discovered, not
assumed, and every reader degrades gracefully when a file is absent.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)

__all__ = [
    "LogRecord",
    "MetricSample",
    "Span",
    "RecordingMessage",
    "DeploymentEvent",
    "ConfigChange",
    "EvidenceBundle",
    "flatten_config",
    "parse_timestamp",
]


def parse_timestamp(value: Any) -> Optional[datetime]:
    """Parse a timestamp from ISO-8601 text, epoch seconds, or epoch nanos."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        # Heuristic: values large enough are nanoseconds.
        v = float(value)
        if v > 1e17:
            v /= 1e9
        elif v > 1e11:
            v /= 1e3
        return datetime.fromtimestamp(v, tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.replace(".", "", 1).isdigit():
        return parse_timestamp(float(text))
    cleaned = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%b %d %H:%M:%S", "%d/%b/%Y:%H:%M:%S"):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def flatten_config(data: Any, prefix: str = "") -> Dict[str, Any]:
    """
    Flatten a nested configuration mapping into dotted keys.

    ``{"dynamic_batching": {"batching_window_ms": 200}}`` becomes
    ``{"dynamic_batching.batching_window_ms": 200}``.
    """
    flat: Dict[str, Any] = {}
    if not isinstance(data, dict):
        return flat
    for key, value in data.items():
        full = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(flatten_config(value, f"{full}."))
        else:
            flat[full] = value
    return flat


@dataclass
class LogRecord:
    """One normalised log line."""

    timestamp: Optional[datetime]
    source: str
    level: str
    message: str
    fields: Dict[str, Any] = field(default_factory=dict)
    raw: str = ""

    @property
    def text(self) -> str:
        return f"{self.message} {' '.join(str(v) for v in self.fields.values())}"


@dataclass
class MetricSample:
    """One row of a CSV metric series."""

    timestamp: Optional[datetime]
    source: str
    values: Dict[str, float]

    def get(self, *names: str) -> Optional[float]:
        for name in names:
            if name in self.values:
                return self.values[name]
        return None


@dataclass
class Span:
    """One OpenTelemetry span."""

    name: str
    timestamp_ns: int
    duration_ns: int
    attributes: Dict[str, Any] = field(default_factory=dict)
    status: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""

    @property
    def duration_ms(self) -> float:
        return self.duration_ns / 1e6

    @property
    def timestamp(self) -> Optional[datetime]:
        return parse_timestamp(self.timestamp_ns)


@dataclass
class RecordingMessage:
    """One MCAP recording message."""

    topic: str
    log_time_ns: int
    data: Dict[str, Any]

    @property
    def timestamp(self) -> Optional[datetime]:
        return parse_timestamp(self.log_time_ns)


@dataclass
class ConfigChange:
    """A single configuration value change carried by a deployment event."""

    file: str
    key: str
    old_value: Any
    new_value: Any
    description: str = ""

    @property
    def numeric(self) -> Optional[Tuple[float, float]]:
        try:
            return float(self.old_value), float(self.new_value)
        except (TypeError, ValueError):
            return None

    @property
    def ratio(self) -> Optional[float]:
        pair = self.numeric
        if not pair or pair[0] == 0:
            return None
        return pair[1] / pair[0]

    @property
    def direction(self) -> str:
        pair = self.numeric
        if not pair:
            return "changed"
        if pair[1] > pair[0]:
            return "increased"
        if pair[1] < pair[0]:
            return "decreased"
        return "unchanged"


@dataclass
class DeploymentEvent:
    """A deployment / rollout record."""

    deployment_id: str
    timestamp: Optional[datetime]
    service: str = ""
    author: str = ""
    image: str = ""
    changes: List[ConfigChange] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def numeric_changes(self) -> List[ConfigChange]:
        return [c for c in self.changes if c.numeric is not None]


class EvidenceBundle:
    """
    A loaded incident bundle.

    The loader searches the bundle for the known artefact *categories* rather
    than hard-coding their file names, so a bundle that names its metrics file
    differently is still understood.
    """

    _METRIC_HINTS = ("gpu", "metric", "telemetry", "resource", "system", "network", "perf")
    _LOG_HINTS = ("log", "event", "journal")
    _TRACE_HINTS = ("trace", "otel", "span")
    _RECORDING_HINTS = ("recording", "mcap", "bag", "rosbag")
    _CONFIG_HINTS = ("config", "param", "yaml", "settings")

    def __init__(self, root: Path):
        self.root = Path(root)
        self.manifest: Dict[str, Any] = {}
        self.config: Dict[str, Any] = {}
        self.config_sources: Dict[str, str] = {}
        self.deployments: List[DeploymentEvent] = []
        self.logs: List[LogRecord] = []
        self.metrics: Dict[str, List[MetricSample]] = {}
        self.spans: List[Span] = []
        self.recordings: List[RecordingMessage] = []
        self.operator_notes: str = ""
        self.source_files: Dict[str, str] = {}
        self.load_errors: List[str] = []

    # ------------------------------------------------------------------ load

    @classmethod
    def load(cls, root: Path) -> "EvidenceBundle":
        """Load and normalise every artefact found under ``root``."""
        bundle = cls(root)
        if not bundle.root.is_dir():
            raise FileNotFoundError(f"Incident bundle not found: {root}")

        bundle._load_manifest()
        bundle._load_configs()
        bundle._load_deployments()
        bundle._load_logs()
        bundle._load_metrics()
        bundle._load_traces()
        bundle._load_recordings()
        bundle._load_notes()
        bundle._load_sources()

        logger.info(
            "Loaded evidence bundle %s: %d logs, %d metric series, %d spans, "
            "%d recording messages, %d deployments, %d config keys",
            bundle.root,
            len(bundle.logs),
            len(bundle.metrics),
            len(bundle.spans),
            len(bundle.recordings),
            len(bundle.deployments),
            len(bundle.config),
        )
        return bundle

    # ---------------------------------------------------------------- pieces

    def _iter_files(self) -> List[Path]:
        return [p for p in sorted(self.root.rglob("*")) if p.is_file()]

    def _relative(self, path: Path) -> str:
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()

    def _load_manifest(self) -> None:
        for candidate in ("manifest.yaml", "manifest.yml", "manifest.json"):
            path = self.root / candidate
            if not path.exists():
                continue
            try:
                if candidate.endswith(".json"):
                    self.manifest = json.loads(path.read_text(encoding="utf-8"))
                else:
                    self.manifest = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception as exc:
                self.load_errors.append(f"manifest parse failed: {exc}")
            break

    def _load_configs(self) -> None:
        """Read every YAML/JSON file that plausibly carries configuration."""
        for path in self._iter_files():
            rel = self._relative(path)
            suffix = path.suffix.lower()
            if suffix not in (".yaml", ".yml", ".json"):
                continue
            lowered = rel.lower()
            if any(part in lowered for part in ("/media/", "deployment", "/evidence/")):
                continue
            if suffix == ".json" and "deploy" in lowered:
                continue
            if not any(hint in lowered for hint in self._CONFIG_HINTS) and "config" not in lowered:
                # JSON files in the source tree are code, not configuration.
                if suffix == ".json":
                    continue
            try:
                if suffix == ".json":
                    data = json.loads(path.read_text(encoding="utf-8"))
                else:
                    data = yaml.safe_load(path.read_text(encoding="utf-8"))
            except Exception as exc:
                self.load_errors.append(f"config parse failed ({rel}): {exc}")
                continue
            if not isinstance(data, dict):
                continue
            flat = flatten_config(data)
            if not flat:
                continue
            self.config_sources[rel] = rel
            for key, value in flat.items():
                # First writer wins so the most specific config file wins over
                # generic ones; later files fill in gaps only.
                self.config.setdefault(key, value)

    def _load_deployments(self) -> None:
        """Read deployment/rollout records."""
        for path in self._iter_files():
            rel = self._relative(path)
            if "deploy" not in rel.lower():
                continue
            if path.suffix.lower() not in (".json", ".yaml", ".yml"):
                continue
            try:
                if path.suffix.lower() == ".json":
                    raw = json.loads(path.read_text(encoding="utf-8"))
                else:
                    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            except Exception as exc:
                self.load_errors.append(f"deployment parse failed ({rel}): {exc}")
                continue

            records: List[Any] = []
            if isinstance(raw, list):
                records = raw
            elif isinstance(raw, dict):
                # Either a single deployment, or a list under a known key.
                for key in ("deployments", "events", "history"):
                    if isinstance(raw.get(key), list):
                        records = raw[key]
                        break
                else:
                    records = [raw]

            for record in records:
                if not isinstance(record, dict):
                    continue
                event = DeploymentEvent(
                    deployment_id=str(
                        record.get("deployment_id")
                        or record.get("id")
                        or record.get("version")
                        or "unknown"
                    ),
                    timestamp=parse_timestamp(
                        record.get("timestamp") or record.get("time") or record.get("date")
                    ),
                    service=str(record.get("service", "")),
                    author=str(record.get("author", "")),
                    image=str(record.get("image", "")),
                    raw=record,
                )
                event.changes.extend(self._extract_changes(record))
                self.deployments.append(event)

        self.deployments.sort(key=lambda d: d.timestamp or datetime.min.replace(tzinfo=timezone.utc))

    @staticmethod
    def _extract_changes(record: Dict[str, Any]) -> List[ConfigChange]:
        """Extract configuration changes from the various shapes seen in the wild."""
        changes: List[ConfigChange] = []

        raw_changes = record.get("changes")
        if isinstance(raw_changes, list):
            for change in raw_changes:
                if not isinstance(change, dict):
                    continue
                file = str(change.get("file", ""))
                desc = str(change.get("change", "") or change.get("description", ""))
                old = change.get("old_value", change.get("from"))
                new = change.get("new_value", change.get("to"))
                key = str(change.get("key", change.get("parameter", "")))
                if not key:
                    # Derive the key from the description, e.g.
                    # "batching_window_ms increased from 100 to 200".
                    match = re.search(r"([A-Za-z0-9_.\-]+)\s+(?:increased|decreased|changed|set)", desc)
                    key = match.group(1) if match else ""
                if key or desc:
                    changes.append(
                        ConfigChange(
                            file=file,
                            key=key,
                            old_value=old,
                            new_value=new,
                            description=desc,
                        )
                    )

        raw_config = record.get("config")
        if isinstance(raw_config, dict):
            for key, value in raw_config.items():
                if isinstance(value, dict):
                    old = value.get("from", value.get("old_value"))
                    new = value.get("to", value.get("new_value"))
                else:
                    old = None
                    new = value
                changes.append(
                    ConfigChange(
                        file=str(record.get("file", "")),
                        key=str(key),
                        old_value=old,
                        new_value=new,
                        description=f"{key} changed",
                    )
                )
        return changes

    def _load_logs(self) -> None:
        """Read JSONL and syslog-style log files."""
        for path in self._iter_files():
            rel = self._relative(path)
            lowered = rel.lower()
            if "/media/" in lowered or "/source/" in lowered:
                continue
            if path.suffix.lower() == ".jsonl":
                self._load_jsonl_logs(path, rel)
            elif path.suffix.lower() == ".log":
                self._load_text_logs(path, rel)

    def _load_jsonl_logs(self, path: Path, rel: str) -> None:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            self.load_errors.append(f"log read failed ({rel}): {exc}")
            return
        for lineno, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                self.logs.append(
                    LogRecord(
                        timestamp=None,
                        source=rel,
                        level="INFO",
                        message=line,
                        raw=line,
                    )
                )
                continue
            if not isinstance(record, dict):
                continue
            message = str(
                record.get("message")
                or record.get("msg")
                or record.get("event")
                or record.get("text")
                or ""
            )
            # Flatten the remaining fields so pattern matching can see them.
            fields = {
                k: v
                for k, v in record.items()
                if k not in ("timestamp", "ts", "time", "message", "msg", "level", "severity")
            }
            self.logs.append(
                LogRecord(
                    timestamp=parse_timestamp(
                        record.get("timestamp") or record.get("ts") or record.get("time")
                    ),
                    source=rel,
                    level=str(record.get("level") or record.get("severity") or "INFO").upper(),
                    message=message,
                    fields=fields,
                    raw=line,
                )
            )

    _SYSLOG_RE = re.compile(
        r"^(?P<ts>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+(?P<host>\S+)\s+"
        r"(?P<proc>[\w\-./\[\]]+):\s*(?P<msg>.*)$"
    )

    def _load_text_logs(self, path: Path, rel: str) -> None:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            self.load_errors.append(f"log read failed ({rel}): {exc}")
            return
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            match = self._SYSLOG_RE.match(line)
            if match:
                self.logs.append(
                    LogRecord(
                        timestamp=None,  # syslog has no year; resolution handled downstream
                        source=rel,
                        level="INFO",
                        message=match.group("msg"),
                        fields={"host": match.group("host"), "process": match.group("proc")},
                        raw=line,
                    )
                )
                continue
            level = "INFO"
            for candidate in ("CRITICAL", "ERROR", "WARNING", "WARN", "DEBUG"):
                if candidate in line.upper():
                    level = candidate if candidate != "WARN" else "WARNING"
                    break
            self.logs.append(
                LogRecord(
                    timestamp=None,
                    source=rel,
                    level=level,
                    message=line,
                    raw=line,
                )
            )

    def _load_metrics(self) -> None:
        """Read CSV metric series."""
        for path in self._iter_files():
            if path.suffix.lower() != ".csv":
                continue
            rel = self._relative(path)
            try:
                rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
            except Exception as exc:
                self.load_errors.append(f"metrics parse failed ({rel}): {exc}")
                continue
            if not rows:
                continue
            series: List[MetricSample] = []
            for row in rows:
                values: Dict[str, float] = {}
                ts_value = None
                for key, raw in row.items():
                    if key is None:
                        continue
                    if key.lower() in ("timestamp", "time", "ts", "date"):
                        ts_value = raw
                        continue
                    try:
                        values[key] = float(raw)
                    except (TypeError, ValueError):
                        continue
                if not values:
                    continue
                series.append(
                    MetricSample(
                        timestamp=parse_timestamp(ts_value),
                        source=rel,
                        values=values,
                    )
                )
            if series:
                self.metrics[rel] = series

    def _load_traces(self) -> None:
        """Read OpenTelemetry-style trace exports."""
        for path in self._iter_files():
            if path.suffix.lower() != ".json":
                continue
            rel = self._relative(path)
            if "trace" not in rel.lower() and "otel" not in rel.lower() and "span" not in rel.lower():
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                self.load_errors.append(f"trace parse failed ({rel}): {exc}")
                continue
            for span in self._iter_spans(raw):
                self.spans.append(span)

    def _iter_spans(self, raw: Any):
        """Yield every :class:`Span` found in an arbitrarily shaped trace file."""
        if isinstance(raw, list):
            for item in raw:
                yield from self._iter_spans(item)
        elif isinstance(raw, dict):
            if "spans" in raw and isinstance(raw["spans"], list):
                trace_id = str(raw.get("traceID") or raw.get("traceId") or "")
                for span in raw["spans"]:
                    if not isinstance(span, dict):
                        continue
                    yield Span(
                        name=str(span.get("name", "")),
                        timestamp_ns=int(
                            span.get("timestamp", span.get("startTimeUnixNano", 0)) or 0
                        ),
                        duration_ns=int(span.get("duration", 0) or 0),
                        attributes=dict(span.get("attributes", {}) or {}),
                        status=dict(span.get("status", {}) or {}),
                        trace_id=trace_id,
                    )
            else:
                for value in raw.values():
                    if isinstance(value, (list, dict)):
                        yield from self._iter_spans(value)

    def _load_recordings(self) -> None:
        """Read MCAP recordings (ROS 2 topic bags)."""
        try:
            from mcap.reader import make_reader
        except Exception:  # pragma: no cover - mcap is a hard dependency
            return
        for path in self._iter_files():
            if path.suffix.lower() != ".mcap":
                continue
            rel = self._relative(path)
            try:
                with open(path, "rb") as handle:
                    reader = make_reader(handle)
                    for schema, channel, message in reader.iter_messages():
                        payload: Dict[str, Any] = {}
                        try:
                            payload = json.loads(message.data.decode("utf-8"))
                        except Exception:
                            payload = {"_raw": message.data[:256].hex()}
                        self.recordings.append(
                            RecordingMessage(
                                topic=getattr(channel, "topic", ""),
                                log_time_ns=int(getattr(message, "log_time", 0) or 0),
                                data=payload if isinstance(payload, dict) else {"value": payload},
                            )
                        )
            except Exception as exc:
                self.load_errors.append(f"mcap read failed ({rel}): {exc}")

    def _load_notes(self) -> None:
        """Read operator notes / README prose."""
        for path in self._iter_files():
            lowered = self._relative(path).lower()
            if not any(
                hint in lowered for hint in ("observation", "note", "readme", "report", "postmortem")
            ):
                continue
            if path.suffix.lower() not in (".md", ".txt", ".rst"):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace").strip()
            except Exception:
                continue
            if text:
                self.operator_notes += f"\n--- {self._relative(path)} ---\n{text}"

    def _load_sources(self) -> None:
        """Index the source tree shipped with the bundle."""
        for path in self._iter_files():
            rel = self._relative(path)
            if not rel.startswith("source/"):
                continue
            if path.stat().st_size > 2_000_000:
                continue
            try:
                self.source_files[rel] = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

    # --------------------------------------------------------------- queries

    def config_value(self, *keys: str) -> Any:
        """Return the first present config value among ``keys`` (dotted paths)."""
        for key in keys:
            if key in self.config:
                return self.config[key]
        return None

    def numeric_config(self, *keys: str) -> Optional[float]:
        """Return a config value coerced to float, or None."""
        value = self.config_value(*keys)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def logs_matching(self, pattern: str) -> List[LogRecord]:
        """Return log records whose text matches ``pattern`` (case-insensitive)."""
        regex = re.compile(pattern, re.IGNORECASE)
        return [rec for rec in self.logs if regex.search(rec.text)]

    def metric_series(self, *names: str) -> List[Tuple[str, MetricSample]]:
        """Return (series_name, sample) pairs for any series exposing ``names``."""
        out: List[Tuple[str, MetricSample]] = []
        for series_name, samples in self.metrics.items():
            for sample in samples:
                if sample.get(*names) is not None:
                    out.append((series_name, sample))
                    break
        return out

    def metric_values(self, *names: str) -> List[float]:
        """Return every numeric value of the first metric series exposing ``names``."""
        for series_name, samples in self.metrics.items():
            values = [s.get(*names) for s in samples]
            filtered = [v for v in values if v is not None]
            if filtered:
                return filtered
        return []

    def spans_named(self, *substrings: str) -> List[Span]:
        return [s for s in self.spans if any(sub in s.name for sub in substrings)]

    def recording_messages(self, *topics: str) -> List[RecordingMessage]:
        if not topics:
            return list(self.recordings)
        return [m for m in self.recordings if any(t in m.topic for t in topics)]
