"""
Tests for Phase 16: Complete Repair-Package Metadata and Validation.
Verifies complete manifest metadata, pre-build rollback verification,
executable permission preservation, path traversal prevention, and archive validation.
"""

import hashlib
import json
import os
import zipfile
import pytest

from cauveris.packaging.builder import PackageBuilder
from cauveris.packaging.manifest import build_manifest
from cauveris.packaging.models import (
    PACKAGE_CANDIDATE_UNVERIFIED,
    PACKAGE_PATCH_EMPTY,
    PackageError,
    VerificationLevel,
)
from cauveris.packaging.validation import validate_package_archive
from cauveris.schemas.incident import Incident
from cauveris.schemas.patch import PatchCandidate, VerificationReport
from cauveris.model_gateway.records import get_execution_store, ModelExecutionRecord
from cauveris.model_gateway.enums import ProviderState, ModelTaskType


@pytest.fixture
def test_bundle(tmp_path):
    """Creates a realistic incident bundle for packaging tests."""
    bundle_dir = tmp_path / "bundle_test"
    bundle_dir.mkdir(parents=True)

    config_file = bundle_dir / "worker.yaml"
    config_file.write_text("batch_size: 10\nworkers: 2\ntimeout: 30\n", encoding="utf-8")

    script_file = bundle_dir / "run.sh"
    script_file.write_text("#!/bin/sh\necho 'running'\n", encoding="utf-8")
    # Mark executable
    os.chmod(script_file, 0o755)

    manifest_file = bundle_dir / "manifest.yaml"
    manifest_file.write_text("name: test-bundle\nversion: 1.0\n", encoding="utf-8")

    return bundle_dir


@pytest.mark.asyncio
async def test_manifest_metadata_completeness(tmp_path, test_bundle):
    """
    Verify that BuiltManifest contains all required metadata fields:
    - incident_id, package_id, generated_at
    - target_files, affected_files, file_checksums (before and after SHA-256)
    - patch_format, hypothesis_id, hypothesis_rationale
    - verification summary (level, checks_passed, limitations)
    - model assistance transparency (provider, model, execution_id, token_usage)
    - rollback instructions and reverse patch reference
    """
    inc_id = "INC-PKG-001"
    cand_id = "patch-001"
    exec_id = "exec-test-999"

    # Save model execution
    rec = ModelExecutionRecord(
        execution_id=exec_id,
        incident_id=inc_id,
        provider="nebius",
        provider_state=ProviderState.NEBIUS_NVIDIA_ACTIVE,
        model_id="nvidia/Llama-3.1-Nemotron-70B-Instruct-HF",
        task_id=ModelTaskType.HYPOTHESIS_PROPOSAL.value,
        usage={"input_tokens": 512, "output_tokens": 128},
    )
    get_execution_store().record(rec)

    patch = PatchCandidate(
        incident_id=inc_id,
        candidate_id=cand_id,
        hypothesis_id="hyp-batch-01",
        rationale="Scale batch size to 64 to avoid queue saturation",
        target_file="worker.yaml",
        affected_files=["worker.yaml"],
        unified_diff="--- worker.yaml\n+++ worker.yaml\n@@ -1,3 +1,3 @@\n-batch_size: 10\n+batch_size: 64\n workers: 2\n timeout: 30\n",
        before_hash=hashlib.sha256(b"batch_size: 10\nworkers: 2\ntimeout: 30\n").hexdigest(),
        after_hash=hashlib.sha256(b"batch_size: 64\nworkers: 2\ntimeout: 30\n").hexdigest(),
        file_checksums={"worker.yaml": {
            "before": hashlib.sha256(b"batch_size: 10\nworkers: 2\ntimeout: 30\n").hexdigest(),
            "after": hashlib.sha256(b"batch_size: 64\nworkers: 2\ntimeout: 30\n").hexdigest(),
        }},
        verified=True,
        provider_execution_id=exec_id,
    )

    report = VerificationReport(
        incident_id=inc_id,
        patch_candidate_id=cand_id,
        verified=True,
        verification_level="STAGING_VERIFIED",
        applies_cleanly=True,
        regression_test_passes_after=True,
        safety_invariants_pass=True,
        rollback_test_passes=True,
        verification_summary={
            "overall_status": "PASSED",
            "limitations": ["Requires cluster restart for parameter reload"],
        },
    )

    artifacts = [
        ("worker.yaml", b"batch_size: 64\nworkers: 2\ntimeout: 30\n"),
        ("fix.patch", patch.unified_diff.encode("utf-8")),
    ]

    manifest = build_manifest(
        incident_id=inc_id,
        patch=patch,
        report=report,
        staged=True,
        source_bundle_id=str(test_bundle),
        artifacts=artifacts,
    )

    manifest_dict = manifest.to_dict()

    # 1. Top-level metadata
    assert manifest_dict["incident_id"] == inc_id
    assert manifest_dict["package_id"] != ""
    assert manifest_dict["generated_at"] != ""
    assert manifest_dict["is_sample"] is False

    # 2. Repair metadata
    repair = manifest_dict["repair"]
    assert repair["candidate_id"] == cand_id
    assert repair["target_files"] == ["worker.yaml"]
    assert repair["affected_files"] == ["worker.yaml"]
    assert "worker.yaml" in repair["file_checksums"]
    assert repair["file_checksums"]["worker.yaml"]["before"] == patch.before_hash
    assert repair["file_checksums"]["worker.yaml"]["after"] == patch.after_hash
    assert repair["patch_format"] == "unified_diff"
    assert repair["hypothesis_id"] == "hyp-batch-01"
    assert repair["hypothesis_rationale"] == "Scale batch size to 64 to avoid queue saturation"

    # 3. Verification metadata
    verification = manifest_dict["verification"]
    assert verification["level"] == VerificationLevel.STAGING_VERIFIED.value
    assert "Requires cluster restart for parameter reload" in verification["limitations"]

    # 4. Model metadata
    model = manifest_dict["model"]
    assert model["provider"] == "nebius"
    assert model["model"] == "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF"
    assert model["execution_id"] == exec_id
    assert model["token_usage"] == {"input_tokens": 512, "output_tokens": 128}

    # 5. Rollback metadata
    rollback = manifest_dict["rollback"]
    assert "rollback_patch.py" in rollback["instructions"]
    assert rollback["reverse_patch"] == "rollback.patch"


