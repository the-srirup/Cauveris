"""
State machine orchestrator for Cauveris incident processing pipeline.
"""
import asyncio
import logging
import time
import inspect
from enum import Enum, auto
from datetime import datetime, timezone
from typing import Optional, Callable, Any, Dict, List
from dataclasses import dataclass, field
from cauveris.config import get_settings
from cauveris.schemas.incident import Incident
from cauveris.model_gateway.base import ModelGateway
from cauveris.ingestion.controller import IngestionController
from cauveris.timeline.builder import TimelineBuilder
from cauveris.hypothesis.generator import HypothesisGenerator
from cauveris.sandbox.controller import SandboxController
from cauveris.simulation.runner import SimulationRunner
from cauveris.patch.generator import PatchGenerator
from cauveris.verifier.engine import VerificationEngine
from cauveris.report.generator import ReportGenerator
from cauveris.temporal.integration import TemporalAnalyzer

logger = logging.getLogger(__name__)


class StageStatus(str, Enum):
    """Execution status for an individual pipeline stage."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


@dataclass
class PipelineStage:
    """Represents a discrete stage in the investigation pipeline."""
    id: str
    name: str
    description: str
    required: bool = True
    depends_on: List[str] = field(default_factory=list)
    status: StageStatus = StageStatus.PENDING
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[float] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "required": self.required,
            "depends_on": self.depends_on,
            "status": self.status.value if isinstance(self.status, StageStatus) else str(self.status),
            "error": self.error,
            "details": self.details,
            "duration_ms": self.duration_ms,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


def create_default_stages() -> List[PipelineStage]:
    """Create the standard 9-stage sequence with strict dependency graph."""
    return [
        PipelineStage(
            id="ingestion_validation",
            name="Evidence Ingestion & Validation",
            description="Extract artifacts, verify SHA256 checksums, validate schema, and scan for secrets",
            required=True,
            depends_on=[],
        ),
        PipelineStage(
            id="timeline_construction",
            name="Timeline Normalization & Clock Alignment",
            description="Align multi-lane logs, OTel traces, and MCAP recording into synchronized timeline",
            required=True,
            depends_on=["ingestion_validation"],
        ),
        PipelineStage(
            id="temporal_analysis",
            name="Temporal Causality Analysis",
            description="Detect clock drift, causality inversions, and perception freshness budget overruns",
            required=True,
            depends_on=["timeline_construction"],
        ),
        PipelineStage(
            id="hypothesis_generation",
            name="Root-Cause Hypothesis Generation",
            description="Formulate falsifiable root-cause hypotheses with interventions and causal claims",
            required=True,
            depends_on=["temporal_analysis"],
        ),
        PipelineStage(
            id="sandbox_planning",
            name="Sandbox Experiment Planning",
            description="Branch isolated workspaces and plan counterfactual fault-injection experiments",
            required=True,
            depends_on=["hypothesis_generation"],
        ),
        PipelineStage(
            id="simulation_execution",
            name="Digital Twin Simulation & Scoring",
            description="Execute deterministic closed-loop simulations to score failure reproduction rates",
            required=True,
            depends_on=["sandbox_planning"],
        ),
        PipelineStage(
            id="patch_forge",
            name="Patch Candidate Synthesis",
            description="Synthesize configuration and source code patches that eliminate the failure",
            required=True,
            depends_on=["simulation_execution"],
        ),
        PipelineStage(
            id="invariant_verification",
            name="9-Point Invariant Verification",
            description="Formally verify zero regressions, deadline adherence, and deterministic replay",
            required=True,
            depends_on=["patch_forge"],
        ),
        PipelineStage(
            id="report_generation",
            name="Audit Report & Provenance Generation",
            description="Generate cryptographic provenance audit report and exportable installer package",
            required=False,
            depends_on=["invariant_verification"],
        ),
    ]


class PipelineState(Enum):
    """Legacy state enum preserved for backward compatibility."""
    RECEIVED = auto()          # Incident bundle received
    VALIDATING = auto()        # Validating evidence
    NORMALIZING = auto()       # Normalizing timestamps and evidence
    MAPPING = auto()           # Mapping evidence to source and runtime
    TEMPORAL_ANALYSIS = auto() # Analyzing temporal causality
    HYPOTHESIZING = auto()     # Generating root-cause hypotheses
    PLANNING = auto()          # Planning experiments
    RUNNING_BRANCHES = auto()  # Running experiment branches in sandboxes
    SCORING = auto()           # Scoring experiments and ranking hypotheses
    PATCH_FORGE = auto()       # Generating and verifying patch candidates
    VERIFYING = auto()         # Running verification checks on patches
    AWAITING_REVIEW = auto()   # Ready for human review
    COMPLETED = auto()         # Processing complete
    FAILED = auto()            # Processing failed


@dataclass
class PipelineContext:
    """Context passed between pipeline stages."""
    incident: Optional[Incident] = None
    settings: Any = field(default_factory=get_settings)
    model_gateway: Optional[ModelGateway] = None
    # Outputs from each stage
    validated_incident: Optional[Incident] = None
    timeline_events: Optional[List[Dict[str, Any]]] = None
    temporal_analysis: Optional[Dict[str, Any]] = None
    hypotheses: Optional[list] = None
    experiments: Optional[list] = None
    patch_candidates: Optional[list] = None
    verification_reports: Optional[list] = None
    final_report: Optional[Any] = None
    # Control flags
    cancelled: bool = False
    error: Optional[str] = None


class PipelineOrchestrator:
    """Orchestrates the Cauveris incident processing pipeline with stage dependencies."""

    def __init__(self):
        self.settings = get_settings()
        self.ingestion = IngestionController()
        self.timeline_builder = TimelineBuilder()
        self.temporal_analyzer = TemporalAnalyzer()
        self.hypothesis_generator = HypothesisGenerator()
        self.sandbox_controller = SandboxController()
        self.simulation_runner = SimulationRunner()
        self.patch_generator = PatchGenerator()
        self.verification_engine = VerificationEngine()
        self.report_generator = ReportGenerator()
        self._task: Optional[asyncio.Task] = None
        self._progress_callback: Optional[Callable[..., None]] = None
        self.stages: List[PipelineStage] = create_default_stages()
        self.current_state: str = "IDLE"
        self.current_progress: float = 0.0
        self.active_stage_id: Optional[str] = None
        self.error: Optional[str] = None
        self.context: Optional[PipelineContext] = None
        self._cancelled: bool = False
        self.started_at: Optional[str] = None
        self.completed_at: Optional[str] = None
        self._bg_task: Optional[asyncio.Task] = None
        # Test hooks
        self.simulate_failure_stage: Optional[str] = None
        self.simulate_degraded_stage: Optional[str] = None

    def is_running(self) -> bool:
        """Check if pipeline execution is currently active."""
        if self._cancelled:
            return False
        if self._bg_task is not None and not self._bg_task.done():
            return True
        return self._task is not None and not self._task.done()

    def set_progress_callback(self, callback: Callable[..., None]):
        """Set a callback to receive progress updates."""
        self._progress_callback = callback

    def get_stage(self, stage_id: str) -> Optional[PipelineStage]:
        """Find a stage by its ID."""
        for s in self.stages:
            if s.id == stage_id:
                return s
        return None

    def _block_dependent_stages(self, failed_stage_id: str):
        """
        Mark all stages that depend directly or transitively on a failed required stage as SKIPPED.
        """
        blocked_ids = set()
        queue = [failed_stage_id]
        while queue:
            curr = queue.pop(0)
            for stage in self.stages:
                if curr in stage.depends_on and stage.id not in blocked_ids:
                    blocked_ids.add(stage.id)
                    queue.append(stage.id)

        for stage in self.stages:
            if stage.id in blocked_ids and stage.status == StageStatus.PENDING:
                stage.status = StageStatus.SKIPPED
                stage.error = f"Blocked by failed prerequisite stage '{failed_stage_id}'"
                logger.warning(f"Stage '{stage.id}' blocked: {stage.error}")

    def get_pipeline_summary(self) -> Dict[str, Any]:
        """Get full structured pipeline execution summary."""
        is_demo = False
        if self.context and self.context.incident:
            is_demo = getattr(self.context.incident, "is_demonstration", False)

        return {
            "state": self.current_state,
            "progress": self.current_progress,
            "active_stage_id": self.active_stage_id,
            "stages": [s.to_dict() for s in self.stages],
            "error": self.error,
            "is_demonstration": is_demo,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _notify_progress(self, legacy_state: Optional[PipelineState] = None):
        """Notify the registered progress callback."""
        if not self._progress_callback:
            return

        summary = self.get_pipeline_summary()
        try:
            sig = inspect.signature(self._progress_callback)
            params = list(sig.parameters.values())
            if len(params) == 1:
                self._progress_callback(summary)
            elif len(params) >= 2:
                state_val = legacy_state if legacy_state is not None else PipelineState.COMPLETED
                self._progress_callback(state_val, self.current_progress)
            else:
                self._progress_callback(summary)
        except Exception:
            try:
                self._progress_callback(summary)
            except Exception:
                try:
                    self._progress_callback(legacy_state, self.current_progress)
                except Exception as e:
                    logger.debug(f"Progress callback notification failed: {e}")

    async def _execute_stage(
        self,
        stage: PipelineStage,
        action_coro: Callable,
        legacy_state: PipelineState
    ) -> bool:
        """
        Execute a single stage with dependency checking and status updates.
        Returns True if stage succeeded (SUCCESS or DEGRADED), False if failed/skipped.
        """
        if self._cancelled:
            stage.status = StageStatus.CANCELLED
            stage.error = "Operation cancelled"
            return False

        # Verify all prerequisite stages are met
        for dep_id in stage.depends_on:
            dep_stage = self.get_stage(dep_id)
            if dep_stage and dep_stage.status in [StageStatus.FAILED, StageStatus.SKIPPED, StageStatus.CANCELLED]:
                stage.status = StageStatus.SKIPPED
                stage.error = f"Blocked by prerequisite stage '{dep_stage.name}' ({dep_stage.status.value})"
                logger.warning(f"Stage '{stage.id}' skipped: {stage.error}")
                self._block_dependent_stages(stage.id)
                self._notify_progress(legacy_state)
                return False

        self.active_stage_id = stage.id
        stage.status = StageStatus.RUNNING
        stage.started_at = datetime.now(timezone.utc).isoformat()
        t_start = time.perf_counter()

        idx = [s.id for s in self.stages].index(stage.id)
        self.current_progress = round(idx / len(self.stages), 2)
        self._notify_progress(legacy_state)

        try:
            if self.simulate_failure_stage == stage.id:
                raise RuntimeError(f"Simulated execution failure in stage '{stage.id}'")

            await action_coro()

            t_end = time.perf_counter()
            stage.duration_ms = round((t_end - t_start) * 1000, 2)
            stage.completed_at = datetime.now(timezone.utc).isoformat()

            if self.simulate_degraded_stage == stage.id:
                stage.status = StageStatus.DEGRADED
                stage.details["warning"] = "Simulated non-critical degraded execution"
            else:
                stage.status = StageStatus.SUCCESS

            self.current_progress = round((idx + 1) / len(self.stages), 2)
            self._notify_progress(legacy_state)
            return True

        except asyncio.CancelledError:
            t_end = time.perf_counter()
            stage.duration_ms = round((t_end - t_start) * 1000, 2)
            stage.completed_at = datetime.now(timezone.utc).isoformat()
            stage.status = StageStatus.CANCELLED
            stage.error = "Stage cancelled by operator"
            self._block_dependent_stages(stage.id)
            self._notify_progress(legacy_state)
            raise

        except Exception as e:
            t_end = time.perf_counter()
            stage.duration_ms = round((t_end - t_start) * 1000, 2)
            stage.completed_at = datetime.now(timezone.utc).isoformat()
            logger.exception(f"Stage '{stage.id}' failed: {e}")

            if stage.required:
                stage.status = StageStatus.FAILED
                stage.error = str(e)
                self._block_dependent_stages(stage.id)
                self._notify_progress(legacy_state)
                return False
            else:
                stage.status = StageStatus.DEGRADED
                stage.error = str(e)
                stage.details["warning"] = f"Non-critical stage degradation: {e}"
                self._notify_progress(legacy_state)
                return True

    async def process_incident(self, incident: Incident) -> PipelineContext:
        """
        Process an incident through the full pipeline.
        """
        self.context = PipelineContext(incident=incident)
        self._cancelled = False
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.completed_at = None
        self.current_state = "RUNNING"
        self._task = asyncio.create_task(self._run_pipeline(self.context))
        return await self._task

    async def _run_pipeline(self, context: PipelineContext) -> PipelineContext:
        """Run the pipeline stages sequentially respecting dependencies."""
        stage_map = {s.id: s for s in self.stages}

        try:
            self._notify_progress(PipelineState.RECEIVED)

            # 1. Ingestion & Validation
            async def do_ingestion():
                context.incident = await self.ingestion.process(context.incident)
                stage_map["ingestion_validation"].details["evidence_count"] = context.incident.evidence_count

            ok = await self._execute_stage(
                stage_map["ingestion_validation"], do_ingestion, PipelineState.VALIDATING
            )
            if not ok:
                self.current_state = "FAILED"
                self.error = stage_map["ingestion_validation"].error
                self.completed_at = datetime.now(timezone.utc).isoformat()
                self._notify_progress(PipelineState.FAILED)
                return context

            # 2. Timeline Construction
            async def do_timeline():
                context.validated_incident = await self.timeline_builder.build(context.incident)
                context.timeline_events = getattr(context.validated_incident, "timeline_events", [])
                stage_map["timeline_construction"].details["event_count"] = len(context.timeline_events)

            ok = await self._execute_stage(
                stage_map["timeline_construction"], do_timeline, PipelineState.NORMALIZING
            )
            if not ok:
                self.current_state = "FAILED"
                self.error = stage_map["timeline_construction"].error
                self.completed_at = datetime.now(timezone.utc).isoformat()
                self._notify_progress(PipelineState.FAILED)
                return context

            # 3. Temporal Causality Analysis
            async def do_temporal():
                context.temporal_analysis = self.temporal_analyzer.analyze_incident(context.validated_incident)
                context.validated_incident.temporal_analysis = context.temporal_analysis
                stage_map["temporal_analysis"].details["violations"] = len(context.temporal_analysis.get("causality_violations", []))

            ok = await self._execute_stage(
                stage_map["temporal_analysis"], do_temporal, PipelineState.TEMPORAL_ANALYSIS
            )
            if not ok:
                self.current_state = "FAILED"
                self.error = stage_map["temporal_analysis"].error
                self.completed_at = datetime.now(timezone.utc).isoformat()
                self._notify_progress(PipelineState.FAILED)
                return context

            # 4. Hypothesis Generation
            async def do_hypotheses():
                context.hypotheses = await self.hypothesis_generator.generate(context.validated_incident)
                stage_map["hypothesis_generation"].details["count"] = len(context.hypotheses or [])

            ok = await self._execute_stage(
                stage_map["hypothesis_generation"], do_hypotheses, PipelineState.HYPOTHESIZING
            )
            if not ok:
                self.current_state = "FAILED"
                self.error = stage_map["hypothesis_generation"].error
                self.completed_at = datetime.now(timezone.utc).isoformat()
                self._notify_progress(PipelineState.FAILED)
                return context

            # 5. Sandbox Experiment Planning
            async def do_sandbox():
                context.experiments = await self.sandbox_controller.plan_experiments(context.hypotheses)
                await self.sandbox_controller.run_experiments(context.experiments)
                stage_map["sandbox_planning"].details["experiments"] = len(context.experiments or [])

            ok = await self._execute_stage(
                stage_map["sandbox_planning"], do_sandbox, PipelineState.PLANNING
            )
            if not ok:
                self.current_state = "FAILED"
                self.error = stage_map["sandbox_planning"].error
                self.completed_at = datetime.now(timezone.utc).isoformat()
                self._notify_progress(PipelineState.FAILED)
                return context

            # 6. Digital Twin Simulation & Scoring
            async def do_simulation():
                context.experiments = await self.simulation_runner.run_simulations(context.experiments)
                stage_map["simulation_execution"].details["simulated_experiments"] = len(context.experiments or [])

            ok = await self._execute_stage(
                stage_map["simulation_execution"], do_simulation, PipelineState.SCORING
            )
            if not ok:
                self.current_state = "FAILED"
                self.error = stage_map["simulation_execution"].error
                self.completed_at = datetime.now(timezone.utc).isoformat()
                self._notify_progress(PipelineState.FAILED)
                return context

            # 7. Patch Forge
            async def do_patch_forge():
                context.patch_candidates = await self.patch_generator.generate(context.experiments)
                stage_map["patch_forge"].details["patches"] = len(context.patch_candidates or [])

            ok = await self._execute_stage(
                stage_map["patch_forge"], do_patch_forge, PipelineState.PATCH_FORGE
            )
            if not ok:
                self.current_state = "FAILED"
                self.error = stage_map["patch_forge"].error
                self.completed_at = datetime.now(timezone.utc).isoformat()
                self._notify_progress(PipelineState.FAILED)
                return context

            # 8. 9-Point Invariant Verification
            async def do_verification():
                context.verification_reports = await self.verification_engine.verify(context.patch_candidates)
                stage_map["invariant_verification"].details["verified_count"] = sum(
                    1 for r in (context.verification_reports or []) if getattr(r, "verified", False)
                )

            ok = await self._execute_stage(
                stage_map["invariant_verification"], do_verification, PipelineState.VERIFYING
            )
            if not ok:
                self.current_state = "FAILED"
                self.error = stage_map["invariant_verification"].error
                self.completed_at = datetime.now(timezone.utc).isoformat()
                self._notify_progress(PipelineState.FAILED)
                return context

            # 9. Audit Report Generation (Non-required)
            async def do_report():
                context.final_report = await self.report_generator.generate(
                    context.validated_incident,
                    context.hypotheses,
                    context.experiments,
                    context.patch_candidates,
                    context.verification_reports
                )

            await self._execute_stage(
                stage_map["report_generation"], do_report, PipelineState.AWAITING_REVIEW
            )

            # Determine final terminal state
            has_failed = any(s.status == StageStatus.FAILED for s in self.stages)
            has_degraded = any(s.status == StageStatus.DEGRADED for s in self.stages)

            if self._cancelled:
                self.current_state = "CANCELLED"
            elif has_failed:
                self.current_state = "FAILED"
            elif has_degraded:
                self.current_state = "DEGRADED"
                self.current_progress = 1.0
            else:
                self.current_state = "SUCCESS"
                self.current_progress = 1.0

            self.active_stage_id = None
            self.completed_at = datetime.now(timezone.utc).isoformat()
            self._notify_progress(PipelineState.COMPLETED)

        except asyncio.CancelledError:
            self._cancelled = True
            context.cancelled = True
            self.current_state = "CANCELLED"
            self.error = "Investigation cancelled by operator"
            for s in self.stages:
                if s.status == StageStatus.RUNNING:
                    s.status = StageStatus.CANCELLED
                    s.error = "Investigation cancelled by operator"
                elif s.status == StageStatus.PENDING:
                    s.status = StageStatus.SKIPPED
            self.active_stage_id = None
            self.completed_at = datetime.now(timezone.utc).isoformat()
            self._notify_progress(PipelineState.FAILED)
            raise
        except Exception as e:
            logger.exception(f"Pipeline failed: {e}")
            self.current_state = "FAILED"
            self.error = str(e)
            context.error = str(e)
            self.active_stage_id = None
            self.completed_at = datetime.now(timezone.utc).isoformat()
            self._notify_progress(PipelineState.FAILED)
        finally:
            self._task = None

        return context

    def cancel(self):
        """Cancel the currently running pipeline."""
        self._cancelled = True
        if self._task and not self._task.done():
            self._task.cancel()
        for s in self.stages:
            if s.status == StageStatus.RUNNING:
                s.status = StageStatus.CANCELLED
                s.error = "Investigation cancelled by operator"
            elif s.status == StageStatus.PENDING:
                s.status = StageStatus.SKIPPED
        self.current_state = "CANCELLED"
        self.error = "Investigation cancelled by operator"
        self.active_stage_id = None
        self.completed_at = datetime.now(timezone.utc).isoformat()
        self._notify_progress(PipelineState.FAILED)

    def reset(self):
        """Reset the orchestrator back to initial ready state."""
        self._cancelled = False
        self.stages = create_default_stages()
        self.current_state = "IDLE"
        self.current_progress = 0.0
        self.active_stage_id = None
        self.error = None
        self.context = None
        self.started_at = None
        self.completed_at = None
