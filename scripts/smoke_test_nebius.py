#!/usr/bin/env python3
"""
Nebius and NVIDIA Nemotron Smoke Test Script.

Validates the live integration with Nebius Token Factory and NVIDIA models.
- Without --live: Checks configuration and reports provider state without calling inference.
- With --live: Sends a bounded terminology-mapping test prompt to the configured NVIDIA model.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Optional

# Ensure project root is in python path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import subprocess  # noqa: E402

# Auto-reexec into project virtualenv if running under an unconfigured python environment
for _candidate in [
    ROOT / ".venv311" / "Scripts" / "python.exe",
    ROOT / ".venv" / "Scripts" / "python.exe",
    ROOT / ".venv311" / "bin" / "python",
    ROOT / ".venv" / "bin" / "python",
]:
    if _candidate.exists() and Path(sys.executable).resolve() != _candidate.resolve():
        try:
            import jwt  # noqa: F401
        except ImportError:
            sys.exit(subprocess.call([str(_candidate)] + sys.argv))

from cauveris.config import get_settings
from cauveris.model_gateway.enums import ModelTaskType
from cauveris.model_gateway.nebius import NebiusModelGateway
from cauveris.model_gateway.records import get_execution_store
from cauveris.model_gateway.security import redact_secrets
from cauveris.model_gateway.tasks import TerminologyMappingOutput
from cauveris.model_gateway.validators import validate_terminology_mapping


def print_banner() -> None:
    print("=" * 80)
    print(" Cauveris Nebius and NVIDIA Integration Smoke Test")
    print("=" * 80)


async def run_checks(live: bool, model_id_override: Optional[str] = None) -> int:
    print_banner()
    settings = get_settings()
    api_key = os.environ.get("NEBIUS_API_KEY") or getattr(settings, "nebius_api_key", "")
    base_url = os.environ.get("NEBIUS_BASE_URL") or getattr(settings, "nebius_base_url", "https://api.tokenfactory.nebius.com/v1")
    model_id = model_id_override or os.environ.get("NEBIUS_MODEL_ID") or getattr(settings, "nebius_model_id", "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF")

    print(f"[*] Base URL:  {base_url}")
    print(f"[*] Model ID:  {model_id}")
    has_key = bool(api_key and api_key.strip())
    masked_key = (api_key[:4] + "*" * 16) if has_key else "(not set)"
    print(f"[*] API Key:   {masked_key}")

    gateway = NebiusModelGateway()
    if model_id_override:
        gateway.model_id = model_id_override
    state = gateway.get_provider_state()
    print(f"[*] Provider State: {state.value}")

    # Check 1: Redaction check
    print("\n[Check 1] Secret Redaction & Sanitization...")
    test_str = "Authorization: Bearer sk-secret-token-abcdef123456789012345"
    redacted, count = redact_secrets(test_str)
    if "sk-secret-token" in redacted or count == 0:
        print("  [FAIL] Secret redaction failed to scrub credential!")
        return 1
    print("  [PASS] Secrets successfully scrubbed from logs/exceptions.")

    # Check 2: Offline / Dry-run behavior
    if not live:
        print("\n[Check 2] Offline / Non-Live Inspection...")
        print("  [INFO] --live flag was not passed.")
        print(f"  [INFO] Provider operational state: {state.value}")
        print("=" * 80)
        print(" LIVE PROVIDER TEST NOT RUN (pass --live with NEBIUS_API_KEY to execute inference)")
        print("=" * 80)
        return 0

    # Live execution requested
    print("\n[Check 2] Live Provider Inference...")
    if not has_key:
        print("  [FAIL] NEBIUS_API_KEY environment variable is required when --live is specified.")
        return 2

    # Verify endpoint and run bounded task
    task_type = ModelTaskType.TERMINOLOGY_MAPPING
    test_prompt = (
        "Map the following observed telemetry terms to canonical Cauveris signals:\n"
        "- input_queue_wait_ms -> queue_delay\n"
        "- mem_rss_bytes -> memory_consumption\n"
        "Return structured TerminologyMappingOutput JSON."
    )

    t0 = time.perf_counter()
    try:
        response = await gateway.generate(
            prompt=test_prompt,
            schema=TerminologyMappingOutput,
            task_type=task_type,
            incident_id="SMOKE-TEST-001",
            incident_context={"known_signals": ["queue_delay", "memory_consumption", "network_rtt"]},
        )
        latency = time.perf_counter() - t0
        print(f"  [PASS] Live call returned status {response.provider} (latency: {latency:.2f}s)")
    except Exception as exc:
        print(f"  [FAIL] Live inference request failed: {exc}")
        return 1

    # Check 3: Structured output validation
    print("\n[Check 3] Structured Output & Deterministic Validation...")
    structured = response.structured_data
    if not structured:
        print("  [FAIL] No structured data returned by model response.")
        return 1

    try:
        parsed_output = TerminologyMappingOutput(**structured)
        canonical_signals = {"queue_delay", "memory_consumption", "network_rtt"}
        discovered_fields = {"input_queue_wait_ms", "mem_rss_bytes", "ping_time_ms"}
        val_result, accepted, rejected, reasons = validate_terminology_mapping(
            output=parsed_output,
            canonical_signals=canonical_signals,
            discovered_fields=discovered_fields,
        )
        print(f"  [PASS] Task output parsed successfully. Validation result: {val_result.value}")
        print(f"         Accepted mappings: {len(accepted)}, Rejected: {len(rejected)}")
    except Exception as val_err:
        print(f"  [FAIL] Task schema validation failed: {val_err}")
        return 1

    # Check 4: Audit Record Verification
    print("\n[Check 4] Audit & Execution Record Store...")
    store = get_execution_store()
    records = store.get_by_incident("SMOKE-TEST-001")
    if not records:
        print("  [FAIL] Model execution record was not persisted in ModelExecutionStore!")
        return 1
    rec = records[-1]
    print("  [PASS] Execution Record Persisted:")
    print(f"         Execution ID:       {rec.execution_id}")
    print(f"         Exact Model ID:     {rec.model_id}")
    print(f"         Latency:            {rec.latency_ms:.2f} ms")
    print(f"         Response Hash:      {rec.response_hash[:16]}...")
    print(f"         Accepted Proposals: {rec.suggestions_accepted}")
    print(f"         Rejected Proposals: {rec.suggestions_rejected}")
    print(f"         Fallback Used:      {rec.fallback_used}")
    if rec.fallback_used:
        print("  [FAIL] Live smoke test must not use fallback when live provider is verified.")
        return 1

    print("\n" + "=" * 80)
    print(" STATUS: NEBIUS NVIDIA INTEGRATION OPERATIONAL (ALL CHECKS PASSED)")
    print("=" * 80)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Nebius and NVIDIA Nemotron integration")
    parser.add_argument("--live", action="store_true", help="Execute live inference against Nebius")
    parser.add_argument("--model", type=str, default=None, help="Override target model ID")
    args = parser.parse_args()

    exit_code = asyncio.run(run_checks(live=args.live, model_id_override=args.model))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