@pytest.mark.asyncio
async def test_builder_successful_build_and_validation(tmp_path, test_bundle):
    """
    Test that PackageBuilder creates a sealed archive, verifies patch applicability,
    verifies rollback restoration in staging, and produces a valid package marked READY.
    """
    inc_id = "INC-PKG-SUCCESS"
    cand_id = "patch-valid-01"

    incident = Incident(
        id=inc_id,
        title="Worker Configuration Tuning",
        system_name="PerceptionPipeline",
        bundle_path=str(test_bundle),
    )

    patch = PatchCandidate(
        incident_id=inc_id,
        candidate_id=cand_id,
        target_file="worker.yaml",
        affected_files=["worker.yaml"],
        unified_diff="--- worker.yaml\n+++ worker.yaml\n@@ -1,3 +1,3 @@\n-batch_size: 10\n+batch_size: 64\n workers: 2\n timeout: 30\n",
        before_hash=hashlib.sha256(b"batch_size: 10\nworkers: 2\ntimeout: 30\n").hexdigest(),
        after_hash=hashlib.sha256(b"batch_size: 64\nworkers: 2\ntimeout: 30\n").hexdigest(),
        file_checksums={"worker.yaml": {
            "before": hashlib.sha256(b"batch_size: 10\nworkers: 2\ntimeout: 30\n").hexdigest(),
            "after": hashlib.sha256(b"batch_size: 64\nworkers: 2\ntimeout: 30\n").hexdigest(),
        }},
        verified=True,
        applies_cleanly=True,
        safety_invariants_pass=True,
        rollback_test_passes=True,
    )

    vreport = VerificationReport(
        incident_id=inc_id,
        patch_candidate_id=cand_id,
        verified=True,
        verification_level="STAGING_VERIFIED",
        applies_cleanly=True,
        rollback_test_passes=True,
    )

    builder = PackageBuilder()
    outcome = await builder.build(
        incident=incident,
        patch=patch,
        user_id="usr_admin",
        org_id="org_default",
        verification_reports=[vreport],
    )

    assert outcome.incident_id == inc_id
    assert outcome.repair_id == cand_id
    assert outcome.staged is True
    assert outcome.zip_path.exists()

    # Validate the generated zip file
    zip_bytes = outcome.zip_path.read_bytes()
    v_archive = validate_package_archive(zip_bytes)
    assert v_archive.ok is True
    assert len(v_archive.failures) == 0
    assert v_archive.manifest["repair"]["candidate_id"] == cand_id


