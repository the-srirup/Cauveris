"""
Sandbox controller for managing experiment branches and interventions.

An experiment branch is a copy of the *real* incident bundle with one
configuration change applied.  The sandbox never invents a configuration: if
the bundle does not declare a file the change belongs in, the change is
recorded as a deployment-level action instead of being written into a file
that does not exist.
"""

import logging
import shutil
import json
import re
import yaml
from pathlib import Path
from typing import List, Optional
from cauveris.analysis.parameters import (
    SECTIONED_CONFIG_SUFFIXES,
    replace_sectioned_scalar,
)
from cauveris.bundles import (
    bundle_incident_id,
    bundle_manifest_incident_id,
    resolve_bundle,
)
from cauveris.schemas.experiment import Experiment
from cauveris.schemas.hypothesis import Hypothesis
from cauveris.simulation.mapping import map_hypothesis_to_intervention
from cauveris.config import get_settings

logger = logging.getLogger(__name__)

#: Configuration files the sandbox knows how to edit, by the role the key
#: plays in them.  The role is what decides the file, not the file's name.
_CONFIG_SUFFIXES = (".yaml", ".yml", ".json")


class _IncidentShim:
    """
    The incident identity the bundle resolver needs, without an incident.

    The sandbox knows *which* incident it is working on but not the incident
    record itself, and the resolver only asks for the id.
    """

    def __init__(self, id: str):
        self.id = id
        self.bundle_path = None
        self.manifest: dict = {}


