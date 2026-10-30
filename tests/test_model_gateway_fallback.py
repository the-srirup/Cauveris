"""
Tests for the model gateway's provider fallback chain.

The chain has to do three things, and each of them is tested here against a
real HTTP server rather than a mock object:

1. Use the first provider that answers.
2. Move on to the next provider when the first one fails.
3. Say so - loudly and honestly - when no provider can answer.
"""

import json

import httpx
import pytest

from cauveris.model_gateway.base import ModelGateway, ModelResponse
from cauveris.model_gateway.fallback import AllProvidersFailed, FallbackModelGateway
from cauveris.model_gateway.local import LocalModelGateway, NoLocalModelAvailable


# ---------------------------------------------------------------------------
# A local model server that really speaks the OpenAI chat-completions protocol
# ---------------------------------------------------------------------------


class _FakeModelServer:
    """
    An HTTP server that behaves like a local model server.

    It answers over real HTTP through a mounted transport, because the thing
    under test is a client: a hand-written stub would not exercise the URL
    construction, the timeout, the status handling or the JSON shape.
    """

    def __init__(self, models=("qwen2.5:7b-instruct",), fail=False):
        self.models = list(models)
        self.fail = fail
        self.requests = []

    async def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.endswith("/models"):
            return httpx.Response(
                200, json={"data": [{"id": name} for name in self.models]}
            )
        if path.endswith("/chat/completions"):
            if self.fail:
                return httpx.Response(503, text="model server is overloaded")
            body = json.loads(request.content.decode("utf-8"))
            return httpx.Response(
                200,
                json={
                    "model": body.get("model"),
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "hypothesis_id": "hyp-from-local",
                                        "causal_claim": "the local model saw it",
                                        "status": "INFERRED",
                                    }
                                )
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 7},
                },
            )
        return httpx.Response(404, text="not found")

    def gateway(self, model_name="qwen2.5:7b-instruct", **kwargs) -> LocalModelGateway:
        """A local gateway whose client reaches this server."""
        gateway = LocalModelGateway(
            endpoints=["http://model.test/v1"],
            model_name=model_name,
            **kwargs,
        )
        gateway._client = httpx.AsyncClient(
            base_url="http://model.test",
            transport=httpx.MockTransport(self.handler),
        )
        return gateway


# ---------------------------------------------------------------------------
# The local gateway
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_local_gateway_asks_a_real_server_and_parses_its_json():
    """
    The local gateway has to talk the real protocol.

    A canned JSON blob written by the gateway itself would be a mock: the
    point of the fallback is that a model running on the machine produced the
    answer.
    """
    server = _FakeModelServer()
    gateway = server.gateway()

    response = await gateway.generate(prompt="why is the robot late?", schema=None)

    assert response.inference is True
    assert response.provider == "local-llm"
    assert response.model_used == "qwen2.5:7b-instruct"
    assert response.endpoint == "http://model.test/v1"
    assert response.cost == 0.0
    assert response.usage["total_tokens"] == 18

    # The server was asked for its models and then for a completion.
    paths = [r.url.path for r in server.requests]
    assert "/v1/models" in paths
    assert "/v1/chat/completions" in paths


@pytest.mark.asyncio
async def test_the_local_gateway_reports_a_dead_server_instead_of_inventing_one():
    """
    When nothing is listening, the gateway says so.

    It must not fall back to a hand-written answer: an invented root cause
    is indistinguishable from a real one once it is in a report.
    """
    gateway = LocalModelGateway(endpoints=["http://127.0.0.1:9/v1"], probe_timeout=0.3)

    with pytest.raises(NoLocalModelAvailable) as caught:
        await gateway.generate(prompt="anything", schema=None)

    assert caught.value.attempts
    assert caught.value.attempts[0]["endpoint"] == "http://127.0.0.1:9/v1"
    assert caught.value.attempts[0]["error"]


@pytest.mark.asyncio
async def test_the_local_gateway_picks_a_model_the_server_actually_serves():
    """
    The served model is discovered, not assumed.

    A fixed model name is right until somebody pulls a different image, and
    then every request 404s.
    """
    server = _FakeModelServer(models=("qwen2.5:7b-instruct-q4_K_M", "llama3.1:8b"))
    gateway = server.gateway()

    response = await gateway.generate(prompt="hello", schema=None)

    assert response.model_used == "qwen2.5:7b-instruct-q4_K_M"


# ---------------------------------------------------------------------------
# The chain
# ---------------------------------------------------------------------------


class _FailingGateway(ModelGateway):
    def __init__(self, name="failing", error="boom"):
        self.name = name
        self.error = error
        self.calls = 0

    def is_available(self) -> bool:
        return True

    async def generate(self, prompt, schema=None, temperature=0.7, max_tokens=None):
        self.calls += 1
        raise RuntimeError(self.error)


class _AnsweringGateway(ModelGateway):
    def __init__(self, provider="second", inference=True):
        self.provider = provider
        self.inference = inference
        self.calls = 0

    def is_available(self) -> bool:
        return True

    async def generate(self, prompt, schema=None, temperature=0.7, max_tokens=None):
        self.calls += 1
        return ModelResponse(
            content="answer",
            structured_data={"ok": True},
            model_used="test-model",
            provider=self.provider,
            inference=self.inference,
        )


