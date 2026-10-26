"""
Evidence loading and normalisation.

Everything Cauveris knows about an incident is read from the incident bundle.
This module turns the raw, heterogeneous bundle contents (manifest, YAML/JSON/
TOML/INI configuration, deployment records, JSONL, syslog and plain-text logs,
CSV and Prometheus metric series, OpenTelemetry traces in JSON and NDJSON,
MCAP recordings, operator notes and source trees) into typed records that the
analysis layer can reason over.

Nothing in here is incident-specific: the bundle layout is discovered, not
assumed, and every reader degrades gracefully when a file is absent.  A bundle
from a company Cauveris has never seen carries whatever formats that company
uses, so the readers recognise the *shape* of a format rather than the name
of a file.
"""

from __future__ import annotations

import configparser
import csv
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

try:  # Python 3.11 ships tomllib; a bundle may carry TOML configuration.
    import tomllib
except ImportError:  # pragma: no cover - only on older interpreters
    tomllib = None  # type: ignore[assignment]

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


#: A line of the Prometheus exposition format:
#: ``name{label="value",other="value"} 12.5 1395066363000``.
_PROMETHEUS_SAMPLE_RE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(?P<labels>[^}]*)\})?\s+"
    r"(?P<value>[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?|Inf|NaN)"
    r"(?:\s+(?P<timestamp>[0-9]+))?$"
)


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

    #: File suffixes that carry log lines.  ``.txt`` and ``.out`` are here
    #: because a bundle captured from a shell redirect or from a console dump
    #: is still a log, whatever it was called.
    _LOG_SUFFIXES = (".log", ".txt", ".out", ".err")
    #: Suffixes that carry one JSON object per line.
    _JSONL_SUFFIXES = (".jsonl", ".ndjson")
    #: Files whose *name* suggests they are prose rather than a log.
    _NOTE_NAME_HINTS = ("observation", "note", "readme", "report", "postmortem")
    #: Name fragments of an extension-less file that make it a log.
    _BARE_LOG_HINTS = ("log", "journal", "stdout", "stderr", "console", "output")

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
        """Read every file that plausibly carries configuration."""
        for path in self._iter_files():
            rel = self._relative(path)
            suffix = path.suffix.lower()
            lowered = rel.lower()
            if any(part in lowered for part in ("/media/", "deployment", "/evidence/")):
                continue
            if suffix == ".json" and "deploy" in lowered:
                continue

            data: Any = None
            if suffix in (".yaml", ".yml", ".json"):
                if suffix == ".json" and not any(
                    hint in lowered for hint in self._CONFIG_HINTS
                ):
                    # JSON files in the source tree are code, not configuration.
                    continue
                try:
                    if suffix == ".json":
                        data = json.loads(path.read_text(encoding="utf-8"))
                    else:
                        data = yaml.safe_load(path.read_text(encoding="utf-8"))
                except Exception as exc:
                    self.load_errors.append(f"config parse failed ({rel}): {exc}")
                    continue
            elif suffix in (".toml", ".ini", ".cfg", ".conf"):
                # A robot's parameters often ship as TOML or INI rather than
                # YAML, and a bundle that carries only those would otherwise be
                # read as having no configuration at all.
                if not self._is_config_candidate(lowered, suffix):
                    continue
                try:
                    data = self._parse_ini_like(path, suffix)
                except Exception as exc:
                    self.load_errors.append(f"config parse failed ({rel}): {exc}")
                    continue
            else:
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

    @classmethod
    def _is_config_candidate(cls, lowered: str, suffix: str) -> bool:
        """
        Whether a TOML/INI file is configuration rather than packaging noise.

        A directory named for configuration is taken at its word; a file at the
        root of the bundle is taken when its own name says so.  ``setup.cfg``
        and ``pyproject.toml`` are packaging files, not the robot's settings.
        """
        stem = lowered.rsplit("/", 1)[-1]
        if stem.startswith(".") or stem in ("setup.cfg", "tox.ini", "pytest.ini"):
            return False
        if stem in ("pyproject.toml", "poetry.lock", "uv.lock", "cargo.toml"):
            return False
        if any(hint in lowered for hint in ("config", "param", "setting")):
            return True
        if "/" not in lowered and any(
            hint in stem for hint in ("config", "param", "setting", "robot", "profile")
        ):
            return True
        return False

    @staticmethod
    def _parse_ini_like(path: Path, suffix: str) -> Dict[str, Any]:
        """Parse a TOML or INI file into a plain mapping."""
        text = path.read_text(encoding="utf-8")
        if suffix == ".toml":
            if tomllib is None:  # pragma: no cover - older interpreters only
                return {}
            data = tomllib.loads(text)
            return data if isinstance(data, dict) else {}
        parser = configparser.ConfigParser(strict=False, interpolation=None)
        parser.read_string(text)
        result: Dict[str, Any] = {}
        for section in parser.sections():
            result[section] = dict(parser.items(section))
        # A key that appears before any section header would be lost by
        # configparser, so it is recovered from the raw text.
        defaults: Dict[str, Any] = {}
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", ";")) or stripped.startswith("["):
                continue
            if "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            if key and key not in defaults:
                defaults[key] = value.strip()
        if defaults:
            for key, value in defaults.items():
                result.setdefault(key, value)
        return result

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
        """
        Read the log files of the bundle, whatever shape they are in.

        Three shapes are recognised: one JSON object per line, a JSON file
        holding an array of records, and plain text - syslog, a console dump,
        or a redirect of a program's output.  A bundle that names its logs
        ``events.ndjson`` or ``stdout.txt`` is as readable as one that calls
        them ``service.log``.
        """
        for path in self._iter_files():
            rel = self._relative(path)
            lowered = rel.lower()
            if "/media/" in lowered or "/source/" in lowered:
                continue
            if any(hint in Path(lowered).name for hint in self._NOTE_NAME_HINTS):
                # Prose about the incident is read as an operator note, not as
                # a log line: reading it twice would double every claim it
                # makes.
                continue
            suffix = path.suffix.lower()
            if suffix in self._JSONL_SUFFIXES:
                self._load_jsonl_logs(path, rel)
            elif suffix in self._LOG_SUFFIXES or self._is_rotated_log(lowered):
                self._load_text_logs(path, rel)
            elif suffix == "" and any(
                hint in Path(lowered).name for hint in self._BARE_LOG_HINTS
            ):
                self._load_text_logs(path, rel)
            elif suffix == ".json" and any(
                hint in lowered for hint in self._LOG_HINTS
            ):
                self._load_json_logs(path, rel)

    @staticmethod
    def _is_rotated_log(lowered: str) -> bool:
        """Whether a file is a rotated log (``service.log.1``, ``service.log.gz``)."""
        name = Path(lowered).name
        if ".log." not in name:
            return False
        tail = name.rsplit(".log.", 1)[-1]
        return bool(tail) and all(part.isdigit() or part in ("gz", "bz2", "xz") for part in tail.split("."))

    def _load_json_logs(self, path: Path, rel: str) -> None:
        """
        Read a JSON file that holds log records.

        The shape is whatever the producer wrote: a list of records, or a
        mapping with the records under one of the usual keys.
        """
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.load_errors.append(f"log parse failed ({rel}): {exc}")
            return
        records: List[Any] = []
        if isinstance(raw, list):
            records = raw
        elif isinstance(raw, dict):
            for key in ("logs", "events", "records", "entries", "messages"):
                value = raw.get(key)
                if isinstance(value, list):
                    records = value
                    break
        if not records:
            return
        # A JSON file that holds no message at all is not a log file; it is
        # some other artefact that happens to live under a ``logs`` directory.
        if not any(
            isinstance(record, dict)
            and any(
                key in record
                for key in ("message", "msg", "event", "text", "log", "level", "severity")
            )
            for record in records
        ):
            return
        for record in records:
            if isinstance(record, dict):
                self._append_json_log_record(record, rel)
            elif isinstance(record, str):
                self.logs.append(
                    LogRecord(timestamp=None, source=rel, level="INFO", message=record, raw=record)
                )

    def _append_json_log_record(
        self, record: Dict[str, Any], rel: str, raw: Optional[str] = None
    ) -> None:
        """Turn one JSON record into a log record."""
        message = str(
            record.get("message")
            or record.get("msg")
            or record.get("event")
            or record.get("text")
            or record.get("log")
            or ""
        )
        if not message:
            # A record with fields but no message is still evidence: it is
            # kept whole, so a pattern that names one of its fields still
            # finds it.
            message = json.dumps(
                {k: v for k, v in record.items() if k not in ("timestamp", "ts", "time")},
                default=str,
            )
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
                raw=raw if raw is not None else json.dumps(record, default=str),
            )
        )

    def _load_jsonl_logs(self, path: Path, rel: str) -> None:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            self.load_errors.append(f"log read failed ({rel}): {exc}")
            return
        for line in text.splitlines():
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
            self._append_json_log_record(record, rel, raw=line)

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
        """Read metric series: CSV tables and Prometheus exposition text."""
        for path in self._iter_files():
            suffix = path.suffix.lower()
            rel = self._relative(path)
            if suffix == ".csv":
                self._load_csv_metrics(path, rel)
            elif suffix in (".prom", ".prometheus") or self._looks_like_prometheus(path):
                self._load_prometheus_metrics(path, rel)

    def _load_csv_metrics(self, path: Path, rel: str) -> None:
        """Read a CSV metric table: one row per sample, one column per series."""
        try:
            rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
        except Exception as exc:
            self.load_errors.append(f"metrics parse failed ({rel}): {exc}")
            return
        if not rows:
            return
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

    @staticmethod
    def _looks_like_prometheus(path: Path) -> bool:
        """
        Whether a file is a Prometheus exposition document.

        The exposition format is identified by its own ``# HELP`` / ``# TYPE``
        comments, which every exporter writes.  A file without them is left
        alone: a stray text file that happens to contain numbers is far more
        likely to be a log than a metric scrape.
        """
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                head = [handle.readline() for _ in range(40)]
        except OSError:
            return False
        for line in head:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                if re.match(r"#\s*(HELP|TYPE)\s+\S", stripped):
                    return True
                continue
            break
        return False

    def _load_prometheus_metrics(self, path: Path, rel: str) -> None:
        """
        Read a Prometheus exposition document into metric samples.

        Each line of the format is ``name{labels} value [timestamp]``.  The
        metric name becomes the column and the label set is kept in it, so a
        scrape that reports the same metric for two processes stays two
        series rather than one series that silently changes meaning.
        """
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            self.load_errors.append(f"metrics read failed ({rel}): {exc}")
            return
        series: List[MetricSample] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = _PROMETHEUS_SAMPLE_RE.match(stripped)
            if match is None:
                continue
            value_text = match.group("value")
            try:
                value = float(value_text)
            except ValueError:
                continue
            if value != value or value in (float("inf"), float("-inf")):
                continue
            name = match.group("name")
            labels = (match.group("labels") or "").strip()
            column = f"{name}{{{labels}}}" if labels else name
            timestamp = match.group("timestamp")
            series.append(
                MetricSample(
                    timestamp=parse_timestamp(timestamp) if timestamp else None,
                    source=rel,
                    values={column: value},
                )
            )
        if series:
            self.metrics[rel] = series

    def _load_traces(self) -> None:
        """
        Read OpenTelemetry-style trace exports.

        Traces arrive as a JSON document, as NDJSON, or as the OTLP structure
        with ``resourceSpans`` and ``scopeSpans``.  A file is read as a trace
        when its name says so, or when its own content carries spans - an
        exporter that names its file ``telemetry.json`` still gets read.
        """
        for path in self._iter_files():
            suffix = path.suffix.lower()
            rel = self._relative(path)
            lowered = rel.lower()
            if suffix == ".json":
                if not any(hint in lowered for hint in self._TRACE_HINTS):
                    continue
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                except Exception as exc:
                    self.load_errors.append(f"trace parse failed ({rel}): {exc}")
                    continue
                for span in self._iter_spans(raw):
                    self.spans.append(span)
            elif suffix in self._JSONL_SUFFIXES:
                if not self._ndjson_carries_spans(path):
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except Exception as exc:
                    self.load_errors.append(f"trace read failed ({rel}): {exc}")
                    continue
                for line in text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    for span in self._iter_spans(raw):
                        self.spans.append(span)

    @staticmethod
    def _ndjson_carries_spans(path: Path) -> bool:
        """Whether an NDJSON file's first records carry spans."""
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for _ in range(5):
                    line = handle.readline().strip()
                    if not line:
                        continue
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError:
                        return False
                    if isinstance(raw, dict) and (
                        "spans" in raw or "resourceSpans" in raw or "scopeSpans" in raw
                    ):
                        return True
                    return False
        except OSError:
            return False
        return False

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
                    yield self._span_from(span, trace_id)
            else:
                # The OTLP structure nests spans under resourceSpans and
                # scopeSpans; an exporter that uses it is read the same way as
                # one that writes a flat list.
                for value in raw.values():
                    if isinstance(value, (list, dict)):
                        yield from self._iter_spans(value)

    @staticmethod
    def _normalise_attributes(raw: Any) -> Dict[str, Any]:
        """
        The attributes of a span, whichever way the exporter stated them.

        A plain JSON exporter writes ``{"http.method": "GET"}``; OTLP writes a
        list of key/value pairs whose value carries its own type.  Both are
        read as a mapping of attribute name to value.
        """
        if isinstance(raw, dict):
            return dict(raw)
        if not isinstance(raw, list):
            return {}
        attributes: Dict[str, Any] = {}
        for item in raw:
            if not isinstance(item, dict) or "key" not in item:
                continue
            value = item.get("value")
            if isinstance(value, dict):
                values = list(value.values())
                value = values[0] if len(values) == 1 else value
            attributes[str(item["key"])] = value
        return attributes

    def _span_from(self, span: Dict[str, Any], trace_id: str = "") -> Span:
        """Build a span from whichever spelling of the fields the exporter used."""
        start = int(
            span.get("timestamp", span.get("startTimeUnixNano", span.get("start_time_unix_nano", 0)))
            or 0
        )
        duration = span.get("duration")
        if duration is None:
            end = int(span.get("endTimeUnixNano", span.get("end_time_unix_nano", 0)) or 0)
            duration = max(0, end - start)
        attributes = span.get("attributes")
        attributes = self._normalise_attributes(attributes)
        return Span(
            name=str(span.get("name", "")),
            timestamp_ns=start,
            duration_ns=int(duration or 0),
            attributes=attributes,
            status=dict(span.get("status", {}) or {}),
            trace_id=trace_id or str(span.get("traceId", span.get("traceID", "")) or ""),
        )

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
