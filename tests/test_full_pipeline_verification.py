"""
End-to-end integration test verifying all 8 core components of Cauveris.
"""
import pytest
from pathlib import Path
from cauveris.datasets.golden_incident import GoldenIncidentGenerator
from cauveris.ingestion.controller import IngestionController
from cauveris.timeline.builder import TimelineBuilder
from cauveris.hypothesis.generator import HypothesisGenerator
from cauveris.sandbox.controller import SandboxController
from cauveris.simulation.runner import SimulationRunner
from cauveris.patch.generator import PatchGenerator
from cauveris.verifier.engine import VerificationEngine
from cauveris.state_machine.orchestrator import PipelineOrchestrator, PipelineState


@pytest.mark.asyncio
async def test_golden_incident_generator():
    """Verify Component 1: Golden Incident Generator creates valid evidence and incident."""
    generator = GoldenIncidentGenerator()
    incident = generator.generate()

    assert incident.id == "CAU-0001"
    assert incident.evidence_count >= 14
    assert len(incident.missing_required_evidence) == 0

    bundle_dir = Path("./incident-CAU-0001")
    assert (bundle_dir / "manifest.yaml").exists()
    assert (bundle_dir / "config" / "inference.yaml").exists()
    assert (bundle_dir / "traces" / "otel.json").exists()
    assert (bundle_dir / "logs" / "cloud-service.jsonl").exists()
    assert (bundle_dir / "metrics" / "gpu.csv").exists()


@pytest.mark.asyncio
async def test_ingestion_controller():
    """Verify Component 2: Ingestion Controller processes and validates bundle evidence."""
    generator = GoldenIncidentGenerator()
    incident = generator.generate()

    ingestion = IngestionController()
    validated_incident = await ingestion.process(incident)

    assert validated_incident.evidence_count >= 14
    for ev in validated_incident.evidence_items:
        if ev.is_required:
            assert ev.status == "OBSERVED"
            assert ev.size_bytes > 0
            assert len(ev.checksum_sha256) == 64


@pytest.mark.asyncio
async def test_timeline_builder():
    """Verify Component 3: Timeline Builder creates synchronized and normalized timeline."""
    generator = GoldenIncidentGenerator()
    incident = generator.generate()
    incident = await IngestionController().process(incident)

    tb = TimelineBuilder()
    incident = await tb.build(incident)

    assert hasattr(incident, "timeline_events")
    assert len(incident.timeline_events) > 0

    # Ensure chronological order
    timestamps = [e.get("timestamp_ns", 0) for e in incident.timeline_events]
    assert timestamps == sorted(timestamps)

    # Ensure relative timestamps are present
    assert "relative_timestamp_s" in incident.timeline_events[0]
    assert incident.timeline_events[0]["relative_timestamp_s"] == 0.0


@pytest.mark.asyncio
async def test_hypothesis_generator():
    """Verify Component 4: Hypothesis Generator creates falsifiable root-cause hypotheses."""
    generator = GoldenIncidentGenerator()
    incident = generator.generate()
    incident = await IngestionController().process(incident)
    incident = await TimelineBuilder().build(incident)

    hg = HypothesisGenerator()
    hypotheses = await hg.generate(incident)

    assert len(hypotheses) >= 4
    hyp_ids = [h.hypothesis_id for h in hypotheses]
    assert "h1_batching_window" in hyp_ids
    h1 = next(h for h in hypotheses if h.hypothesis_id == "h1_batching_window")
    assert h1.confidence_prior > 0.8
    assert "batching" in h1.intervention.lower()


@pytest.mark.asyncio
async def test_sandbox_and_simulation():
    """Verify Components 5 & 6: Sandbox Controller and Pure Python Digital Twin."""
    generator = GoldenIncidentGenerator()
    incident = generator.generate()
    incident = await IngestionController().process(incident)
    incident = await TimelineBuilder().build(incident)
    hypotheses = await HypothesisGenerator().generate(incident)

    sandbox = SandboxController()
    experiments = await sandbox.plan_experiments(hypotheses)
    assert len(experiments) == len(hypotheses)

    await sandbox.run_experiments(experiments)

    sim_runner = SimulationRunner()
    sim_experiments = await sim_runner.run_simulations(experiments)

    h1_exp = next(e for e in sim_experiments if "h1" in e.hypothesis_id)
    assert h1_exp.status in ["COMPLETED", "SIMULATED"]
    assert h1_exp.reproduction_rate == 0.0  # 0 emergency stops when batching window is reduced
    assert h1_exp.failure_oracle.get("hypothesis_supported") is True


@pytest.mark.asyncio
async def test_patch_generator_and_verification_engine():
    """Verify Components 7 & 8: Patch Generator and 9-point Verification Engine."""
    generator = GoldenIncidentGenerator()
    incident = generator.generate()
    incident = await IngestionController().process(incident)
    incident = await TimelineBuilder().build(incident)
    hypotheses = await HypothesisGenerator().generate(incident)

    sandbox = SandboxController()
    experiments = await sandbox.plan_experiments(hypotheses)
    await sandbox.run_experiments(experiments)
    sim_experiments = await SimulationRunner().run_simulations(experiments)

    patch_gen = PatchGenerator()
    patches = await patch_gen.generate(sim_experiments)
    assert len(patches) > 0

    h1_patch = next(p for p in patches if "h1" in p.candidate_id)
    assert h1_patch.lines_changed == 1
    assert "batching_window_ms: 100" in h1_patch.unified_diff
    assert h1_patch.score > 0.9

    verifier = VerificationEngine()
    reports = await verifier.verify(patches)
    assert len(reports) == len(patches)

    h1_report = next(r for r in reports if "h1" in r.patch_candidate_id)
    assert h1_report.verified is True
    assert h1_report.details.get("checks_passed") == 9
    assert h1_patch.verified is True


@pytest.mark.asyncio
async def test_end_to_end_pipeline_orchestrator():
    """Verify the entire end-to-end 11-stage pipeline orchestrator produces verified patch."""
    generator = GoldenIncidentGenerator()
    incident = generator.generate()

    visited_states = []

    def on_progress(state: PipelineState, progress: float):
        visited_states.append(state)

    orchestrator = PipelineOrchestrator()
    orchestrator.set_progress_callback(on_progress)

    context = await orchestrator.process_incident(incident)

    assert context.error is None
    assert context.cancelled is False
    assert PipelineState.COMPLETED in visited_states

    # Verify outputs
    assert len(context.hypotheses) >= 4
    assert len(context.experiments) >= 4
    assert len(context.patch_candidates) >= 1
    assert any(p.verified for p in context.patch_candidates)

    # Verify report and patch package
    assert context.final_report is not None
    assert "patch_package_path" in context.final_report
    patch_pkg_dir = Path(context.final_report["patch_package_path"])
    assert (patch_pkg_dir / "fix.patch").exists()
    assert (patch_pkg_dir / "verification.json").exists()
    assert (patch_pkg_dir / "PULL_REQUEST.md").exists()
    assert (patch_pkg_dir / "reviewer-checklist.md").exists()
    assert (patch_pkg_dir / "rollback.sh").exists()
