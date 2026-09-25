"""
State machine orchestrator for Cauveris incident processing pipeline.
"""
import asyncio
import logging
from enum import Enum, auto
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


class PipelineState(Enum):
    """States of the Cauveris processing pipeline."""
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
    # timeline_events is now stored directly on the Incident object
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
    """Orchestrates the Cauveris incident processing pipeline."""

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
        self._progress_callback: Optional[Callable[[PipelineState, float], None]] = None

    def set_progress_callback(self, callback: Callable[[PipelineState, float], None]):
        """Set a callback to receive progress updates."""
        self._progress_callback = callback

    async def process_incident(self, incident: Incident) -> PipelineContext:
        """
        Process an incident through the full pipeline.

        Args:
            incident: The incident to process

        Returns:
            PipelineContext with results
        """
        context = PipelineContext(incident=incident)
        self._task = asyncio.create_task(self._run_pipeline(context))
        return await self._task

    async def _run_pipeline(self, context: PipelineContext) -> PipelineContext:
        """Run the pipeline stages sequentially."""
        try:
            await self._transition(context, PipelineState.RECEIVED, 0.0)
            context.incident = await self.ingestion.process(context.incident)
            await self._transition(context, PipelineState.VALIDATING, 0.1)

            context.validated_incident = await self.timeline_builder.build(context.incident)
            await self._transition(context, PipelineState.NORMALIZING, 0.2)

            # Temporal causality analysis right after timeline construction
            context.temporal_analysis = self.temporal_analyzer.analyze_incident(context.validated_incident)
            # Attach temporal analysis to incident for report embedding
            context.validated_incident.temporal_analysis = context.temporal_analysis
            await self._transition(context, PipelineState.TEMPORAL_ANALYSIS, 0.25)

            context.hypotheses = await self.hypothesis_generator.generate(context.validated_incident)
            await self._transition(context, PipelineState.HYPOTHESIZING, 0.3)

            context.experiments = await self.sandbox_controller.plan_experiments(context.hypotheses)
            await self._transition(context, PipelineState.PLANNING, 0.4)

            await self.sandbox_controller.run_experiments(context.experiments)
            await self._transition(context, PipelineState.RUNNING_BRANCHES, 0.5)

            context.experiments = await self.simulation_runner.run_simulations(context.experiments)
            await self._transition(context, PipelineState.SCORING, 0.6)

            context.patch_candidates = await self.patch_generator.generate(context.experiments)
            await self._transition(context, PipelineState.PATCH_FORGE, 0.7)

            context.verification_reports = await self.verification_engine.verify(context.patch_candidates)
            await self._transition(context, PipelineState.VERIFYING, 0.8)

            context.final_report = await self.report_generator.generate(
                context.validated_incident,
                context.hypotheses,
                context.experiments,
                context.patch_candidates,
                context.verification_reports
            )
            await self._transition(context, PipelineState.AWAITING_REVIEW, 0.9)

            await self._transition(context, PipelineState.COMPLETED, 1.0)

        except asyncio.CancelledError:
            context.cancelled = True
            await self._transition(context, PipelineState.FAILED, 0.0, "Processing cancelled")
            raise
        except Exception as e:
            logger.exception("Pipeline failed")
            context.error = str(e)
            await self._transition(context, PipelineState.FAILED, 0.0, str(e))
        finally:
            self._task = None

        return context

    async def _transition(self, context: PipelineContext, state: PipelineState, progress: float, message: str = ""):
        """Transition to a new state and report progress."""
        logger.info(f"Transitioning to {state.name}: {message}")
        if self._progress_callback:
            self._progress_callback(state, progress)

    def cancel(self):
        """Cancel the currently running pipeline."""
        if self._task and not self._task.done():
            self._task.cancel()
