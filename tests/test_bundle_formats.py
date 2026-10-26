"""
Evidence ingestion from bundles that are not the demo bundle.

The pipeline has to read an incident bundle from a company it has never met.
That means the formats it reads are discovered rather than assumed: a company
that exports Prometheus text, or NDJSON events, or TOML parameters, must be
understood as readily as one that ships ``service.log`` and ``config.yaml``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cauveris.analysis.evidence import EvidenceBundle


def _bundle(tmp_path: Path) -> Path:
    root = tmp_path / "incident-CAU-9001"
    root.mkdir()
    return root


# --------------------------------------------------------------------- logs


def test_plain_text_log_is_read(tmp_path: Path) -> None:
    """A console dump is a log, whatever it is called."""
    root = _bundle(tmp_path)
    (root / "logs").mkdir()
    (root / "logs" / "console.txt").write_text(
        "2026-09-20T10:29:59Z ERROR service: container killed: OOMKilled, "
        "memory limit exceeded (used 1400 MB of 512 MiB)\n",
        encoding="utf-8",
    )

    bundle = EvidenceBundle.load(root)

    assert len(bundle.logs) == 1
    assert "OOMKilled" in bundle.logs[0].text
    assert bundle.logs[0].level == "ERROR"


def test_extensionless_journal_is_read(tmp_path: Path) -> None:
    """A file with no suffix is still read when its name says it is a log."""
    root = _bundle(tmp_path)
    (root / "journal").write_text("ERROR upstream timed out after 50 ms\n", encoding="utf-8")

    bundle = EvidenceBundle.load(root)

    assert any("timed out" in record.text for record in bundle.logs)


def test_rotated_log_is_read(tmp_path: Path) -> None:
    """The previous day's rotated log is evidence too."""
    root = _bundle(tmp_path)
    (root / "service.log.1").write_text("ERROR out of memory\n", encoding="utf-8")

    bundle = EvidenceBundle.load(root)

    assert any("out of memory" in record.text for record in bundle.logs)


def test_ndjson_events_are_read(tmp_path: Path) -> None:
    """One JSON object per line, under a name that is not ``.log``."""
    root = _bundle(tmp_path)
    (root / "events.ndjson").write_text(
        json.dumps(
            {"ts": "2026-09-20T10:29:59Z", "level": "error", "msg": "lock wait timeout"}
        )
        + "\n",
        encoding="utf-8",
    )

    bundle = EvidenceBundle.load(root)

    assert any("lock wait timeout" in record.text for record in bundle.logs)
    assert bundle.logs[0].timestamp is not None


def test_json_array_of_log_records_is_read(tmp_path: Path) -> None:
    """A JSON file holding a list of events is a log file."""
    root = _bundle(tmp_path)
    (root / "logs").mkdir()
    (root / "logs" / "events.json").write_text(
        json.dumps([{"level": "ERROR", "message": "dependency timed out after 50 ms"}]),
        encoding="utf-8",
    )

    bundle = EvidenceBundle.load(root)

    assert any("dependency timed out" in record.text for record in bundle.logs)


def test_a_json_file_that_is_not_a_log_is_not_read_as_one(tmp_path: Path) -> None:
    """A file under ``logs/`` that holds data rather than events is left alone."""
    root = _bundle(tmp_path)
    (root / "logs").mkdir()
    (root / "logs" / "summary.json").write_text(
        json.dumps({"totals": {"requests": 12}}), encoding="utf-8"
    )

    bundle = EvidenceBundle.load(root)

    assert bundle.logs == []


# ------------------------------------------------------------------ metrics


