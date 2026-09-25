"""
Comprehensive tests for patch export and direct execution/import in the infected space.
"""
import py_compile
import tempfile
import pytest
from pathlib import Path
from httpx import AsyncClient, ASGITransport

from cauveris.patch.generator import PatchGenerator
from cauveris.schemas.experiment import Experiment
from cauveris.api.main import app, incidents, pipeline_contexts
from cauveris.state_machine.orchestrator import PipelineOrchestrator


@pytest.fixture
def sample_h1_experiment():
    return Experiment(
        experiment_id="exp-h1-batching",
        hypothesis_id="h1_batching_window",
        branch_name="branch-exp-h1-batching",
        intervention="Reduce dynamic batching window from 200ms to 100ms",
        trial_count=10,
        reproduction_count=0,
        reproduction_rate=0.0,
        failure_oracle={"hypothesis_supported": True},
        status="COMPLETED",
        conclusion="Hypothesis supported; batching window reduction resolves incident."
    )


@pytest.mark.asyncio
async def test_standalone_installer_compiles(sample_h1_experiment):
    """Verify that generated standalone installer script is syntactically valid Python."""
    gen = PatchGenerator()
    patches = await gen.generate([sample_h1_experiment])
    assert len(patches) > 0
    patch = patches[0]

    installer_code = gen.generate_standalone_installer(patch)
    assert "class" in installer_code or "def apply" in installer_code
    assert "CANDIDATE_ID" in installer_code
    assert "batching_window_ms: 100" in installer_code

    # Verify syntax compilation
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(installer_code)
        temp_path = f.name

    try:
        py_compile.compile(temp_path, doraise=True)
    finally:
        Path(temp_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_direct_import_and_execution_in_infected_space(sample_h1_experiment):
    """
    Verify that an exported patch script can be directly imported or executed
    in an infected space to fix the bug, verify status, and support rollback.
    """
    gen = PatchGenerator()
    patches = await gen.generate([sample_h1_experiment])
    patch = patches[0]

    with tempfile.TemporaryDirectory() as tmp_dir:
        infected_workspace = Path(tmp_dir)

        # 1. Setup infected workspace with bad config
        cfg_dir = infected_workspace / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        infected_config = cfg_dir / "inference.yaml"
        infected_config.write_text(
            "dynamic_batching:\n"
            "  enabled: true\n"
            "  max_batch_size: 8\n"
            "  batching_window_ms: 200\n"
            "  timeout_ms: 500\n",
            encoding="utf-8"
        )

        # 2. Export patch to infected workspace (mimicking direct copy/import)
        exported = gen.export_patch(patch, infected_workspace)
        assert exported["patch_file"].exists()
        assert exported["installer_script"].exists()

        installer_file = exported["installer_script"]

        # 3. Import and execute patch script inside infected space
        scope = {}
        with open(installer_file, "r", encoding="utf-8") as f:
            code = f.read()
        exec(code, scope)

        # 4. Check initial status
        status_fn = scope["status"]
        assert status_fn(target_dir=str(infected_workspace)) == "INFECTED"

        # 5. Check dry-run check()
        check_fn = scope["check"]
        assert check_fn(target_dir=str(infected_workspace)) is True
        # Content must remain unchanged after dry run
        assert "batching_window_ms: 200" in infected_config.read_text(encoding="utf-8")

        # 6. Apply fix directly
        apply_fn = scope["apply"]
        success = apply_fn(target_dir=str(infected_workspace))
        assert success is True

        # Verify patched content
        patched_content = infected_config.read_text(encoding="utf-8")
        assert "batching_window_ms: 100" in patched_content
        assert "batching_window_ms: 200" not in patched_content

        # Verify backup was created
        backup_file = infected_config.with_suffix(".yaml.bak")
        assert backup_file.exists()
        assert "batching_window_ms: 200" in backup_file.read_text(encoding="utf-8")

        # Verify regression test was installed
        test_file = infected_workspace / "tests" / "test_freshness_budget.py"
        assert test_file.exists()
        assert "test_batching_window_within_budget" in test_file.read_text(encoding="utf-8")

        # Verify status is now PATCHED
        assert status_fn(target_dir=str(infected_workspace)) == "PATCHED"

        # 7. Apply again (idempotent)
        assert apply_fn(target_dir=str(infected_workspace)) is True

        # 8. Rollback
        rollback_fn = scope["rollback"]
        assert rollback_fn(target_dir=str(infected_workspace)) is True

        # Verify restored to infected state
        reverted_content = infected_config.read_text(encoding="utf-8")
        assert "batching_window_ms: 200" in reverted_content
        assert status_fn(target_dir=str(infected_workspace)) == "INFECTED"
        assert not test_file.exists()


@pytest.mark.asyncio
async def test_api_export_and_apply_patch_endpoints():
    """Verify GET /export-patch and POST /apply-patch API endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Load incident and run pipeline
        await client.post("/api/v1/incidents?golden=true")
        incident = incidents["CAU-0001"]
        orchestrator = PipelineOrchestrator()
        context = await orchestrator.process_incident(incident)
        pipeline_contexts["CAU-0001"] = context

        # 1. Export installer format
        res_inst = await client.get("/api/v1/incidents/CAU-0001/export-patch?format=installer")
        assert res_inst.status_code == 200
        assert res_inst.headers["content-type"] == "text/x-python; charset=utf-8"
        assert b"apply_patch" in res_inst.content

        # 2. Export patch format
        res_patch = await client.get("/api/v1/incidents/CAU-0001/export-patch?format=patch")
        assert res_patch.status_code == 200
        assert res_patch.headers["content-type"] == "text/x-diff; charset=utf-8"
        assert b"batching_window_ms: 100" in res_patch.content

        # 3. Apply patch via API to an infected workspace
        with tempfile.TemporaryDirectory() as tmp_dir:
            target_ws = Path(tmp_dir)
            cfg_dir = target_ws / "config"
            cfg_dir.mkdir(parents=True, exist_ok=True)
            cfg = cfg_dir / "inference.yaml"
            cfg.write_text(
                "dynamic_batching:\n"
                "  enabled: true\n"
                "  max_batch_size: 8\n"
                "  batching_window_ms: 200\n"
                "  timeout_ms: 500\n",
                encoding="utf-8"
            )

            # POST /apply-patch
            apply_res = await client.post(
                "/api/v1/incidents/CAU-0001/apply-patch",
                json={"target_directory": str(target_ws), "dry_run": False}
            )
            assert apply_res.status_code == 200
            apply_data = apply_res.json()
            assert apply_data["success"] is True
            assert apply_data["status"] == "PATCHED"
            assert "batching_window_ms: 100" in cfg.read_text(encoding="utf-8")

            # POST /apply-patch with rollback
            rb_res = await client.post(
                "/api/v1/incidents/CAU-0001/apply-patch",
                json={"target_directory": str(target_ws), "rollback": True}
            )
            assert rb_res.status_code == 200
            rb_data = rb_res.json()
            assert rb_data["success"] is True
            assert rb_data["status"] == "INFECTED"
            assert "batching_window_ms: 200" in cfg.read_text(encoding="utf-8")
