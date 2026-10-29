"""
Deterministic Validation Adapters for Model Proposals in Cauveris.
No model output becomes authoritative without passing these deterministic gates.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from .tasks import (
    TerminologyMappingOutput,
    ProposedTermMapping,
    LogClusteringOutput,
    LogCluster,
    HypothesisProposalOutput,
    ProposedHypothesis,
    RepairStrategyOutput,
    ProposedRepairStrategy,
    MissingEvidenceOutput,
    EvidenceRecommendation,
    ExplanationGenerationOutput,
)
from .enums import ValidationResult

logger = logging.getLogger(__name__)

VALIDATOR_VERSION = "1.0.0"


def validate_terminology_mapping(
    output: TerminologyMappingOutput,
    canonical_signals: Set[str],
    discovered_fields: Set[str],
) -> Tuple[ValidationResult, List[ProposedTermMapping], List[Dict[str, Any]], List[str]]:
    """
    Validate terminology proposals against canonical signal registry.
    """
    accepted: List[ProposedTermMapping] = []
    rejected: List[Dict[str, Any]] = []
    reasons: List[str] = []

    for mapping in output.mappings:
        # Check source field exists
        if mapping.unfamiliar_term not in discovered_fields:
            reason = f"Unfamiliar term '{mapping.unfamiliar_term}' was not found in discovered fields"
            rejected.append({"term": mapping.unfamiliar_term, "reason": reason})
            reasons.append(reason)
            continue

        # Check proposed canonical target exists in registered signals
        if mapping.proposed_canonical_signal not in canonical_signals:
            reason = f"Proposed canonical signal '{mapping.proposed_canonical_signal}' is not in canonical registry"
            rejected.append({"term": mapping.unfamiliar_term, "target": mapping.proposed_canonical_signal, "reason": reason})
            reasons.append(reason)
            continue

        accepted.append(mapping)

    if not output.mappings:
        result = ValidationResult.REJECTED
    elif not rejected:
        result = ValidationResult.ACCEPTED
    elif accepted:
        result = ValidationResult.PARTIAL
    else:
        result = ValidationResult.REJECTED

    return result, accepted, rejected, reasons


def validate_log_clustering(
    output: LogClusteringOutput,
    valid_event_ids: Set[str],
) -> Tuple[ValidationResult, List[LogCluster], List[Dict[str, Any]], List[str]]:
    """
    Validate log clustering proposals: no fabricated event IDs allowed.
    """
    accepted: List[LogCluster] = []
    rejected: List[Dict[str, Any]] = []
    reasons: List[str] = []

    for cluster in output.clusters:
        fabricated = [eid for eid in cluster.representative_event_ids if eid not in valid_event_ids]
        if fabricated:
            reason = f"Cluster '{cluster.cluster_id}' referenced fabricated event IDs: {fabricated}"
            rejected.append({"cluster_id": cluster.cluster_id, "fabricated_ids": fabricated, "reason": reason})
            reasons.append(reason)
            continue

        accepted.append(cluster)

    if not output.clusters:
        result = ValidationResult.REJECTED
    elif not rejected:
        result = ValidationResult.ACCEPTED
    elif accepted:
        result = ValidationResult.PARTIAL
    else:
        result = ValidationResult.REJECTED

    return result, accepted, rejected, reasons


def validate_hypothesis_proposal(
    output: HypothesisProposalOutput,
    registered_mechanisms: Set[str],
    incident_evidence_ids: Set[str],
) -> Tuple[ValidationResult, List[ProposedHypothesis], List[Dict[str, Any]], List[str]]:
    """
    Validate proposed hypotheses against registered mechanisms and incident artifacts.
    Enforces deterministic confidence ceiling.
    """
    accepted: List[ProposedHypothesis] = []
    rejected: List[Dict[str, Any]] = []
    reasons: List[str] = []

    for prop in output.proposals:
        # 1. Mechanism must be registered
        if prop.mechanism_id not in registered_mechanisms:
            reason = f"Mechanism '{prop.mechanism_id}' is not registered in Cauveris mechanism catalog"
            rejected.append({"proposal": prop.mechanism_id, "reason": reason})
            reasons.append(reason)
            continue

        # 2. Supporting evidence references must actually exist
        missing_ids = [eid for eid in prop.supporting_evidence_ids if eid not in incident_evidence_ids]
        if missing_ids:
            reason = f"Proposal for '{prop.mechanism_id}' referenced nonexistent evidence IDs: {missing_ids}"
            rejected.append({"proposal": prop.mechanism_id, "missing_ids": missing_ids, "reason": reason})
            reasons.append(reason)
            continue

        # 3. Deterministic confidence cap: model confidence can never exceed 0.85
        if prop.confidence > 0.85:
            prop.confidence = 0.85

        accepted.append(prop)

    if not output.proposals:
        result = ValidationResult.REJECTED
    elif not rejected:
        result = ValidationResult.ACCEPTED
    elif accepted:
        result = ValidationResult.PARTIAL
    else:
        result = ValidationResult.REJECTED

    return result, accepted, rejected, reasons


def validate_repair_strategy(
    output: RepairStrategyOutput,
    registered_strategies: Set[str],
    editable_controls: Dict[str, Dict[str, Any]],  # key -> {file, min, max, type, units}
) -> Tuple[ValidationResult, List[ProposedRepairStrategy], List[Dict[str, Any]], List[str]]:
    """
    Validate repair strategy proposals: control must be editable, value in safe range.
    """
    accepted: List[ProposedRepairStrategy] = []
    rejected: List[Dict[str, Any]] = []
    reasons: List[str] = []

    for strat in output.strategies:
        if strat.strategy_id not in registered_strategies:
            reason = f"Strategy '{strat.strategy_id}' is not in registered repair strategies"
            rejected.append({"strategy_id": strat.strategy_id, "reason": reason})
            reasons.append(reason)
            continue

        controls_ok = True
        for ctrl in strat.proposed_controls:
            if ctrl.parameter_key not in editable_controls:
                reason = f"Control '{ctrl.parameter_key}' is not an editable configuration control"
                rejected.append({"strategy_id": strat.strategy_id, "control": ctrl.parameter_key, "reason": reason})
                reasons.append(reason)
                controls_ok = False
                break

            meta = editable_controls[ctrl.parameter_key]
            # Bounds check if numerical
            if isinstance(ctrl.proposed_value, (int, float)):
                min_val = meta.get("min")
                max_val = meta.get("max")
                if min_val is not None and ctrl.proposed_value < min_val:
                    reason = f"Proposed value {ctrl.proposed_value} for '{ctrl.parameter_key}' violates min limit {min_val}"
                    rejected.append({"strategy_id": strat.strategy_id, "reason": reason})
                    reasons.append(reason)
                    controls_ok = False
                    break
                if max_val is not None and ctrl.proposed_value > max_val:
                    reason = f"Proposed value {ctrl.proposed_value} for '{ctrl.parameter_key}' violates max limit {max_val}"
                    rejected.append({"strategy_id": strat.strategy_id, "reason": reason})
                    reasons.append(reason)
                    controls_ok = False
                    break

        if controls_ok:
            accepted.append(strat)

    if not output.strategies:
        result = ValidationResult.REJECTED
    elif not rejected:
        result = ValidationResult.ACCEPTED
    elif accepted:
        result = ValidationResult.PARTIAL
    else:
        result = ValidationResult.REJECTED

    return result, accepted, rejected, reasons


def validate_missing_evidence(
    output: MissingEvidenceOutput,
    existing_evidence_types: Set[str],
) -> Tuple[ValidationResult, List[EvidenceRecommendation], List[Dict[str, Any]], List[str]]:
    """
    Validate missing evidence recommendations: filter out types already gathered.
    """
    accepted: List[EvidenceRecommendation] = []
    rejected: List[Dict[str, Any]] = []
    reasons: List[str] = []

    for rec in output.recommendations:
        if rec.evidence_type in existing_evidence_types:
            reason = f"Evidence type '{rec.evidence_type}' is already collected in the bundle"
            rejected.append({"evidence_type": rec.evidence_type, "reason": reason})
            reasons.append(reason)
            continue
        accepted.append(rec)

    if not output.recommendations:
        result = ValidationResult.REJECTED
    elif not rejected:
        result = ValidationResult.ACCEPTED
    elif accepted:
        result = ValidationResult.PARTIAL
    else:
        result = ValidationResult.REJECTED

    return result, accepted, rejected, reasons


def validate_explanation(
    output: ExplanationGenerationOutput,
    persisted_verification_level: str,
    persisted_numbers: Optional[Set[str]] = None,
    known_limitations: Optional[List[str]] = None,
) -> Tuple[ValidationResult, ExplanationGenerationOutput, List[Dict[str, Any]], List[str]]:
    """
    Validate that generated explanation does not contradict verified facts, upgrade verification levels,
    or drop acknowledged limitations.
    """
    rejected: List[Dict[str, Any]] = []
    reasons: List[str] = []

    text = f"{output.user_explanation} {output.technical_summary}"
    verified_levels = {"MODEL_VERIFIED", "TEST_VERIFIED", "RUNTIME_VERIFIED", "STAGING_VERIFIED", "VERIFIED"}

    # Model cannot claim verified or passed if persisted level was not proven or degraded
    if persisted_verification_level.upper() not in verified_levels:
        lower_text = text.lower()
        if ("verified" in lower_text or "passed" in lower_text) and not any(
            neg in lower_text for neg in ("not verified", "unverified", "not passed", "failed", "partial", "not proven")
        ):
            reason = f"Model explanation claimed verification success but persisted verification level is '{persisted_verification_level}'"
            rejected.append({"reason": reason})
            reasons.append(reason)

    # Limitations cannot disappear if there are known system limitations
    if known_limitations and not output.acknowledged_limitations:
        reason = "Model explanation omitted known system limitations"
        rejected.append({"reason": reason})
        reasons.append(reason)

    if rejected:
        return ValidationResult.REJECTED, output, rejected, reasons

    return ValidationResult.ACCEPTED, output, [], []
