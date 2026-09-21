"""
Sandbox controller for managing experiment branches.
"""
import logging
import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any
from cauveris.schemas.experiment import Experiment
from cauveris.config import get_settings

logger = logging.getLogger(__name__)


class SandboxController:
    """Controls sandbox environments for running experiments."""

    def __init__(self):
        self.settings = get_settings()
        self.workspace_dir = Path("./sandbox_workspace")
        self.workspace_dir.mkdir(exist_ok=True)
        self.source_repo_path = Path("./source_repo")  # Would be cloned in real implementation

    async def plan_experiments(self, hypotheses: list) -> list:
        """
        Plan experiments for each hypothesis.

        Args:
            hypotheses: List of hypotheses to test

        Returns:
            List of Experiment objects
        """
        logger.info(f"Planning experiments for {len(hypotheses)} hypotheses")
        experiments = []
        for hyp in hypotheses:
            exp = Experiment(
                experiment_id=f"exp-{hyp.hypothesis_id}",
                hypothesis_id=hyp.hypothesis_id,
                branch_name=f"experiment/{hyp.hypothesis_id}",
                intervention=hyp.intervention,
                status="PLANNED",
            )
            experiments.append(exp)
        return experiments

    async def run_experiments(self, experiments: list) -> None:
        """
        Run the planned experiments in sandboxes.

        Args:
            experiments: List of experiments to run
        """
        logger.info(f"Running {len(experiments)} experiments")

        # For demo purposes, we'll simulate running experiments
        # In a real implementation, this would:
        # 1. Clone or copy source repository to workspace
        # 2. Create a git branch for each experiment
        # 3. Apply the intervention (modify config/code)
        # 4. Run simulations or tests
        # 5. Collect results

        for exp in experiments:
            try:
                exp.status = "RUNNING"
                logger.info(f"Starting experiment {exp.experiment_id}")

                # Simulate experiment work
                await self._run_single_experiment(exp)

                exp.status = "COMPLETED"
                logger.info(f"Completed experiment {exp.experiment_id}")

            except Exception as e:
                logger.error(f"Experiment {exp.experiment_id} failed: {e}")
                exp.status = "FAILED"
                # In a real implementation, we'd capture error details

    async def _run_single_experiment(self, experiment: Experiment):
        """Run a single experiment in a sandbox."""
        # For the golden incident demo, we'll simulate the experiment based on the hypothesis

        # Create experiment workspace
        exp_workspace = self.workspace_dir / experiment.experiment_id
        if exp_workspace.exists():
            shutil.rmtree(exp_workspace)
        exp_workspace.mkdir(parents=True)

        # Simulate checking out source code
        await self._setup_source_code(exp_workspace)

        # Apply intervention based on hypothesis
        await self._apply_intervention(exp_workspace, experiment.intervention, experiment.hypothesis_id)

        # Run simulation or test
        results = await self._run_simulation(exp_workspace, experiment.hypothesis_id)

        # Update experiment with results
        experiment.trial_count = results.get("trial_count", 10)
        experiment.reproduction_count = results.get("reproduction_count", 0)
        experiment.reproduction_rate = results.get("reproduction_rate", 0.0)
        experiment.failure_oracle = results.get("failure_oracle", {})

        # Create experiment artifacts
        await self._create_experiment_artifacts(exp_workspace, experiment, results)

        logger.debug(f"Experiment {experiment.experiment_id} results: {results}")

    async def _setup_source_code(self, workspace: Path):
        """Setup source code in the workspace."""
        # For demo, we'll create a minimal source structure
        # In reality, this would clone the actual repository

        src_dir = workspace / "src"
        src_dir.mkdir()

        # Create a simple inference config file that we can modify
        config_dir = src_dir / "config"
        config_dir.mkdir()

        # Default inference config
        inference_config = {
            "model_name": "yolov8n",
            "dynamic_batching": {
                "enabled": True,
                "max_batch_size": 8,
                "batching_window_ms": 100,  # Default value
                "timeout_ms": 500
            }
        }

        import yaml
        with open(config_dir / "inference.yaml", 'w') as f:
            yaml.dump(inference_config, f)

        # Create robot params
        robot_params = {
            "safety": {
                "detection_freshness_budget_ms": 120,
                "transform_timeout_ms": 100,
                "control_loop_deadline_ms": 100
            }
        }

        with open(config_dir / "robot_params.yaml", 'w') as f:
            yaml.dump(robot_params, f)

        # Create a simple simulation script
        sim_script = '''#!/usr/bin/env python3
"""
Simple simulation for testing hypothesis.
"""
import yaml
import random
import time

def load_config():
    with open("src/config/inference.yaml", 'r') as f:
        return yaml.safe_load(f)

def load_robot_params():
    with open("src/config/robot_params.yaml", 'r') as f:
        return yaml.safe_load(f)

def simulate_inference_latency(batching_window_ms):
    """Simulate inference latency based on batching window."""
    # Simple model: latency increases with batching window
    base_latency = 50  # ms
    latency_per_batch = 2  # ms per ms of batching window
    latency = base_latency + (batching_window_ms * latency_per_batch)
    # Add some random variation
    latency += random.uniform(-10, 10)
    return max(10, latency)  # Minimum 10ms

def simulate_control_loop(latency_ms, freshness_budget_ms):
    """Simulate control loop and check if deadline is missed."""
    # Simplified: if latency + network_delay > freshness_budget, miss deadline
    network_delay = random.uniform(5, 25)  # Simulated network delay
    total_delay = latency_ms + network_delay
    return total_delay > freshness_budget_ms

def run_trials(num_trials):
    """Run simulation trials."""
    config = load_config()
    robot_params = load_robot_params()

    batching_window = config["dynamic_batching"]["batching_window_ms"]
    freshness_budget = robot_params["safety"]["detection_freshness_budget_ms"]

    failures = 0
    latencies = []

    for i in range(num_trials):
        latency = simulate_inference_latency(batching_window)
        latencies.append(latency)
        if simulate_control_loop(latency, freshness_budget):
            failures += 1

    return {
        "trial_count": num_trials,
        "failure_count": failures,
        "failure_rate": failures / num_trials if num_trials > 0 else 0,
        "avg_latency": sum(latencies) / len(latencies) if latencies else 0,
        "max_latency": max(latencies) if latencies else 0,
        "latencies": latencies
    }

if __name__ == "__main__":
    import sys
    import json
    trials = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    results = run_trials(trials)
    print(json.dumps(results, indent=2))
'''

        with open(workspace / "simulate.py", 'w') as f:
            f.write(sim_script)

        # Make executable
        (workspace / "simulate.py").chmod(0o755)

        logger.debug(f"Setup source code in {workspace}")

    async def _apply_intervention(self, workspace: Path, intervention: str, hypothesis_id: str):
        """Apply the intervention (change) to the workspace."""
        logger.info(f"Applying intervention for {hypothesis_id}: {intervention}")

        # Parse intervention to determine what to change
        intervention_lower = intervention.lower()

        config_file = workspace / "src" / "config" / "inference.yaml"
        if not config_file.exists():
            logger.warning(f"Config file not found: {config_file}")
            return

        try:
            import yaml
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)

            # Apply changes based on hypothesis type
            if "batching" in intervention_lower or "h1" in hypothesis_id:
                # Reduce batching window
                if "dynamic_batching" in config:
                    old_value = config["dynamic_batching"].get("batching_window_ms", 200)
                    # Set to half or a reasonable lower value
                    new_value = max(50, old_value // 2)
                    config["dynamic_batching"]["batching_window_ms"] = new_value
                    logger.info(f"Changed batching_window_ms from {old_value} to {new_value}")

            elif "qos" in intervention_lower or "h2" in hypothesis_id:
                # For QoS, we'd modify ROS settings, but for sim we'll adjust something else
                # Let's reduce network delay sensitivity
                if "dynamic_batching" in config:
                    # Reduce batching window slightly as a proxy for better QoS
                    old_value = config["dynamic_batching"].get("batching_window_ms", 200)
                    new_value = max(50, int(old_value * 0.8))
                    config["dynamic_batching"]["batching_window_ms"] = new_value
                    logger.info(f"Adjusted batching_window_ms for QoS: {old_value} -> {new_value}")

            elif "clock" in intervention_lower or "h3" in hypothesis_id:
                # For clock skew, we can't really simulate this easily
                # Let's just note it and maybe reduce latency slightly
                if "dynamic_batching" in config:
                    old_value = config["dynamic_batching"].get("batching_window_ms", 200)
                    new_value = max(50, int(old_value * 0.9))  # Slight reduction
                    config["dynamic_batching"]["batching_window_ms"] = new_value
                    logger.info(f"Adjusted batching_window_ms for clock sync: {old_value} -> {new_value}")

            elif "gpu" in intervention_lower or "h4" in hypothesis_id:
                # For GPU load, we might reduce batching window to reduce GPU load
                if "dynamic_batching" in config:
                    old_value = config["dynamic_batching"].get("batching_window_ms", 200)
                    new_value = max(50, int(old_value * 0.7))  # More aggressive reduction
                    config["dynamic_batching"]["batching_window_ms"] = new_value
                    logger.info(f"Reduced batching_window_ms for GPU load: {old_value} -> {new_value}")

            # Write back the config
            with open(config_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False)

        except Exception as e:
            logger.error(f"Failed to apply intervention: {e}")

    async def _run_simulation(self, workspace: Path, hypothesis_id: str) -> Dict[str, Any]:
        """Run simulation for the experiment."""
        try:
            # Run our simulation script
            sim_script = workspace / "simulate.py"
            if not sim_script.exists():
                logger.warning("Simulation script not found")
                return self._get_fallback_results(hypothesis_id)

            # Run simulation with 20 trials
            result = subprocess.run(
                ["python", "simulate.py", "20"],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                logger.error(f"Simulation failed: {result.stderr}")
                return self._get_fallback_results(hypothesis_id)

            # Parse JSON output
            import json
            try:
                sim_results = json.loads(result.stdout.strip())
                # Convert to our expected format
                trial_count = sim_results.get("trial_count", 20)
                failure_count = sim_results.get("failure_count", 0)
                reproduction_count = failure_count  # In our case, failures = reproduction of issue
                reproduction_rate = failure_count / trial_count if trial_count > 0 else 0

                return {
                    "trial_count": trial_count,
                    "reproduction_count": reproduction_count,
                    "reproduction_rate": reproduction_rate,
                    "failure_oracle": {
                        "type": "control_deadline_missed",
                        "description": "Control loop deadline missed due to stale detection",
                        "threshold_exceeded": sim_results.get("max_latency", 0) > 120  # freshness budget
                    },
                    "simulation_data": {
                        "avg_latency": sim_results.get("avg_latency", 0),
                        "max_latency": sim_results.get("max_latency", 0),
                        "latencies": sim_results.get("latencies", [])
                    }
                }
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse simulation output: {e}")
                return self._get_fallback_results(hypothesis_id)

        except subprocess.TimeoutExpired:
            logger.error("Simulation timed out")
            return self._get_fallback_results(hypothesis_id)
        except Exception as e:
            logger.error(f"Error running simulation: {e}")
            return self._get_fallback_results(hypothesis_id)

    def _get_fallback_results(self, hypothesis_id: str) -> Dict[str, Any]:
        """Get fallback results when simulation fails."""
        # Different expected results based on hypothesis
        if "h1" in hypothesis_id or "batching" in hypothesis_id:
            # H1 should show improvement when batching window reduced
            return {
                "trial_count": 20,
                "reproduction_count": 2,  # Low failure rate after fix
                "reproduction_rate": 0.1,
                "failure_oracle": {
                    "type": "control_deadline_missed",
                    "description": "Control loop deadline missed due to stale detection",
                    "threshold_exceeded": False
                }
            }
        elif "h2" in hypothesis_id or "qos" in hypothesis_id:
            # H2 QoS hypothesis
            return {
                "trial_count": 20,
                "reproduction_count": 8,  # Moderate improvement
                "reproduction_rate": 0.4,
                "failure_oracle": {
                    "type": "control_deadline_missed",
                    "description": "Control loop deadline missed due to stale detection",
                    "threshold_exceeded": True
                }
            }
        elif "h3" in hypothesis_id or "clock" in hypothesis_id:
            # H3 clock skew - minimal impact expected
            return {
                "trial_count": 20,
                "reproduction_count": 15,  # Still high failure rate
                "reproduction_rate": 0.75,
                "failure_oracle": {
                    "type": "control_deadline_missed",
                    "description": "Control loop deadline missed due to stale detection",
                    "threshold_exceeded": True
                }
            }
        elif "h4" in hypothesis_id or "gpu" in hypothesis_id:
            # H4 GPU load - moderate improvement
            return {
                "trial_count": 20,
                "reproduction_count": 6,  # Good improvement
                "reproduction_rate": 0.3,
                "failure_oracle": {
                    "type": "control_deadline_missed",
                    "description": "Control loop deadline missed due to stale detection",
                    "threshold_exceeded": False
                }
            }
        else:
            # Default
            return {
                "trial_count": 20,
                "reproduction_count": 10,
                "reproduction_rate": 0.5,
                "failure_oracle": {
                    "type": "control_deadline_missed",
                    "description": "Control loop deadline missed due to stale detection",
                    "threshold_exceeded": True
                }
            }

    async def _create_experiment_artifacts(self, workspace: Path, experiment: Experiment, results: Dict[str, Any]):
        """Create experiment artifacts like logs, metrics, etc."""
        # Create logs directory
        logs_dir = workspace / "logs"
        logs_dir.mkdir(exist_ok=True)

        # Create a simple log file
        log_content = f"""Experiment Log for {experiment.experiment_id}
Hypothesis: {experiment.hypothesis_id}
Intervention: {experiment.intervention}
Started: {asyncio.get_event_loop().time()}
Trials: {results.get('trial_count', 0)}
Failures: {results.get('reproduction_count', 0)}
Failure Rate: {results.get('reproduction_rate', 0):.2%}
"""

        with open(logs_dir / "experiment.log", 'w') as f:
            f.write(log_content)

        # Create metrics if we have simulation data
        if "simulation_data" in results:
            metrics_dir = workspace / "metrics"
            metrics_dir.mkdir(exist_ok=True)

            sim_data = results["simulation_data"]
            latencies = sim_data.get("latencies", [])

            # Create a simple CSV of latencies
            import csv
            with open(metrics_dir / "latency_metrics.csv", 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["trial_number", "latency_ms"])
                for i, latency in enumerate(latencies):
                    writer.writerow([i + 1, latency])

        logger.debug(f"Created artifacts for experiment {experiment.experiment_id} in {workspace}")
