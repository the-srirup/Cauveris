"""
Patch generator for creating targeted candidate fixes and regression tests.
"""
import logging
from typing import List
from cauveris.schemas.experiment import Experiment
from cauveris.schemas.patch import PatchCandidate
from cauveris.config import get_settings

logger = logging.getLogger(__name__)


class PatchGenerator:
    """Generates candidate patches and regression tests from experiment results."""

    def __init__(self):
        self.settings = get_settings()

    async def generate(self, experiments: List[Experiment]) -> List[PatchCandidate]:
        """
        Generate patch candidates from experiment results.

        Args:
            experiments: List of completed experiments

        Returns:
            List of PatchCandidate objects
        """
        logger.info(f"Generating patches from {len(experiments)} experiments")
        completed_experiments = [
            exp for exp in experiments
            if exp.status in ["COMPLETED", "SIMULATED", "REPRODUCED"]
        ]
        logger.info(f"Found {len(completed_experiments)} completed experiments to analyze")

        if not completed_experiments:
            logger.warning("No completed experiments found; considering all experiments")
            completed_experiments = experiments

        # Sort experiments by lowest reproduction rate (most effective fix first)
        completed_experiments.sort(key=lambda x: getattr(x, "reproduction_rate", 1.0))

        patch_candidates = []
        for exp in completed_experiments:
            try:
                patch = await self._generate_patch_from_experiment(exp)
                if patch:
                    patch_candidates.append(patch)
                    logger.info(
                        f"Generated patch {patch.candidate_id} for {exp.experiment_id} "
                        f"(score: {patch.score:.2f}, repro_rate: {exp.reproduction_rate:.1%})"
                    )
            except Exception as e:
                logger.error(f"Failed to generate patch from experiment {exp.experiment_id}: {e}")

        logger.info(f"Generated {len(patch_candidates)} patch candidates in total")
        return patch_candidates

    async def _generate_patch_from_experiment(self, experiment: Experiment) -> PatchCandidate:
        """Generate a patch candidate from a single experiment."""
        hyp_id = experiment.hypothesis_id.lower()
        intervention = experiment.intervention.lower()

        # Base patch structure
        patch = PatchCandidate(
            candidate_id=f"patch-{experiment.experiment_id}",
            affected_files=[],
            lines_changed=0,
            unified_diff="",
            regression_test_patch=None,
            build_state="pending",
            existing_test_state="pending",
            replay_state="pending",
            safety_result="pending",
            latency_result="pending",
            policy_findings=[],
            score=0.0,
            rejection_reason=None,
            applied_cleanly=False,
            regression_test_fails_before=False,
            regression_test_passes_after=False,
            original_failure_not_reproduced=False,
            existing_tests_pass=False,
            safety_invariants_pass=False,
            performance_within_budget=False,
            forbidden_change_scan_passes=False,
            rollback_test_passes=False,
            verified=False,
        )

        if "h1" in hyp_id or "batching" in intervention:
            patch = self._generate_batching_patch(patch, experiment)
        elif "h2" in hyp_id or "qos" in intervention:
            patch = self._generate_qos_patch(patch, experiment)
        elif "h3" in hyp_id or "clock" in intervention:
            patch = self._generate_clock_patch(patch, experiment)
        elif "h4" in hyp_id or "gpu" in intervention:
            patch = self._generate_gpu_patch(patch, experiment)
        else:
            patch = self._generate_generic_patch(patch, experiment)

        # Calculate score based on experiment reproduction rate and patch properties
        patch.score = self._calculate_patch_score(patch, experiment)
        return patch

    def _generate_batching_patch(self, patch: PatchCandidate, experiment: Experiment) -> PatchCandidate:
        """Generate patch for dynamic batching window (winning root cause fix)."""
        patch.affected_files = ["config/inference.yaml"]
        patch.lines_changed = 1

        patch.unified_diff = """--- a/config/inference.yaml
+++ b/config/inference.yaml
@@ -4,3 +4,3 @@
 dynamic_batching:
   enabled: true
   max_batch_size: 8
-  batching_window_ms: 200
+  batching_window_ms: 100
   timeout_ms: 500
"""

        patch.regression_test_patch = """--- /dev/null
+++ b/tests/test_freshness_budget.py
@@ -0,0 +1,24 @@
+import unittest
+import yaml
+
+class TestFreshnessBudgetRegression(unittest.TestCase):
+    def test_batching_window_within_budget(self):
+        with open("config/inference.yaml", "r") as f:
+            cfg = yaml.safe_load(f)
+        window = cfg.get("dynamic_batching", {}).get("batching_window_ms", 200)
+        # Freshness budget is 120ms. Batching window must not exceed 100ms.
+        self.assertLessEqual(window, 100, f"Batching window {window}ms exceeds safe budget")
+
+    def test_estimated_latency_under_freshness_budget(self):
+        with open("config/inference.yaml", "r") as f:
+            cfg = yaml.safe_load(f)
+        window = cfg.get("dynamic_batching", {}).get("batching_window_ms", 200)
+        # Estimated latency formula: (window * 0.52) + 36ms GPU + 14ms network
+        estimated_latency = (window * 0.52) + 36.0 + 14.0
+        self.assertLess(estimated_latency, 120.0, f"Total latency {estimated_latency}ms exceeds 120ms freshness budget")
+
+if __name__ == "__main__":
+    unittest.main()
"""
        return patch

    def _generate_qos_patch(self, patch: PatchCandidate, experiment: Experiment) -> PatchCandidate:
        """Generate patch for ROS QoS depth."""
        patch.affected_files = ["source/robot-stack/src/detection_client.py"]
        patch.lines_changed = 2
        patch.unified_diff = """--- a/source/robot-stack/src/detection_client.py
+++ b/source/robot-stack/src/detection_client.py
@@ -3,2 +3,2 @@
-        self.qos_depth = 10
+        self.qos_depth = 1
         self.keep_last = True
"""
        return patch

    def _generate_clock_patch(self, patch: PatchCandidate, experiment: Experiment) -> PatchCandidate:
        """Generate patch for clock skew tolerance."""
        patch.affected_files = ["config/robot_params.yaml"]
        patch.lines_changed = 2
        patch.unified_diff = """--- a/config/robot_params.yaml
+++ b/config/robot_params.yaml
@@ -5,2 +5,3 @@
   detection_freshness_budget_ms: 120
+  max_clock_skew_tolerance_ms: 25
   control_loop_deadline_ms: 100
"""
        return patch

    def _generate_gpu_patch(self, patch: PatchCandidate, experiment: Experiment) -> PatchCandidate:
        """Generate patch for GPU workload."""
        patch.affected_files = ["config/inference.yaml"]
        patch.lines_changed = 2
        patch.unified_diff = """--- a/config/inference.yaml
+++ b/config/inference.yaml
@@ -4,2 +4,3 @@
   max_batch_size: 4
+  power_limit_watts: 140
"""
        return patch

    def _generate_generic_patch(self, patch: PatchCandidate, experiment: Experiment) -> PatchCandidate:
        """Generate generic fallback patch."""
        patch.affected_files = ["config/inference.yaml"]
        patch.lines_changed = 1
        patch.unified_diff = """--- a/config/inference.yaml
+++ b/config/inference.yaml
@@ -4,1 +4,1 @@
-  batching_window_ms: 200
+  batching_window_ms: 100
"""
        return patch

    def _calculate_patch_score(self, patch: PatchCandidate, experiment: Experiment) -> float:
        """Calculate score based on reproduction rate reduction and minimality."""
        score = 0.50

        # Reproduction elimination reward
        if experiment.reproduction_rate == 0.0:
            score += 0.35
        elif experiment.reproduction_rate < 0.20:
            score += 0.20
        elif experiment.reproduction_rate < 0.50:
            score += 0.05
        else:
            score -= 0.20

        # Minimality of diff
        if patch.lines_changed <= 2:
            score += 0.07
        elif patch.lines_changed <= 5:
            score += 0.03

        # Single file change preferred
        if len(patch.affected_files) == 1:
            score += 0.05

        return round(min(0.99, max(0.10, score)), 2)