def test_prometheus_exposition_is_read(tmp_path: Path) -> None:
    """A Prometheus scrape is a metric series."""
    root = _bundle(tmp_path)
    (root / "metrics").mkdir()
    (root / "metrics" / "node.prom").write_text(
        "# HELP process_resident_memory_bytes Resident memory size in bytes.\n"
        "# TYPE process_resident_memory_bytes gauge\n"
        "process_resident_memory_bytes{job=\"perception\"} 1.466e+09 1789273799000\n"
        "process_resident_memory_bytes{job=\"perception\"} 1.610e+09 1789273800000\n"
        "# TYPE inference_latency_ms gauge\n"
        "inference_latency_ms{job=\"perception\"} 42 1789273799000\n",
        encoding="utf-8",
    )

    bundle = EvidenceBundle.load(root)

    series = bundle.metrics["metrics/node.prom"]
    assert len(series) == 3
    assert series[0].timestamp is not None
    labels = [key for key in series[0].values]
    assert labels[0].startswith("process_resident_memory_bytes{")
    assert series[0].values[labels[0]] == pytest.approx(1.466e9)


def test_a_text_file_without_prometheus_comments_is_not_metrics(tmp_path: Path) -> None:
    """Log lines that contain numbers are not a metric scrape."""
    root = _bundle(tmp_path)
    (root / "logs").mkdir()
    (root / "logs" / "service.txt").write_text(
        "2026-09-20T10:29:59Z INFO request served in 42 ms\n", encoding="utf-8"
    )

    bundle = EvidenceBundle.load(root)

    assert bundle.metrics == {}


# --------------------------------------------------------------------- config


def test_toml_configuration_is_read(tmp_path: Path) -> None:
    """A bundle whose parameters ship as TOML is not without configuration."""
    root = _bundle(tmp_path)
    (root / "config").mkdir()
    (root / "config" / "robot.toml").write_text(
        "[dynamic_batching]\nbatching_window_ms = 120\n", encoding="utf-8"
    )

    bundle = EvidenceBundle.load(root)

    assert bundle.numeric_config("dynamic_batching.batching_window_ms") == 120.0


def test_ini_configuration_is_read(tmp_path: Path) -> None:
    """An INI file at the root of the bundle is configuration."""
    root = _bundle(tmp_path)
    (root / "settings.ini").write_text(
        "[dynamic_batching]\nbatching_window_ms = 90\n", encoding="utf-8"
    )

    bundle = EvidenceBundle.load(root)

    assert bundle.numeric_config("dynamic_batching.batching_window_ms") == 90.0


def test_packaging_files_are_not_configuration(tmp_path: Path) -> None:
    """``pyproject.toml`` is packaging, not the robot's settings."""
    root = _bundle(tmp_path)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "robot"\nversion = "1.0"\n', encoding="utf-8"
    )

    bundle = EvidenceBundle.load(root)

    assert bundle.config == {}


# -------------------------------------------------------------------- traces


def test_otlp_ndjson_traces_are_read(tmp_path: Path) -> None:
    """An OTLP export in NDJSON is read, whatever the file is called."""
    root = _bundle(tmp_path)
    (root / "telemetry.ndjson").write_text(
        json.dumps(
            {
                "resourceSpans": [
                    {
                        "scopeSpans": [
                            {
                                "spans": [
                                    {
                                        "name": "inference",
                                        "startTimeUnixNano": "1789273799000000000",
                                        "endTimeUnixNano": "1789273799042000000",
                                        "attributes": [
                                            {"key": "model", "value": {"stringValue": "yolo"}}
                                        ],
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    bundle = EvidenceBundle.load(root)

    assert len(bundle.spans) == 1
    span = bundle.spans[0]
    assert span.name == "inference"
    assert span.duration_ms == pytest.approx(42.0)
    assert span.attributes["model"] == "yolo"


def test_a_ndjson_file_without_spans_is_not_a_trace(tmp_path: Path) -> None:
    """An NDJSON log file is not mistaken for a trace file."""
    root = _bundle(tmp_path)
    (root / "events.ndjson").write_text(
        json.dumps({"message": "hello"}) + "\n", encoding="utf-8"
    )

    bundle = EvidenceBundle.load(root)

    assert bundle.spans == []
