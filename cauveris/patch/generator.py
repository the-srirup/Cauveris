"""
Patch generator for creating targeted candidate fixes and regression tests.
"""
import logging
from pathlib import Path
from typing import List, Dict, Union, Any
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

    def generate_standalone_installer(self, patch: PatchCandidate) -> str:
        """
        Generate a self-contained, zero-dependency Python script that can be
        directly imported or executed in the infected target space to apply the fix.
        """
        candidate_repr = repr(patch.candidate_id)
        affected_repr = repr(patch.affected_files)
        diff_repr = repr(patch.unified_diff)
        test_patch_repr = repr(patch.regression_test_patch or "")

        installer_template = f'''#!/usr/bin/env python3
"""
Cauveris Automated Patch Installer & Exporter
Candidate: {patch.candidate_id}
Affected Files: {patch.affected_files}

Zero-dependency executable patch script generated by Cauveris.
Can be executed directly or imported in Python inside the infected space.

Usage:
    python apply_patch.py                # Apply fix directly to current directory
    python apply_patch.py --target <dir> # Apply fix to specific workspace
    python apply_patch.py --check        # Verify patch applies cleanly without writing
    python apply_patch.py --status       # Check infection/patch status
    python apply_patch.py --rollback     # Revert fix to pre-patch state

Python API:
    import apply_patch
    apply_patch.apply()                  # Apply to current directory
    apply_patch.rollback()               # Revert
"""
import sys
import shutil
import argparse
from pathlib import Path

CANDIDATE_ID = {candidate_repr}
AFFECTED_FILES = {affected_repr}
UNIFIED_DIFF = {diff_repr}
REGRESSION_TEST_PATCH = {test_patch_repr}


def _find_file(base_dir: Path, relative_path: str):
    """Find file at exact relative path or search recursively by filename."""
    candidate = base_dir / relative_path
    if candidate.exists():
        return candidate
    filename = Path(relative_path).name
    matches = list(base_dir.rglob(filename))
    if matches:
        return matches[0]
    return None


def _parse_hunks(diff_text: str):
    """Extract removed lines, added lines, and target filenames from a unified diff."""
    target_file = None
    removals = []
    additions = []

    for line in diff_text.splitlines():
        if line.startswith("--- "):
            pass
        elif line.startswith("+++ "):
            clean_path = line[4:].strip()
            if clean_path.startswith("b/"):
                clean_path = clean_path[2:]
            target_file = clean_path
        elif line.startswith("-") and not line.startswith("---"):
            removals.append(line[1:])
        elif line.startswith("+") and not line.startswith("+++"):
            additions.append(line[1:])

    return target_file, removals, additions


def check(target_dir=None) -> bool:
    """Check if the patch can be applied cleanly without modifying disk."""
    return apply(target_dir=target_dir, dry_run=True)


def status(target_dir=None) -> str:
    """
    Check status of the infected space.
    Returns 'PATCHED', 'INFECTED', or 'MISSING_FILES'.
    """
    root = Path(target_dir or Path.cwd()).resolve()
    target_file_rel, removals, additions = _parse_hunks(UNIFIED_DIFF)
    if not target_file_rel:
        return "UNKNOWN"

    file_path = _find_file(root, target_file_rel)
    if not file_path:
        return "MISSING_FILES"

    content = file_path.read_text(encoding="utf-8")
    is_patched = all(add in content for add in additions)
    is_infected = any(rem in content for rem in removals)

    if is_patched and not is_infected:
        return "PATCHED"
    elif is_infected:
        return "INFECTED"
    return "UNKNOWN"


def apply(target_dir=None, dry_run: bool = False) -> bool:
    """
    Apply the patch directly to the target infected space.

    Args:
        target_dir: Directory of the infected space (defaults to current directory)
        dry_run: If True, tests application without writing to disk

    Returns:
        True if patch was applied or verified, False otherwise
    """
    root = Path(target_dir or Path.cwd()).resolve()
    print(f"[Cauveris Patch] Target space: {{root}}")
    print(f"[Cauveris Patch] Candidate: {{CANDIDATE_ID}}")

    target_file_rel, removals, additions = _parse_hunks(UNIFIED_DIFF)
    if not target_file_rel:
        print("[Cauveris Patch] Error: Could not determine target file from diff.", file=sys.stderr)
        return False

    file_path = _find_file(root, target_file_rel)
    if not file_path:
        print(f"[Cauveris Patch] Error: File '{{target_file_rel}}' not found in {{root}}", file=sys.stderr)
        return False

    print(f"[Cauveris Patch] Located target file: {{file_path.relative_to(root)}}")
    content = file_path.read_text(encoding="utf-8")

    # Check if already patched
    if all(add in content for add in additions) and not any(rem in content for rem in removals):
        print("[Cauveris Patch] Target space is already patched. Nothing to do.")
        return True

    # Check if removals are present
    for rem in removals:
        if rem not in content:
            print(f"[Cauveris Patch] Warning: Expected line to replace not found: '{{rem.strip()}}'", file=sys.stderr)
            return False

    # Compute new content
    new_content = content
    for rem, add in zip(removals, additions):
        new_content = new_content.replace(rem, add, 1)

    if dry_run:
        print("[Cauveris Patch] Dry-run verification: Patch applies cleanly!")
        return True

    # Create backup before modification
    backup_file = file_path.with_suffix(file_path.suffix + ".bak")
    backup_dir = root / ".cauveris_backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    rel_backup = backup_dir / target_file_rel
    rel_backup.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy2(file_path, backup_file)
    shutil.copy2(file_path, rel_backup)
    print(f"[Cauveris Patch] Created safety backup at {{backup_file.name}}")

    # Write patched content
    file_path.write_text(new_content, encoding="utf-8")
    print(f"[Cauveris Patch] Successfully patched {{file_path.name}}")

    # Write regression test if provided
    if REGRESSION_TEST_PATCH:
        test_file_rel, _, test_additions = _parse_hunks(REGRESSION_TEST_PATCH)
        if test_file_rel:
            test_path = root / test_file_rel
            test_path.parent.mkdir(parents=True, exist_ok=True)
            test_content = "\\n".join(test_additions) + "\\n"
            test_path.write_text(test_content, encoding="utf-8")
            print(f"[Cauveris Patch] Installed regression test at {{test_file_rel}}")

    print("[Cauveris Patch] All operations completed successfully.")
    return True


def rollback(target_dir=None) -> bool:
    """
    Rollback the patch using the saved backup.

    Args:
        target_dir: Directory of the infected space (defaults to current directory)

    Returns:
        True if rollback succeeded, False otherwise
    """
    root = Path(target_dir or Path.cwd()).resolve()
    print(f"[Cauveris Patch] Rolling back in: {{root}}")

    target_file_rel, _, _ = _parse_hunks(UNIFIED_DIFF)
    if not target_file_rel:
        return False

    file_path = _find_file(root, target_file_rel)
    if not file_path:
        return False

    backup_file = file_path.with_suffix(file_path.suffix + ".bak")
    backup_dir = root / ".cauveris_backup" / target_file_rel

    restored = False
    if backup_file.exists():
        shutil.copy2(backup_file, file_path)
        backup_file.unlink()
        restored = True
    elif backup_dir.exists():
        shutil.copy2(backup_dir, file_path)
        restored = True

    if not restored:
        print("[Cauveris Patch] Error: No backup found to restore.", file=sys.stderr)
        return False

    # Remove regression test if installed
    if REGRESSION_TEST_PATCH:
        test_file_rel, _, _ = _parse_hunks(REGRESSION_TEST_PATCH)
        if test_file_rel:
            test_path = root / test_file_rel
            if test_path.exists():
                test_path.unlink()
                print(f"[Cauveris Patch] Removed installed regression test {{test_file_rel}}")

    print(f"[Cauveris Patch] Rollback restored {{file_path.name}} to pre-patch state.")
    return True


def main():
    parser = argparse.ArgumentParser(description="Cauveris Self-Applying Patch Installer")
    parser.add_argument("--target", default=".", help="Target workspace/directory to patch (default: current directory)")
    parser.add_argument("--check", action="store_true", help="Verify patch applies cleanly without writing")
    parser.add_argument("--status", action="store_true", help="Display current patch status (INFECTED / PATCHED)")
    parser.add_argument("--rollback", action="store_true", help="Revert applied patch using backup")

    args = parser.parse_args()

    if args.status:
        st = status(args.target)
        print(f"Status: {{st}}")
        sys.exit(0 if st == "PATCHED" else 1)
    elif args.rollback:
        success = rollback(args.target)
        sys.exit(0 if success else 1)
    elif args.check:
        success = check(args.target)
        sys.exit(0 if success else 1)
    else:
        success = apply(args.target)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
'''
        return installer_template

    def export_patch(
        self,
        patch: PatchCandidate,
        destination_dir: Union[Path, str],
        export_installer: bool = True
    ) -> Dict[str, Path]:
        """
        Export standalone patch files and executable installer to a directory.

        Args:
            patch: The PatchCandidate to export
            destination_dir: Target output directory
            export_installer: Whether to also generate standalone apply_patch.py

        Returns:
            Dictionary mapping artifact names to their created Paths
        """
        dest = Path(destination_dir)
        dest.mkdir(parents=True, exist_ok=True)

        patch_file = dest / "fix.patch"
        patch_file.write_text(patch.unified_diff, encoding="utf-8")

        results = {"patch_file": patch_file}

        if patch.regression_test_patch:
            reg_file = dest / "regression_test.patch"
            reg_file.write_text(patch.regression_test_patch, encoding="utf-8")
            results["regression_test_patch"] = reg_file

        if export_installer:
            installer_code = self.generate_standalone_installer(patch)
            installer_file = dest / "apply_patch.py"
            installer_file.write_text(installer_code, encoding="utf-8")
            results["installer_script"] = installer_file

        return results

    def apply_to_workspace(
        self,
        patch: PatchCandidate,
        workspace_dir: Union[Path, str],
        dry_run: bool = False
    ) -> bool:
        """
        Apply patch directly to a specified workspace.

        Args:
            patch: The PatchCandidate to apply
            workspace_dir: Directory of the infected space
            dry_run: Test without modifying files if True

        Returns:
            True if patch succeeded, False otherwise
        """
        installer_code = self.generate_standalone_installer(patch)
        scope: Dict[str, Any] = {}
        exec(installer_code, scope)
        apply_fn = scope.get("apply")
        if callable(apply_fn):
            return bool(apply_fn(target_dir=str(workspace_dir), dry_run=dry_run))
        return False

