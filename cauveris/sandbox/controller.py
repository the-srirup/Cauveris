"""
Sandbox controller for managing experiment branches and interventions.
"""
import logging
import shutil
import json
import yaml
from pathlib import Path
from typing import List, Optional
from cauveris.schemas.experiment import Experiment
from cauveris.schemas.hypothesis import Hypothesis
from cauveris.config import get_settings

logger = logging.getLogger(__name__)


class SandboxController:
    """Controls sandbox environments for creating experiment branches and applying interventions."""

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.settings = get_settings()
        self.workspace_dir = Path(workspace_dir or self.settings.sandbox_workspace_path)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    async def plan_experiments(self, hypotheses: List[Hypothesis]) -> List[Experiment]:
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

    async def run_experiments(self, experiments: List[Experiment]) -> None:
        """
        Setup sandboxes and apply interventions for the planned experiments.

        Args:
            experiments: List of experiments to set up and run
        """
        logger.info(f"Setting up sandboxes and applying interventions for {len(experiments)} experiments")

        for exp in experiments:
            try:
                exp.status = "RUNNING"
                logger.info(f"Setting up branch sandbox for {exp.experiment_id}")
                await self._setup_experiment_sandbox(exp)
                logger.info(f"Sandbox ready for {exp.experiment_id}")
            except Exception as e:
                logger.error(f"Failed to setup experiment {exp.experiment_id}: {e}")
                exp.status = "FAILED"

    async def _setup_experiment_sandbox(self, exp: Experiment):
        """Prepare workspace, source code, and apply intervention."""
        exp_dir = self.workspace_dir / exp.experiment_id
        if exp_dir.exists():
            shutil.rmtree(exp_dir)
        exp_dir.mkdir(parents=True, exist_ok=True)

        # Create standard project layout in sandbox
        config_dir = exp_dir / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        src_dir = exp_dir / "src"
        src_dir.mkdir(parents=True, exist_ok=True)

        # Baseline inference config
        inference_cfg = {
            "model_name": "objdet",
            "version": "v42",
            "dynamic_batching": {
                "enabled": True,
                "max_batch_size": 8,
                "batching_window_ms": 200,
                "timeout_ms": 500
            }
        }

        # Baseline robot params
        robot_params = {
            "robot_name": "warehouse-amr-01",
            "safety": {
                "detection_freshness_budget_ms": 120,
                "control_loop_deadline_ms": 100,
                "transform_timeout_ms": 100,
                "emergency_stop_on_stale_data": True,
                "emergency_stop_on_transform_fail": True
            },
            "perception": {
                "detection_topics": ["object_detections"],
                "required_detection_frequency_hz": 10
            }
        }

        # Detection client code
        detection_client_code = """
class DetectionClient:
    def __init__(self, qos_depth=10, keep_last=True):
        self.qos_depth = qos_depth
        self.keep_last = keep_last
"""
        (src_dir / "detection_client.py").write_text(detection_client_code, encoding='utf-8')

        # Apply hypothesis intervention
        hyp_id = exp.hypothesis_id.lower()
        applied_changes = {}

        if "h1" in hyp_id or "batching" in hyp_id:
            # Reduce batching window from 200ms to 100ms
            inference_cfg["dynamic_batching"]["batching_window_ms"] = 100
            applied_changes["config/inference.yaml"] = "batching_window_ms: 200 -> 100"
            logger.info(f"[{exp.experiment_id}] Applied H1 intervention: batching_window_ms set to 100")

        elif "h2" in hyp_id or "qos" in hyp_id:
            # Reduce QoS depth to 1
            new_client_code = """
class DetectionClient:
    def __init__(self, qos_depth=1, keep_last=True):
        self.qos_depth = 1  # Reduced depth to prevent stale buffer buildup
        self.keep_last = keep_last
"""
            (src_dir / "detection_client.py").write_text(new_client_code, encoding='utf-8')
            applied_changes["src/detection_client.py"] = "qos_depth: 10 -> 1"
            logger.info(f"[{exp.experiment_id}] Applied H2 intervention: QoS depth set to 1")

        elif "h3" in hyp_id or "clock" in hyp_id:
            # Add clock skew tolerance
            robot_params["safety"]["max_clock_skew_tolerance_ms"] = 25
            applied_changes["config/robot_params.yaml"] = "max_clock_skew_tolerance_ms added: 25"
            logger.info(f"[{exp.experiment_id}] Applied H3 intervention: clock skew tolerance added")

        elif "h4" in hyp_id or "gpu" in hyp_id:
            # Reduce max batch size and throttle power limit
            inference_cfg["dynamic_batching"]["max_batch_size"] = 4
            inference_cfg["dynamic_batching"]["power_limit_watts"] = 140
            applied_changes["config/inference.yaml"] = "max_batch_size: 8 -> 4, power_limit: 140W"
            logger.info(f"[{exp.experiment_id}] Applied H4 intervention: max batch size set to 4")

        # Write config files
        with open(config_dir / "inference.yaml", 'w', encoding='utf-8') as f:
            yaml.dump(inference_cfg, f, default_flow_style=False)
        with open(config_dir / "robot_params.yaml", 'w', encoding='utf-8') as f:
            yaml.dump(robot_params, f, default_flow_style=False)

        # Write branch info
        branch_info = {
            "experiment_id": exp.experiment_id,
            "branch_name": exp.branch_name,
            "hypothesis_id": exp.hypothesis_id,
            "intervention": exp.intervention,
            "applied_changes": applied_changes
        }
        with open(exp_dir / "branch_info.json", 'w', encoding='utf-8') as f:
            json.dump(branch_info, f, indent=2)
