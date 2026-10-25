"""
Live-path smoke tests for the Nebius model gateway.

Stands up a local OpenAI-compatible HTTP server on 127.0.0.1 and points the
REAL NebiusModelGateway at it over actual TCP sockets, so URL formation,
Authorization headers, /models discovery, response_format fallbacks, 404
retries, and error propagation are exercised end-to-end — without ever
calling the Nebius API or spending tokens/credit.

The final test verifies the seam that mattered in production: a model-shaped
response (hypothesis id hyp-<incident>-nebius naming a batching-window
intervention) must flow from HypothesisGenerator into the digital twin's
InterventionPlan instead of falling through to baseline.
"""

import json
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict
from urllib.parse import urlparse

import httpx
import pytest

from cauveris.config import get_settings
from cauveris.hypothesis.generator import HypothesisGenerator
from cauveris.model_gateway.nebius import NebiusModelGateway, normalize_nebius_url
from cauveris.schemas.hypothesis import Hypothesis
from cauveris.schemas.incident import Incident
from cauveris.simulation.mapping import map_experiment_to_intervention

MODEL_JSON_NO_HYPOTHESIS_ID = {
    "causal_claim": (
        "Dynamic batching window increase in deployment v42 starved the telemetry "
        "queue, so the robot consumed stale object detections."
    ),
    "status": "CONFIRMED",
    "expected_observation": "Batch wait exceeds the 120ms freshness budget right after the v42 deploy",
    "falsifying_observation": "Latency spike persists when the window reverts to 100ms",
    "intervention": "Lower dynamic_batching.batching_window_ms to 100ms in config/inference.yaml",
    "confidence_prior": 0.9,
}


def _chat_payload(model: str, content_obj: Dict[str, Any]) -> Dict[str, Any]:
    """OpenAI chat.completion-shaped response."""
    return {
        "id": "chatcmpl-cauveris-smoke-1",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps(content_obj)},
            }
        ],
        "usage": {"prompt_tokens": 812, "completion_tokens": 311, "total_tokens": 1123},
    }


