from cauveris.invariants import (
    InvariantAuthority,
    InvariantRegistry,
    InvariantSetStatus,
    InvariantStatus,
    normalize_value,
    are_units_compatible,
)


def test_unit_normalization_and_compatibility():
    # 0.12 seconds should normalize to 120.0 ms
    val, unit = normalize_value(0.12, "s")
    assert val == 120.0
    assert unit == "ms"

    # 2048 KB should normalize to 2.048 MB
    val_mb, unit_mb = normalize_value(2048, "KB")
    assert val_mb == 2.048
    assert unit_mb == "MB"

    # Compatibility
    assert are_units_compatible("ms", "s") is True
    assert are_units_compatible("ms", "seconds") is True
    assert are_units_compatible("MB", "KB") is True
    assert are_units_compatible("ms", "MB") is False


def test_invariant_set_consensus():
    reg = InvariantRegistry("INC-001")
    reg.register_candidate(
        "perception_freshness",
        120.0,
        "ms",
        authority=InvariantAuthority.RUNTIME_CONFIG,
        source_artifact_id="art-1",
        source_locator="config/safety.yaml#freshness_ms",
    )
    reg.register_candidate(
        "perception_freshness",
        0.12,
        "s",
        authority=InvariantAuthority.DEPLOYMENT_CONFIG,
        source_artifact_id="art-2",
        source_locator="deploy/helm.yaml#budget",
    )

    inv_set = reg.build_invariant_set()
    assert inv_set.status == InvariantSetStatus.VALID
    assert len(inv_set.conflicts) == 0
    inv = inv_set.get_invariant("perception_freshness")
    assert inv is not None
    assert inv.status == InvariantStatus.ACTIVE
    assert inv.value == 120.0
    assert inv.unit == "ms"
    assert inv_set.is_verification_blocked() is False


def test_invariant_set_conflicting_authorities_blocks_verification():
    reg = InvariantRegistry("INC-002")
    # Two sources at same authority level declare different values
    reg.register_candidate(
        "perception_freshness",
        120.0,
        "ms",
        authority=InvariantAuthority.RUNTIME_CONFIG,
        source_artifact_id="art-1",
    )
    reg.register_candidate(
        "perception_freshness",
        400.0,
        "ms",
        authority=InvariantAuthority.RUNTIME_CONFIG,
        source_artifact_id="art-2",
    )

    inv_set = reg.build_invariant_set()
    assert inv_set.status == InvariantSetStatus.CONFLICTED
    assert len(inv_set.conflicts) == 1
    assert inv_set.is_verification_blocked() is True

    conflict = inv_set.conflicts[0]
    assert conflict.invariant_id == "perception_freshness"
    assert conflict.status == "CONFLICTED"
    assert len(conflict.candidates) == 2
    assert conflict.selected is None
    assert conflict.verification_blocked is True

    inv = inv_set.get_invariant("perception_freshness")
    assert inv is not None
    assert inv.status == InvariantStatus.CONFLICTED
    assert inv.value is None


def test_incompatible_dimensions_conflict():
    reg = InvariantRegistry("INC-003")
    reg.register_candidate(
        "control_deadline",
        100.0,
        "ms",
        authority=InvariantAuthority.RUNTIME_CONFIG,
    )
    reg.register_candidate(
        "control_deadline",
        50.0,
        "MB",  # Incompatible physical dimension
        authority=InvariantAuthority.DEPLOYMENT_CONFIG,
    )

    inv_set = reg.build_invariant_set()
    assert inv_set.status == InvariantSetStatus.CONFLICTED
    assert inv_set.is_verification_blocked() is True
    assert "Incompatible physical units" in inv_set.conflicts[0].resolution_reason


def test_operator_resolution_unblocks():
    reg = InvariantRegistry("INC-004")
    reg.register_candidate(
        "perception_freshness",
        120.0,
        "ms",
        authority=InvariantAuthority.RUNTIME_CONFIG,
    )
    reg.register_candidate(
        "perception_freshness",
        400.0,
        "ms",
        authority=InvariantAuthority.RUNTIME_CONFIG,
    )

    # Initial build is blocked
    inv_set1 = reg.build_invariant_set("1.0.0")
    assert inv_set1.is_verification_blocked() is True

    # Operator resolves with audit record
    reg.apply_operator_resolution(
        "perception_freshness",
        120.0,
        "ms",
        audit_id="audit_res_001",
        reason="Verified active robot controller firmware threshold",
    )

    inv_set2 = reg.build_invariant_set("1.1.0")
    assert inv_set2.is_verification_blocked() is False
    assert inv_set2.status == InvariantSetStatus.VALID
    inv = inv_set2.get_invariant("perception_freshness")
    assert inv.value == 120.0
    assert inv.authority == InvariantAuthority.OPERATOR_OVERRIDE
    assert "audit_res_001" in inv.assumptions[0]