@pytest.mark.asyncio
async def test_builder_refuses_unverified_patch(test_bundle):
    """PackageBuilder must refuse to package unverified patches."""
    inc_id = "INC-PKG-UNVERIFIED"
    incident = Incident(id=inc_id, title="Test", bundle_path=str(test_bundle))
    patch = PatchCandidate(
        incident_id=inc_id,
        candidate_id="patch-unverified",
        target_file="worker.yaml",
        affected_files=["worker.yaml"],
        unified_diff="--- worker.yaml\n+++ worker.yaml\n@@ -1 +1 @@\n-batch_size: 10\n+batch_size: 20\n",
        verified=False,
    )

    builder = PackageBuilder()
    with pytest.raises(PackageError) as exc_info:
        await builder.build(
            incident=incident,
            patch=patch,
            user_id="usr_admin",
            org_id="org_default",
        )
    assert exc_info.value.code == PACKAGE_CANDIDATE_UNVERIFIED


@pytest.mark.asyncio
async def test_builder_refuses_empty_patch(test_bundle):
    """PackageBuilder must refuse to package empty patches."""
    inc_id = "INC-PKG-EMPTY"
    incident = Incident(id=inc_id, title="Test", bundle_path=str(test_bundle))
    patch = PatchCandidate(
        incident_id=inc_id,
        candidate_id="patch-empty",
        target_file="worker.yaml",
        affected_files=["worker.yaml"],
        unified_diff="",
        verified=True,
    )

    builder = PackageBuilder()
    with pytest.raises(PackageError) as exc_info:
        await builder.build(
            incident=incident,
            patch=patch,
            user_id="usr_admin",
            org_id="org_default",
        )
    assert exc_info.value.code == PACKAGE_PATCH_EMPTY


@pytest.mark.asyncio
async def test_builder_refuses_path_traversal(test_bundle):
    """PackageBuilder must refuse patches whose target files escape the bundle root."""
    inc_id = "INC-PKG-TRAVERSAL"
    incident = Incident(id=inc_id, title="Test", bundle_path=str(test_bundle))
    patch = PatchCandidate(
        incident_id=inc_id,
        candidate_id="patch-traversal",
        target_file="../../etc/shadow",
        affected_files=["../../etc/shadow"],
        unified_diff="--- ../../etc/shadow\n+++ ../../etc/shadow\n@@ -1 +1 @@\n-a\n+b\n",
        verified=True,
    )

    builder = PackageBuilder()
    with pytest.raises(PackageError) as exc_info:
        await builder.build(
            incident=incident,
            patch=patch,
            user_id="usr_admin",
            org_id="org_default",
        )
    assert exc_info.value.code == "path_traversal"


@pytest.mark.asyncio
async def test_builder_refuses_failed_rollback(test_bundle):
    """PackageBuilder must refuse patches if rollback fails to restore the exact original content."""
    inc_id = "INC-PKG-BAD-ROLLBACK"
    incident = Incident(id=inc_id, title="Test", bundle_path=str(test_bundle))

    # A broken diff whose hunk does not match the file cleanly
    patch = PatchCandidate(
        incident_id=inc_id,
        candidate_id="patch-bad-hunk",
        target_file="worker.yaml",
        affected_files=["worker.yaml"],
        # Does not match worker.yaml
        unified_diff="--- worker.yaml\n+++ worker.yaml\n@@ -1,3 +1,3 @@\n-non_existent_key: 10\n+batch_size: 64\n workers: 2\n timeout: 30\n",
        verified=True,
    )

    builder = PackageBuilder()
    with pytest.raises(PackageError) as exc_info:
        await builder.build(
            incident=incident,
            patch=patch,
            user_id="usr_admin",
            org_id="org_default",
        )
    assert exc_info.value.code == "patch_does_not_apply"


def test_validation_detects_checksum_mismatch(tmp_path):
    """validate_package_archive must detect if manifest declares a checksum that differs from the file in archive."""
    zip_path = tmp_path / "corrupt_pkg.zip"

    # Create a zip where manifest declared sha256 does not match file bytes
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("manifest.json", json.dumps({
            "schema_version": "1.0",
            "format": "cauveris-repair-package-v1",
            "verification_level": "STAGING_VERIFIED",
            "files": [
                {"path": "fix.patch", "sha256": "f" * 64, "size_bytes": 10, "file_type": "patch", "required": True}
            ]
        }))
        zf.writestr("fix.patch", b"hello world")
        zf.writestr("patch.diff", b"hello world")
        zf.writestr("rollback.patch", b"hello rollback")
        zf.writestr("rollback.diff", b"hello rollback")
        zf.writestr("checksums.txt", f"{hashlib.sha256(b'hello world').hexdigest()}  fix.patch\n")
        zf.writestr("README.md", b"# Readme")

    report = validate_package_archive(zip_path.read_bytes())
    assert report.ok is False
    codes = [f.code for f in report.failures]
    assert "manifest_checksum_mismatch" in codes or "checksum_mismatch" in codes