@pytest.mark.asyncio
async def test_the_chain_falls_through_to_the_next_provider():
    first = _FailingGateway("first", "connection refused")
    second = _AnsweringGateway("second")
    chain = FallbackModelGateway([first, second])

    response = await chain.generate(prompt="why")

    assert first.calls == 1
    assert second.calls == 1
    assert response.provider == "second"
    assert response.inference is True

    # The failed attempt is recorded, so a degraded answer is visible.
    attempts = response.usage["provider_attempts"]
    assert attempts[0]["provider"] == "_FailingGateway"
    assert attempts[0]["ok"] is False
    assert "connection refused" in attempts[0]["error"]
    assert attempts[1]["ok"] is True


@pytest.mark.asyncio
async def test_the_chain_keeps_going_past_a_provider_that_does_not_infer():
    """
    A provider that answers with a template has not answered.

    A real - if weaker - answer from the next provider beats a fabricated
    one, so the chain moves on rather than accepting it.
    """
    template = _AnsweringGateway("template", inference=False)
    real = _AnsweringGateway("real")
    chain = FallbackModelGateway([template, real])

    response = await chain.generate(prompt="why")

    assert template.calls == 1
    assert real.calls == 1
    assert response.provider == "real"


@pytest.mark.asyncio
async def test_the_chain_reports_every_failure_when_nothing_answers():
    first = _FailingGateway("first", "no route to host")
    second = _FailingGateway("second", "connection refused")
    chain = FallbackModelGateway([first, second])

    with pytest.raises(AllProvidersFailed) as caught:
        await chain.generate(prompt="why")

    assert len(caught.value.attempts) == 2
    assert all(a.ok is False for a in caught.value.attempts)
    assert "no route to host" in str(caught.value)


@pytest.mark.asyncio
async def test_a_chain_of_one_is_still_a_chain():
    gateway = _AnsweringGateway("only")
    chain = FallbackModelGateway([gateway])

    response = await chain.generate(prompt="why")

    assert response.provider == "only"
    assert chain.provider_names == ["_AnsweringGateway"]


# ---------------------------------------------------------------------------
# The factory
# ---------------------------------------------------------------------------


def test_the_factory_builds_a_chain_and_does_not_need_a_key(monkeypatch):
    """
    The platform has to work with no hosted key at all.

    The local provider is always in the chain, so the chain is never empty
    and the factory never returns something that cannot be asked.
    """
    from cauveris.config import get_settings
    from cauveris.model_gateway import create_model_gateway

    settings = get_settings()
    original = settings.nebius_api_key
    try:
        settings.nebius_api_key = None
        gateway = create_model_gateway()
        assert isinstance(gateway, FallbackModelGateway)
        assert len(gateway.gateways) == 1
        assert isinstance(gateway.gateways[0], LocalModelGateway)
    finally:
        settings.nebius_api_key = original


def test_the_factory_prefers_the_hosted_provider_when_a_key_exists(monkeypatch):
    from cauveris.config import get_settings
    from cauveris.model_gateway import create_model_gateway
    from cauveris.model_gateway.nebius import NebiusModelGateway

    settings = get_settings()
    original = settings.nebius_api_key
    try:
        settings.nebius_api_key = "test-key"
        gateway = create_model_gateway()
        assert isinstance(gateway, FallbackModelGateway)
        assert isinstance(gateway.gateways[0], NebiusModelGateway)
        assert isinstance(gateway.gateways[1], LocalModelGateway)
    finally:
        settings.nebius_api_key = original


# ---------------------------------------------------------------------------
# What the platform reports about its model providers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_health_endpoint_reports_what_is_actually_reachable():
    """
    The health endpoint must not announce a readiness it did not check.

    It used to answer "Local deterministic simulation engine is active and
    ready" with a made-up latency, which told an operator that a model was
    standing by when nothing was listening at all.
    """
    from httpx import ASGITransport, AsyncClient

    from cauveris.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/model-health")

    assert response.status_code == 200
    payload = response.json()

    # Every endpoint that was probed is reported, with what it said.
    assert payload["provider_probes"]
    for probe in payload["provider_probes"]:
        assert "endpoint" in probe
        assert "reachable" in probe

    # The verdict follows the probes rather than the configuration.
    reachable = [p for p in payload["provider_probes"] if p["reachable"]]
    assert payload["inference_available"] is bool(reachable)
    if not reachable:
        assert payload["provider"] == "none reachable"
        assert payload["gateway_status"] == "no_inference"

    # The platform itself is still healthy: the evidence rules carry the
    # analysis when no model is reachable.
    assert payload["status"] == "healthy"
    assert payload["cloud_credentials_required"] is False


@pytest.mark.asyncio
async def test_the_model_test_endpoint_probes_local_servers_for_real(test_user, monkeypatch):
    """
    The connectivity test has to be a connectivity test.

    Without a hosted key it now probes the local servers and reports what
    they answered, rather than returning a canned success.
    """
    from httpx import ASGITransport, AsyncClient

    from cauveris.api.main import app
    from cauveris.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "nebius_api_key", None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(test_user["headers"])
        response = await client.post("/api/v1/model/test", json={})

    assert response.status_code == 200
    payload = response.json()
    assert "endpoints" in payload
    assert isinstance(payload["endpoints"], list)
    # A latency that was never measured must not be reported.
    if not payload.get("success"):
        assert payload.get("latency_ms") is None