def make_fake_nebius_server():
    """
    Create (not start) a minimal OpenAI-compatible server.

    State is manipulated by tests:
      - models_script: deque of /v1/models payloads (lists of model ids); the
        last value is reused when the deque is empty
      - chat_script: deque of dict(status=..., body=...); default 200 with a
        model-shaped hypothesis when empty
      - sleep_seconds: delay before answering chat calls (timeout tests)
      - calls: log of every request (method, path, auth, body)
    """
    state: Dict[str, Any] = {
        "calls": [],
        "models_script": deque(),
        "last_models": [
            "meta-llama/Meta-Llama-3.1-8B-Instruct",
            "meta-llama/Meta-Llama-3.1-70B-Instruct",
            "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF",
        ],
        "chat_script": deque(),
        "sleep_seconds": 0.0,
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep pytest output clean
            pass

        def _send(self, status: int, payload: Any) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            state["calls"].append(
                {"method": "GET", "path": path, "auth": self.headers.get("authorization"), "body": None}
            )
            if path == "/v1/models":
                if state["models_script"]:
                    payload = state["models_script"].popleft()
                    state["last_models"] = payload
                else:
                    payload = state["last_models"]
                self._send(200, {"data": [{"id": m} for m in payload]})
            else:
                self._send(404, {"error": f"unknown path {path}"})

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            length = int(self.headers.get("content-length", 0))
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                body = None
            state["calls"].append({"method": "POST", "path": path, "auth": self.headers.get("authorization"), "body": body})

            if state["sleep_seconds"]:
                time.sleep(state["sleep_seconds"])

            if path != "/v1/chat/completions":
                self._send(404, {"error": f"unknown path {path}"})
                return

            if state["chat_script"]:
                entry = state["chat_script"].popleft()
                self._send(entry["status"], entry["body"])
                return

            # Default: happy path honoring the requested model
            model = (body or {}).get("model", "meta-llama/Meta-Llama-3.1-70B-Instruct")
            self._send(200, _chat_payload(model, MODEL_JSON_NO_HYPOTHESIS_ID))

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    server.state = state
    server.base_url = f"http://127.0.0.1:{port}/v1"
    return server


@pytest.fixture
def fake_nebius():
    """Start a local fake OpenAI-compatible server and point settings at it."""
    server = make_fake_nebius_server()
    server_thread = None
    settings = get_settings()
    saved = (settings.nebius_api_key, settings.nebius_base_url, settings.model_reasoning)
    server_thread = threading_stub(server)
    settings.nebius_api_key = "smoke-test-key-not-real"
    settings.nebius_base_url = server.base_url
    settings.model_reasoning = "meta-llama/Meta-Llama-3.1-70B-Instruct"
    try:
        yield server, settings
    finally:
        server.shutdown()
        server.server_close()
        if server_thread is not None:
            server_thread.join(timeout=5)
        settings.nebius_api_key, settings.nebius_base_url, settings.model_reasoning = saved


def threading_stub(server):
    thread = Thread(server)
    thread.start()
    return thread


class Thread:
    """Tiny wrapper so the server runs serve_forever in its own thread."""

    def __init__(self, server):
        import threading

        self._thread = threading.Thread(target=server.serve_forever, daemon=True)

    def start(self):
        self._thread.start()

    def join(self, timeout):
        self._thread.join(timeout)


def make_incident() -> Incident:
    return Incident(
        id="CAU-SMOKE",
        title="Warehouse AMR stale detections after deployment v42",
        description="ROBOT consumes stale object detections following dynamic batching change",
        system_name="warehouse-amr-01",
    )


def test_normalize_url_runs_against_local_server(fake_nebius):
    """The gateway must accept an explicit http:// base URL untouched."""
    server, _ = fake_nebius
    assert normalize_nebius_url(server.base_url) == server.base_url


async def test_gateway_happy_path_over_real_http(fake_nebius):
    """Full request contract: auth header, json_object mode, parsed structure, usage/cost."""
    server, _ = fake_nebius
    gw = NebiusModelGateway()

    resp = await gw.generate(prompt="Analyze incident CAU-SMOKE", schema=Hypothesis)

    auth_ok = all(c["auth"] == "Bearer smoke-test-key-not-real" for c in server.state["calls"])
    assert auth_ok and server.state["calls"], "Authorization header must reach the wire"

    chat_calls = [c for c in server.state["calls"] if c["path"] == "/v1/chat/completions"]
    assert len(chat_calls) == 1
    body = chat_calls[0]["body"]
    assert body["model"] == "meta-llama/Meta-Llama-3.1-70B-Instruct"
    assert body["response_format"] == {"type": "json_object"}
    assert body["max_tokens"] == 2048
    assert body["messages"][0]["role"] == "system"
    assert "Hypothesis" in body["messages"][0]["content"]

    assert resp.provider == "nebius"
    assert resp.structured_data["causal_claim"].startswith("Dynamic batching window increase")
    assert resp.usage["total_tokens"] == 1123
    assert resp.cost > 0
    await gw.aclose()


async def test_gateway_resolves_fictional_model_via_models_endpoint(fake_nebius):
    """A placeholder model name must be resolved against the account's real /models."""
    server, settings = fake_nebius
    settings.model_reasoning = "nemotron-3-super"  # fictional placeholder

    gw = NebiusModelGateway()
    resp = await gw.generate(prompt="x", schema=Hypothesis)

    assert [c["path"] for c in server.state["calls"]][0] == "/v1/models"
    assert resp.model_used == "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF"
    await gw.aclose()


async def test_gateway_retries_with_alternate_model_after_404(fake_nebius):
    """404 on the resolved model must invalidate cache, re-resolve, and retry."""
    server, settings = fake_nebius
    settings.model_reasoning = "nemotron-3-super"
    # First /models: only llamas -> resolves to Llama-70B
    server.state["models_script"].append(["meta-llama/Meta-Llama-3.1-70B-Instruct"])
    # Chat call 1: upstream says this account lost that model (404)
    missing = {"error": {"message": "meta-llama/Meta-Llama-3.1-70B-Instruct not found on account"}}
    server.state["chat_script"].append({"status": 404, "body": missing})
    # Second /models: only deepseek remains -> retry with the new model
    server.state["models_script"].append(["deepseek-ai/DeepSeek-V3"])
    # Chat call 2 succeeds (default handler)

    gw = NebiusModelGateway()
    resp = await gw.generate(prompt="x", schema=Hypothesis)

    chat_calls = [c for c in server.state["calls"] if c["path"] == "/v1/chat/completions"]
    assert len(chat_calls) == 2
    assert chat_calls[0]["body"]["model"] == "meta-llama/Meta-Llama-3.1-70B-Instruct"
    assert chat_calls[1]["body"]["model"] == "deepseek-ai/DeepSeek-V3"
    assert resp.structured_data is not None
    await gw.aclose()


async def test_gateway_retries_without_response_format_after_400(fake_nebius):
    """Strict OpenAI-compatible backends without json mode: retry must drop response_format."""
    server, _ = fake_nebius
    unsupported = {"error": {"message": "response_format is not supported by this backend"}}
    server.state["chat_script"].append({"status": 400, "body": unsupported})

    gw = NebiusModelGateway()
    resp = await gw.generate(prompt="x", schema=Hypothesis)

    chat_calls = [c for c in server.state["calls"] if c["path"] == "/v1/chat/completions"]
    assert len(chat_calls) == 2
    assert "response_format" in chat_calls[0]["body"]
    assert "response_format" not in chat_calls[1]["body"]
    assert resp.structured_data["status"] == "CONFIRMED"
    await gw.aclose()


async def test_gateway_invalid_api_key_propagates(fake_nebius):
    """401 from the upstream must surface, not silently degrade."""
    server, _ = fake_nebius
    unauthorized = {"error": {"message": "invalid api key"}}
    server.state["chat_script"].append({"status": 401, "body": unauthorized})

    gw = NebiusModelGateway()
    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        await gw.generate(prompt="x", schema=Hypothesis)
    assert excinfo.value.response.status_code == 401
    await gw.aclose()


async def test_gateway_surfaces_malformed_response(fake_nebius):
    """HTTP 200 with a non-conformant body must raise rather than fabricate content."""
    server, _ = fake_nebius
    server.state["chat_script"].append({"status": 200, "body": {"object": "chat.completion", "choices": []}})

    gw = NebiusModelGateway()
    with pytest.raises((KeyError, IndexError)):
        await gw.generate(prompt="x", schema=Hypothesis)
    await gw.aclose()


async def test_gateway_timeout_propagates(fake_nebius):
    """A hung upstream must surface a timeout (short-timeout client injected)."""
    server, _ = fake_nebius
    server.state["sleep_seconds"] = 1.0

    gw = NebiusModelGateway(
        client=httpx.AsyncClient(base_url=server.base_url, timeout=0.3, headers={"Authorization": "Bearer smoke-test-key-not-real"})
    )
    with pytest.raises((httpx.TimeoutException, httpx.ReadTimeout)):
        await gw.generate(prompt="x", schema=Hypothesis)
    await gw.aclose()


async def test_gateway_unavailable_without_key(fake_nebius):
    """No key configured -> CredentialNotConfigured, no network call is attempted."""
    server, settings = fake_nebius
    settings.nebius_api_key = None

    gw = NebiusModelGateway()
    with pytest.raises(Exception):  # CredentialNotConfigured
        await gw.generate(prompt="x", schema=Hypothesis)
    assert server.state["calls"] == []
    await gw.aclose()


async def test_model_hypothesis_flows_into_twin_intervention_plan(fake_nebius):
    """
    The production seam: a Nebius-shaped hypothesis (id hyp-<incident>-nebius,
    intervention naming dynamic_batching.batching_window_ms) must map onto the
    digital twin's injectable knobs instead of falling back to baseline.
    """
    server, _ = fake_nebius

    gen = HypothesisGenerator(model_gateway=NebiusModelGateway())
    incident = make_incident()
    hypotheses = await gen.generate(incident)
    await gen.model_gateway.aclose()

    model_hypotheses = [h for h in hypotheses if h.hypothesis_id == "hyp-CAU-SMOKE-nebius"]
    assert model_hypotheses, "model response must become a hypothesis with the -nebius id"
    hyp = model_hypotheses[0]
    # The model payload deliberately carries a non-enum status ("CONFIRMED");
    # the generator must coerce it rather than drop the whole hypothesis.
    assert hyp.status == "INFERRED"
    assert "batching window" in hyp.causal_claim.lower()
    assert "batching_window_ms" in hyp.intervention

    plan = map_experiment_to_intervention(
        hypothesis_id=hyp.hypothesis_id,
        intervention=hyp.intervention,
        likely_parameters=hyp.likely_parameters,
        causal_claim=hyp.causal_claim,
    )
    assert not plan.is_baseline, "model hypothesis must not fall through to baseline twin faults"
    assert plan.batching_window_ms == 100.0
    assert plan.applied_changes["config/inference.yaml"].startswith("batching_window_ms: 200 -> 100")
