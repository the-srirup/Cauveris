"""
The whole pipeline on incidents Cauveris has never seen.

Each family below is a synthetic incident with its own layout - its own
configuration format, its own log format, its own file names - so that the
pipeline has to work from what the bundle *is* rather than from what it is
used to.  The question each test answers is the one a customer asks:

    *my robot died, here are the logs, here is what it was configured to do -
    what went wrong, what do I change, and how do you know the change works?*

The answer has to be a real diff against a real file, verified against the
incident's own evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest
import yaml

from cauveris.hypothesis.generator import HypothesisGenerator
from cauveris.patch.generator import PatchGenerator
from cauveris.sandbox.controller import SandboxController
from cauveris.schemas.incident import Incident
from cauveris.simulation.runner import SimulationRunner
from cauveris.verifier.engine import VerificationEngine

#: The configuration every family starts from.
BASE_CONFIG: Dict[str, Any] = {
    "dynamic_batching": {"batching_window_ms": 100, "max_batch_size": 8},
    "qos": {"queue_depth": 5},
    "server": {"worker_count": 2},
    "safety": {"detection_freshness_budget_ms": 400},
}


def _yaml_config(config: Dict[str, Any]) -> str:
    return yaml.safe_dump(config, sort_keys=False)


def _toml_config(config: Dict[str, Any]) -> str:
    """The same configuration, as TOML."""
    lines: List[str] = []
    for section, values in config.items():
        lines.append(f"[{section}]")
        for key, value in values.items():
            lines.append(f"{key} = {value}")
        lines.append("")
    return "\n".join(lines)


def _ini_config(config: Dict[str, Any]) -> str:
    """The same configuration, as INI."""
    lines: List[str] = []
    for section, values in config.items():
        lines.append(f"[{section}]")
        for key, value in values.items():
            lines.append(f"{key} = {value}")
        lines.append("")
    return "\n".join(lines)


def _ndjson_logs(records: List[Dict[str, Any]]) -> str:
    return "\n".join(json.dumps(record) for record in records) + "\n"


def _write_bundle(root: Path, files: Dict[str, str], incident_id: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    (root / "manifest.yaml").write_text(
        yaml.safe_dump({"incident_id": incident_id, "title": "synthetic"}),
        encoding="utf-8",
    )
    return root


#: Three failures that present as "the robot stopped", each with its own
#: cause, its own evidence and its own configuration format.
FAMILIES = {
    "memory": {
        "incident_id": "CAU-7001",
        "config": {**BASE_CONFIG, "resources": {"memory_limit_mb": 512}},
        "parameter": "resource_limit_mb",
        "hypothesis": "h_memory_exhaustion",
        "files": lambda config: {
            # YAML, in a config/ directory - the shape Cauveris was built on.
            "config/service.yaml": _yaml_config(config),
            "logs/service.log": (
                "2026-09-20T10:29:58Z WARN service: request served in 42 ms\n"
                "2026-09-20T10:29:59Z ERROR service: container killed: OOMKilled, "
                "memory limit exceeded (used 1400 MB of 512 MiB)\n"
            ),
            "metrics/memory.csv": (
                "timestamp,memory_used_mb,memory_total_mb,memory_utilization_percent\n"
                "2026-09-20T10:29:58Z,1100,8192,13\n"
                "2026-09-20T10:29:59Z,1400,8192,17\n"
            ),
        },
    },
    "timeout": {
        "incident_id": "CAU-7002",
        "config": {**BASE_CONFIG, "http": {"request_timeout_ms": 50}},
        "parameter": "request_timeout_ms",
        "hypothesis": "h_dependency_timeout",
        "files": lambda config: {
            # TOML, and NDJSON events - neither of which the demo bundle uses.
            "config/robot.toml": _toml_config(config),
            "logs/events.ndjson": _ndjson_logs(
                [
                    {
                        "ts": "2026-09-20T10:29:58Z",
                        "level": "info",
                        "msg": "request served in 42 ms",
                    },
                    {
                        "ts": "2026-09-20T10:29:59Z",
                        "level": "error",
                        "msg": (
                            "upstream request timed out after 50 ms "
                            "(no response inside the client deadline)"
                        ),
                    },
                ]
            ),
        },
    },
    "lock": {
        "incident_id": "CAU-7003",
        "config": {**BASE_CONFIG, "storage": {"lock_timeout_ms": 50}},
        "parameter": "lock_timeout_ms",
        "hypothesis": "h_lock_contention",
        "files": lambda config: {
            # INI beside the manifest, and a log with no suffix at all.
            "robot.ini": _ini_config(config),
            "journal": (
                "2026-09-20T10:29:58Z INFO service: request served in 42 ms\n"
                "2026-09-20T10:29:59Z ERROR service: lock wait timeout after 50 ms "
                "(lock held for 120 ms)\n"
            ),
        },
    },
    "database": {
        "incident_id": "CAU-7004",
        "config": {**BASE_CONFIG, "database": {"max_connections": 10}},
        "parameter": "db_pool_size",
        "hypothesis": "h_connection_pool_exhaustion",
        "files": lambda config: {
            "config/database.yaml": _yaml_config(config),
            "logs/postgres.log": (
                "2026-09-20T10:29:58Z INFO pgpool: connection granted to client 9\n"
                "2026-09-20T10:29:59Z ERROR pgpool: connection pool exhausted: "
                "active connections 35 exceeded pool capacity 10 (remaining: 0)\n"
            ),
        },
    },
}


async def _run_family(name: str, tmp_path: Path) -> Dict[str, Any]:
    """Diagnose, patch and verify one synthetic family."""
    spec = FAMILIES[name]
    bundle = _write_bundle(
        tmp_path / f"incident-{spec['incident_id']}",
        spec["files"](spec["config"]),
        spec["incident_id"],
    )
    incident = Incident(
        id=spec["incident_id"],
        title=f"synthetic {name} incident",
        manifest={},
        bundle_path=str(bundle),
    )

    hypotheses = await HypothesisGenerator().generate(incident)

    sandbox = SandboxController(workspace_dir=tmp_path / f"sandbox-{name}")
    experiments = await sandbox.plan_experiments(hypotheses, incident_id=incident.id)
    await sandbox.run_experiments(experiments)

    runner = SimulationRunner()
    experiments = await runner.run_simulations(experiments)

    generator = PatchGenerator()
    patches = await generator.generate(experiments, incident=incident)

    verifier = VerificationEngine(workspace_dir=tmp_path / f"verify-{name}")
    reports = await verifier.verify(patches, incident=incident, bundle_root=bundle)

    return {
        "bundle": bundle,
        "hypotheses": hypotheses,
        "patches": patches,
        "reports": reports,
        "spec": spec,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(FAMILIES))
async def test_an_unseen_incident_is_diagnosed_patched_and_verified(
    name: str, tmp_path: Path
) -> None:
    """Every stage works on an incident with a layout of its own."""
    outcome = await _run_family(name, tmp_path)
    spec = outcome["spec"]

    # 1. The right cause is named.
    hypothesis_ids = [h.hypothesis_id for h in outcome["hypotheses"]]
    assert spec["hypothesis"] in hypothesis_ids, (
        f"the incident was diagnosed as {hypothesis_ids}, "
        f"not as {spec['hypothesis']}"
    )

    # 2. A patch is produced against the customer's own file.
    assert outcome["patches"], "no patch was produced"
    patch = outcome["patches"][0]
    assert patch.unified_diff.strip(), "the patch is empty"
    changed = {edit.parameter for edit in patch.config_edits}
    assert changed, "the patch changes nothing"

    # 3. The patch is a real diff against a real file in the bundle.
    touched = [
        rel
        for rel in spec["files"](spec["config"])
        if rel in patch.unified_diff
    ]
    assert touched, "the patch does not touch any file the bundle shipped"

    # 4. A deadline is never raised to hide a slow dependency.  A timeout is
    #    fixed by making the request fit inside the deadline, not by moving
    #    the deadline.
    for edit in patch.config_edits:
        if edit.parameter == "request_timeout_ms":
            assert float(edit.target_value) <= float(edit.current_value), (
                "the patch raises the request deadline to hide a slow dependency"
            )

    # 5. The verification passes all nine points - which is what proves the
    #    declared mechanism was actually cleared.
    assert outcome["reports"], "the patch was not verified"
    report = outcome["reports"][0]
    assert report.verified, (
        f"the patch was rejected: {report.details.get('failures')}"
    )
    assert report.details.get("checks_passed") == 9


@pytest.mark.asyncio
async def test_a_latency_rule_is_not_offered_for_a_killed_process(
    tmp_path: Path,
) -> None:
    """A patch for a timeout cannot fix a process that was killed."""
    outcome = await _run_family("memory", tmp_path)

    hypothesis_ids = [h.hypothesis_id for h in outcome["hypotheses"]]
    latency_rules = {
        "h_batching_window_latency",
        "h_arrival_rate_saturation",
        "h_consumer_sampling_interval",
        "h_subscriber_buffer_staleness",
        "h_network_transport_delay",
        "h_gpu_resource_contention",
        "h_clock_skew",
    }
    assert not latency_rules.intersection(hypothesis_ids), (
        "a latency hypothesis was offered for an incident whose request was lost"
    )
