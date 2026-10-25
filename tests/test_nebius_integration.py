"""
Unit and integration tests for Nebius Model Gateway and live model integration.
"""

import json
import pytest
import httpx
from cauveris.model_gateway.nebius import NebiusModelGateway, normalize_nebius_url
from cauveris.schemas.hypothesis import Hypothesis
from cauveris.schemas.incident import Incident
from cauveris.hypothesis.generator import HypothesisGenerator
from cauveris.config import get_settings


def test_normalize_nebius_url():
    assert normalize_nebius_url("") == "https://api.tokenfactory.nebius.com/v1"
    assert normalize_nebius_url("https://api.nebius.ai/v1") == "https://api.tokenfactory.nebius.com/v1"
    assert normalize_nebius_url("https://api.nebius.ai/v1/") == "https://api.tokenfactory.nebius.com/v1"
    assert normalize_nebius_url("https://api.studio.nebius.ai/v1") == "https://api.studio.nebius.ai/v1"
    assert normalize_nebius_url("https://custom.host/v1") == "https://custom.host/v1"


@pytest.mark.asyncio
async def test_nebius_model_gateway_live_mocked():
    """Verify NebiusModelGateway calls the OpenAI-compatible endpoint with resolved model."""
    settings = get_settings()
    settings.nebius_api_key = "test-live-key"
    settings.nebius_base_url = "https://api.tokenfactory.nebius.com/v1"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/models"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "meta-llama/Meta-Llama-3.1-70B-Instruct"},
                        {"id": "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF"},
                    ]
                },
            )
        if path.endswith("/chat/completions"):
            return httpx.Response(
                200,
                json={
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "model": "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(
                                    {
                                        "hypothesis_id": "hyp-ai-001",
                                        "causal_claim": "Inference batching window saturation caused robot control loop breach",
                                        "status": "INFERRED",
                                        "expected_observation": "P99 latency > 120ms during deployment",
                                        "falsifying_observation": "P99 latency <= 100ms",
                                        "intervention": "Lower dynamic_batching.batching_window_ms to 100ms",
                                        "confidence_prior": 0.92,
                                    }
                                ),
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 120,
                        "completion_tokens": 60,
                        "total_tokens": 180,
                    },
                },
            )
        return httpx.Response(404)

    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.tokenfactory.nebius.com/v1",
    )
    gateway = NebiusModelGateway(client=mock_client)
    assert gateway.is_available() is True

    resp = await gateway.generate(
        prompt="Analyze incident CAU-0001",
        schema=Hypothesis,
        temperature=0.2,
    )

    assert resp.provider == "nebius"
    assert resp.structured_data is not None
    assert resp.structured_data["hypothesis_id"] == "hyp-ai-001"
    assert resp.usage["total_tokens"] == 180
    assert resp.cost > 0.0

    await gateway.aclose()
    settings.nebius_api_key = None


@pytest.mark.asyncio
async def test_hypothesis_generator_incorporates_nebius_response():
    """Verify HypothesisGenerator actively ingests the model's live hypothesis."""
    settings = get_settings()
    settings.nebius_api_key = "test-live-key"
    settings.nebius_base_url = "https://api.tokenfactory.nebius.com/v1"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/models"):
            return httpx.Response(
                200,
                json={"data": [{"id": "meta-llama/Meta-Llama-3.1-70B-Instruct"}]},
            )
        if path.endswith("/chat/completions"):
            return httpx.Response(
                200,
                json={
                    "id": "chatcmpl-test",
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(
                                    {
                                        "hypothesis_id": "hyp-CAU-0001-nebius",
                                        "causal_claim": "Live Nebius Model diagnosed GPU contention in cloud service",
                                        "expected_observation": "Queue depth spike",
                                        "falsifying_observation": "Stable queue depth",
                                        "intervention": "Scale cloud replica instances",
                                    }
                                ),
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
                },
            )
        return httpx.Response(404)

    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.tokenfactory.nebius.com/v1",
    )
    gateway = NebiusModelGateway(client=mock_client)

    generator = HypothesisGenerator(model_gateway=gateway)
    incident = Incident(
        id="CAU-0001",
        title="Perception Latency Breach",
        description="Robot missed freshness deadline",
        system_name="RobotFleet-1",
    )

    hyps = await generator.generate(incident)
    # Check that the Nebius-generated hypothesis is included!
    nebius_hyps = [h for h in hyps if "nebius" in h.hypothesis_id.lower()]
    assert len(nebius_hyps) == 1
    assert "Live Nebius Model" in nebius_hyps[0].causal_claim

    await gateway.aclose()
    settings.nebius_api_key = None