class SandboxController:
    """Controls sandbox environments for creating experiment branches and applying interventions."""

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.settings = get_settings()
        self.workspace_dir = Path(workspace_dir or self.settings.sandbox_workspace_path)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    async def plan_experiments(
        self, hypotheses: List[Hypothesis], incident_id: Optional[str] = None
    ) -> List[Experiment]:
        """
        Plan experiments for each hypothesis.

        Args:
            hypotheses: List of hypotheses to test
            incident_id: The incident the hypotheses were derived from

        Returns:
            List of Experiment objects
        """
        logger.info(f"Planning experiments for {len(hypotheses)} hypotheses")
        if not incident_id:
            # The bundle the hypotheses were derived from names the incident
            # more reliably than a search of the working directory does: it
            # is the bundle itself that says which incident it is, in its
            # manifest or in the name it was filed under.
            for hyp in hypotheses:
                declared = getattr(hyp, "bundle_path", None)
                if not declared:
                    continue
                owner = bundle_manifest_incident_id(Path(declared))
                if owner:
                    incident_id = owner
                    break
                stem = Path(declared).name
                if stem.startswith("incident-"):
                    incident_id = stem[len("incident-") :]
                    break
        if not incident_id:
            # Discover incident_id from hypotheses or working directory
            for hyp in hypotheses:
                for art in (hyp.supporting_artifact_ids or []):
                    m = re.search(r"incident-([a-zA-Z0-9_\-]+)", str(art))
                    if m:
                        incident_id = m.group(1)
                        break
                if incident_id:
                    break
            if not incident_id:
                # A bundle in the working directory says which incident it
                # belongs to.  The demo bundle is one of those bundles, not a
                # special one - what matters is what the bundle declares.
                for p in (
                    sorted(Path(".").glob("incident-*"))
                    + sorted(Path(".").glob("golden_incident/incident-*"))
                    + sorted(Path(".").glob("packages/incident-*"))
                    + sorted(Path(".").glob("packages/golden_incident/incident-*"))
                    + sorted(Path(".").glob("packages/*"))
                    + sorted(Path(".").glob("packages/*/*"))
                ):
                    if not p.is_dir():
                        continue
                    owner = bundle_incident_id(p)
                    if owner:
                        incident_id = owner
                        break

        experiments = []
        for hyp in hypotheses:
            exp = Experiment(
                experiment_id=f"exp-{hyp.hypothesis_id}",
                hypothesis_id=hyp.hypothesis_id,
                incident_id=incident_id,
                branch_name=f"experiment/{hyp.hypothesis_id}",
                intervention=hyp.intervention,
                bundle_path=getattr(hyp, "bundle_path", None),
                proposed_changes=[
                    change.as_dict() if hasattr(change, "as_dict") else dict(change)
                    for change in (getattr(hyp, "proposed_changes", None) or [])
                ],
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
        logger.info(
            f"Setting up sandboxes and applying interventions for {len(experiments)} experiments"
        )

        for exp in experiments:
            try:
                exp.status = "RUNNING"
                logger.info(f"Setting up branch sandbox for {exp.experiment_id}")
                await self._setup_experiment_sandbox(exp)
                logger.info(f"Sandbox ready for {exp.experiment_id}")
            except Exception as e:
                logger.error(f"Failed to setup experiment {exp.experiment_id}: {e}")
                exp.status = "FAILED"

    # ------------------------------------------------------------------ setup

    def _bundle_source(self, exp: Experiment) -> Optional[Path]:
        """
        Locate the incident bundle this experiment is based on.

        The bundle the hypothesis was derived from wins: branching from any
        other incident's files would make the experiment - and everything
        downstream of it - about the wrong incident.  When that path is not
        available the bundle is resolved by incident id, and a bundle that
        belongs to a *different* incident is refused rather than used.
        """
        declared = getattr(exp, "bundle_path", None)
        incident_id = str(exp.incident_id or "").strip()

        if declared:
            candidate = Path(declared)
            if candidate.is_dir():
                return candidate
            logger.warning(
                f"[{exp.experiment_id}] The declared bundle {candidate} does not exist; "
                "the branch falls back to a search by incident id."
            )

        shim = _IncidentShim(id=incident_id)
        bundle = resolve_bundle(
            shim,
            evidence_store_path=self.settings.evidence_store_path,
        )
        if bundle is None:
            return None
        logger.info(f"[{exp.experiment_id}] Branching from the incident bundle {bundle}")
        return bundle

    async def _setup_experiment_sandbox(self, exp: Experiment):
        """Prepare the workspace, copy the real bundle, and apply the change."""
        exp_dir = self.workspace_dir / exp.experiment_id
        if exp_dir.exists():
            shutil.rmtree(exp_dir)
        exp_dir.mkdir(parents=True, exist_ok=True)
        # The branch directory travels with the experiment, so that the
        # simulation reads *this* branch rather than whichever branch the
        # same-named experiment left in a shared workspace.
        exp.branch_path = str(exp_dir)

        source = self._bundle_source(exp)
        bundle_dir = exp_dir / "bundle"
        if source is not None:
            shutil.copytree(source, bundle_dir)
            logger.info(f"[{exp.experiment_id}] Copied the incident bundle from {source}")
        else:
            bundle_dir.mkdir(parents=True, exist_ok=True)
            logger.warning(
                f"[{exp.experiment_id}] No incident bundle found; the branch holds only the change"
            )

        plan = map_hypothesis_to_intervention(
            hypothesis_id=exp.hypothesis_id,
            intervention=exp.intervention,
            proposed_changes=exp.proposed_changes,
        )
        applied_changes = dict(plan.applied_changes)

        # Apply every change to the real configuration file it belongs in.
        edited_files: List[str] = []
        for parameter, target in plan.parameter_overrides.items():
            rel = plan.target_files.get(parameter)
            if not rel:
                continue
            key = plan.target_keys.get(parameter)
            if not key:
                continue
            changed = self._apply_to_config(bundle_dir / rel, key, target)
            if changed:
                edited_files.append(rel)

        # Write the branch description next to the bundle.
        branch_info = {
            "experiment_id": exp.experiment_id,
            "branch_name": exp.branch_name,
            "hypothesis_id": exp.hypothesis_id,
            "intervention": exp.intervention,
            "applied_changes": applied_changes,
            "parameter_overrides": plan.parameter_overrides,
            "source_bundle": str(source) if source else None,
            "edited_files": edited_files,
        }
        with open(exp_dir / "branch_info.json", "w", encoding="utf-8") as f:
            json.dump(branch_info, f, indent=2)

    def _apply_to_config(self, path: Path, dotted_key: str, value: float) -> bool:
        """
        Set one key in a configuration file, preserving its structure.

        Returns whether the file was changed.  A file that does not exist, or
        a key that is not in it, is left alone: writing a key into a file that
        does not declare it would hide the fact that the knob is somewhere
        else.
        """
        suffix = path.suffix.lower()
        if not path.exists() or suffix not in _CONFIG_SUFFIXES + SECTIONED_CONFIG_SUFFIXES:
            return False
        if suffix in SECTIONED_CONFIG_SUFFIXES:
            return self._apply_to_sectioned_config(path, dotted_key, value)
        try:
            text = path.read_text(encoding="utf-8")
            if suffix in (".yaml", ".yml"):
                data = yaml.safe_load(text) or {}
            else:
                data = json.loads(text or "{}")
        except Exception as exc:
            logger.warning(f"Could not read {path}: {exc}")
            return False
        if not isinstance(data, dict):
            return False

        parts = [part for part in dotted_key.split(".") if part]
        if not parts:
            return False
        node = data
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                return False
            node = child
        if parts[-1] not in node:
            logger.info(
                f"{path} does not declare {dotted_key}; the change needs another home"
            )
            return False

        old = node[parts[-1]]
        node[parts[-1]] = int(value) if float(value).is_integer() else float(value)
        try:
            if suffix in (".yaml", ".yml"):
                path.write_text(
                    yaml.safe_dump(data, sort_keys=False, default_flow_style=False),
                    encoding="utf-8",
                )
            else:
                path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Could not write {path}: {exc}")
            return False
        logger.info(f"[{path.name}] {dotted_key}: {old} -> {node[parts[-1]]}")
        return True

    def _apply_to_sectioned_config(
        self, path: Path, dotted_key: str, value: float
    ) -> bool:
        """
        Set one key in a TOML or INI configuration file.

        The file is edited in place, in its own format: a robot that ships
        ``robot.toml`` must still have a ``robot.toml`` after the experiment,
        with the one number changed.
        """
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Could not read {path}: {exc}")
            return False
        result = replace_sectioned_scalar(text, dotted_key, value)
        if result is None:
            logger.info(
                f"{path} does not declare {dotted_key}; the change needs another home"
            )
            return False
        patched, previous = result
        try:
            path.write_text(patched, encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Could not write {path}: {exc}")
            return False
        logger.info(f"[{path.name}] {dotted_key}: {previous} -> {value}")
        return True
