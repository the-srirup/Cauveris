"""
Local fixture model gateway for development and testing.
Provides deterministic, rule-based responses instead of real LLM calls.
"""
import asyncio
import json
from typing import Any, Dict, Optional, Type
from pydantic import BaseModel
from cauveris.schemas.hypothesis import Hypothesis
from cauveris.schemas.experiment import Experiment
from cauveris.schemas.patch import PatchCandidate, VerificationReport
from .base import ModelGateway, ModelResponse, extract_json_from_text
from cauveris.config import get_settings
import logging

logger = logging.getLogger(__name__)


class LocalModelGateway(ModelGateway):
    """Local fixture model gateway that provides deterministic responses."""

    def __init__(self):
        self.settings = get_settings()

    def is_available(self) -> bool:
        """Local gateway is always available."""
        return True

    async def generate(
        self,
        prompt: str,
        schema: Optional[Type[BaseModel]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> ModelResponse:
        """
        Generate a deterministic response based on prompt patterns.
        This is used for development and testing without real LLM calls.
        """
        # Simulate some processing time
        await asyncio.sleep(0.1)

        # Determine what type of response is needed based on prompt
        prompt_lower = prompt.lower()

        if "hypothesis" in prompt_lower or "root cause" in prompt_lower:
            content = self._generate_hypothesis_response()
            structured_data = self._parse_hypothesis_json(content) if schema == Hypothesis else None
        elif "patch" in prompt_lower or "fix" in prompt_lower:
            content = self._generate_patch_response()
            structured_data = self._parse_patch_json(content) if schema == PatchCandidate else None
        elif "experiment" in prompt_lower or "intervention" in prompt_lower:
            content = self._generate_experiment_response()
            structured_data = self._parse_experiment_json(content) if schema == Experiment else None
        elif "validation" in prompt_lower or "verify" in prompt_lower:
            content = self._generate_verification_response()
            structured_data = self._parse_verification_json(content) if schema == VerificationReport else None
        else:
            # Default response
            content = '{"status": "processed", "message": "Local fixture response"}'
            structured_data = extract_json_from_text(content)

        return ModelResponse(
            content=content,
            structured_data=structured_data,
            model_used="local-fixture-v1",
            provider="local",
            usage={"prompt_tokens": len(prompt.split()), "completion_tokens": 50},
            cost=0.0
        )

    def _generate_hypothesis_response(self) -> str:
        """Generate a fixture hypothesis response."""
        return json.dumps({
            "hypothesis_id": "hyp-001",
            "causal_claim": "Increased dynamic batching window in deployment v42 caused inference P99 latency to exceed robot freshness budget",
            "status": "INFERRED",
            "supporting_artifact_ids": ["deployments/events.json:v42", "metrics/gpu.csv:queue-depth"],
            "contradicting_artifact_ids": [],
            "missing_evidence": "Direct latency measurements from inference service logs",
            "confidence_prior": 0.75,
            "expected_observation": "Inference latency P99 > 120ms after v42 deployment",
            "falsifying_observation": "Inference latency P99 < 100ms after v42 deployment",
            "intervention": "Reduce dynamic batching window to v41 levels and monitor latency",
            "estimated_trials": 5,
            "estimated_cost": 2.5,
            "likely_files": ["src/inference/batching_config.py", "src/inference/server.py"],
            "likely_parameters": ["batching_window_ms", "max_batch_size"],
            "safety_constraints": ["Do not reduce batching below minimum throughput requirements"]
        }, indent=2)

    def _generate_patch_response(self) -> str:
        """Generate a fixture patch response."""
        return json.dumps({
            "candidate_id": "patch-001",
            "affected_files": ["src/inference/batching_config.py"],
            "lines_changed": 3,
            "unified_diff": "--- a/src/inference/batching_config.py\n+++ b/src/inference/batching_config.py\n@@ -10,7 +10,7 @@\n -BATCHING_WINDOW_MS = 200  # v42 increase\n +BATCHING_WINDOW_MS = 100  # v41 value\n  # Other batching parameters\n  MAX_BATCH_SIZE = 32",
            "regression_test_patch": None,
            "build_state": "success",
            "existing_test_state": "pass",
            "replay_state": "success",
            "safety_result": "pass",
            "latency_result": "within_budget",
            "policy_findings": [],
            "score": 0.95,
            "rejection_reason": None,
            "applied_cleanly": True,
            "regression_test_fails_before": True,
            "regression_test_passes_after": True,
            "original_failure_not_reproduced": True,
            "existing_tests_pass": True,
            "safety_invariants_pass": True,
            "performance_within_budget": True,
            "forbidden_change_scan_passes": True,
            "rollback_test_passes": True,
            "verified": True
        }, indent=2)

    def _generate_experiment_response(self) -> str:
        """Generate a fixture experiment response."""
        return json.dumps({
            "experiment_id": "exp-001",
            "hypothesis_id": "hyp-001",
            "branch_name": "experiment/hyp-001-batching-window",
            "intervention": "Reduced dynamic batching window from 200ms to 100ms",
            "status": "REPRODUCED",
            "trial_count": 10,
            "reproduction_count": 8,
            "reproduction_rate": 0.8,
            "failure_oracle": "Safety stop triggered due to missed control deadline",
            "logs_artifact_id": "logs/exp-001-system.log",
            "metrics_artifact_id": "metrics/exp-001-latency.csv",
            "replay_artifact_id": "recordings/exp-001-replay.mcap",
            "conclusion": "Hypothesis supported: reduced batching window decreased P99 latency below freshness budget"
        }, indent=2)

    def _generate_verification_response(self) -> str:
        """Generate a fixture verification response."""
        return json.dumps({
            "patch_candidate_id": "patch-001",
            "applies_cleanly": True,
            "regression_test_fails_before": True,
            "regression_test_passes_after": True,
            "original_failure_not_reproduced": True,
            "existing_tests_pass": True,
            "safety_invariants_pass": True,
            "performance_within_budget": True,
            "forbidden_change_scan_passes": True,
            "rollback_test_passes": True,
            "verified": True,
            "details": {
                "build_time_seconds": 45.2,
                "test_pass_rate": 1.0,
                "safety_checks_passed": 8,
                "performance_regression_percent": -2.1
            }
        }, indent=2)

    def _parse_hypothesis_json(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse hypothesis JSON from content."""
        try:
            data = json.loads(content)
            # Validate required fields
            required_fields = ["hypothesis_id", "causal_claim", "status"]
            if all(field in data for field in required_fields):
                return data
        except json.JSONDecodeError:
            pass
        return extract_json_from_text(content)

    def _parse_patch_json(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse patch JSON from content."""
        try:
            data = json.loads(content)
            # Validate required fields
            required_fields = ["candidate_id", "affected_files", "unified_diff"]
            if all(field in data for field in required_fields):
                return data
        except json.JSONDecodeError:
            pass
        return extract_json_from_text(content)

    def _parse_experiment_json(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse experiment JSON from content."""
        try:
            data = json.loads(content)
            # Validate required fields
            required_fields = ["experiment_id", "hypothesis_id", "intervention", "status"]
            if all(field in data for field in required_fields):
                return data
        except json.JSONDecodeError:
            pass
        return extract_json_from_text(content)

    def _parse_verification_json(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse verification JSON from content."""
        try:
            data = json.loads(content)
            # Validate required fields
            required_fields = ["patch_candidate_id", "verified"]
            if all(field in data for field in required_fields):
                return data
        except json.JSONDecodeError:
            pass
        return extract_json_from_text(content)
