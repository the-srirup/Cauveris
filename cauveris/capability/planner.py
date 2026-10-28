"""
Capability Planner and honest capability evaluation for Cauveris.
Evaluates:
- Can it be read?
- Can evidence be extracted?
- Can a mechanism be diagnosed?
- Is a suitable model available?
- Is an editable control available?
- Is a safe editor available?
- Is a verification adapter available?

Produces a CapabilityReport before repair begins.
Handles unknown incidents honestly: if no safe repair is possible, produces diagnosis,
hypotheses, evidence coverage, missing files/metrics, unsupported mechanisms, manual
investigation suggestions, and NO speculative patch.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from cauveris.analysis.evidence_aliaser import EvidenceAliaser
from cauveris.analysis.mechanism_detectors import MechanismDetectorRegistry
from cauveris.inventory.artifact_inventory import ArtifactEntry, ArtifactInventory
from cauveris.patch.config_locators import ConfigLocatorRegistry

logger = logging.getLogger(__name__)


@dataclass
class StageCapability:
    can_execute: bool
    status: str  # "supported", "partial", "unsupported"
    reasons: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CapabilityReport:
    """The formal capability report generated before any repair action is attempted."""

    ingestion: StageCapability
    diagnosis: StageCapability
    simulation: StageCapability
    repair: StageCapability
    verification: StageCapability
    unsupported_artifacts: List[str] = field(default_factory=list)
    missing_evidence: List[str] = field(default_factory=list)
    candidate_mechanisms: List[Dict[str, Any]] = field(default_factory=list)
    patchable_controls: List[Dict[str, Any]] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    honest_repair_decision: str = "REFUSE"  # "PERMIT_REPAIR" or "REFUSE"
    manual_investigation_suggestions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ingestion": self.ingestion.to_dict(),
            "diagnosis": self.diagnosis.to_dict(),
            "simulation": self.simulation.to_dict(),
            "repair": self.repair.to_dict(),
            "verification": self.verification.to_dict(),
            "unsupported_artifacts": self.unsupported_artifacts,
            "missing_evidence": self.missing_evidence,
            "candidate_mechanisms": self.candidate_mechanisms,
            "patchable_controls": self.patchable_controls,
            "limitations": self.limitations,
            "honest_repair_decision": self.honest_repair_decision,
            "manual_investigation_suggestions": self.manual_investigation_suggestions,
        }


class CapabilityPlanner:
    """Plans and determines platform capabilities for an arbitrary incident package."""

    def __init__(self):
        self.aliaser = EvidenceAliaser()
        self.detector_registry = MechanismDetectorRegistry()
        self.config_registry = ConfigLocatorRegistry()

    def evaluate_bundle(
        self,
        bundle_path: Path,
        inventory_entries: Optional[List[ArtifactEntry]] = None,
    ) -> CapabilityReport:
        bundle_path = Path(bundle_path)
        if inventory_entries is None:
            inventory = ArtifactInventory(bundle_path)
            inventory_entries = inventory.scan()

        # 1. Ingestion evaluation
        unsupported_arts: List[str] = []
        readable_arts: List[str] = []
        for art in inventory_entries:
            if art.parse_status in ("failed", "unsupported", "skipped_binary"):
                unsupported_arts.append(f"{art.relative_path} ({art.detected_type}: {art.parse_status})")
            else:
                readable_arts.append(art.relative_path)

        can_ingest = len(readable_arts) > 0
        ingestion_cap = StageCapability(
            can_execute=can_ingest,
            status="supported" if not unsupported_arts else "partial",
            reasons=[
                f"{len(readable_arts)} artifacts successfully read and inventoried",
                f"{len(unsupported_arts)} artifacts unparsed or unsupported binary",
            ],
            details={"total_artifacts": len(inventory_entries), "readable": len(readable_arts)},
        )

        # 2. Extract logs, metrics, configs from inventory
        logs_text_parts: List[str] = []
        raw_metrics: Dict[str, Any] = {}
        config_entries: Dict[str, Any] = {}
        config_files: List[Path] = []

        for art in inventory_entries:
            p = bundle_path / art.relative_path
            rel_lower = art.relative_path.lower()
            is_log_candidate = (
                art.detected_type in ("log", "text/plain", "jsonl", "ndjson")
                or any(kw in rel_lower for kw in ("log", "event", "record", "trace", "journal", "packet"))
                or rel_lower.endswith((".log", ".txt", ".ndjson", ".jsonl"))
            )
            if is_log_candidate:
                try:
                    logs_text_parts.append(p.read_text(encoding="utf-8", errors="ignore")[:50000])
                except Exception:
                    pass
            elif art.detected_type.startswith("metric") or "metric" in art.relative_path.lower():
                # Extract metrics
                try:
                    txt = p.read_text(encoding="utf-8", errors="ignore")
                    # simple key: value or csv extraction
                    for line in txt.splitlines()[:50]:
                        if ":" in line or "=" in line:
                            sep = ":" if ":" in line else "="
                            parts = line.split(sep, 1)
                            raw_metrics[parts[0].strip()] = parts[1].strip()
                except Exception:
                    pass
            elif art.is_editable or art.detected_type in ("yaml", "json", "toml", "ini", "env", "xml"):
                config_files.append(p)
                try:
                    txt = p.read_text(encoding="utf-8", errors="ignore")
                    for line in txt.splitlines()[:50]:
                        if ":" in line or "=" in line:
                            sep = ":" if ":" in line else "="
                            parts = line.split(sep, 1)
                            config_entries[parts[0].strip()] = parts[1].strip()
                except Exception:
                    pass

        logs_combined = "\n".join(logs_text_parts)

        # Map metrics with aliasing
        matched_metrics, unknown_metrics = self.aliaser.match_dictionary(raw_metrics)
        canonical_metric_values: Dict[str, Any] = {}
        for canon, m in matched_metrics.items():
            try:
                canonical_metric_values[canon] = float(m.value)
            except (ValueError, TypeError):
                canonical_metric_values[canon] = m.value

        # 3. Diagnosis evaluation (8 mechanisms)
        mech_results = self.detector_registry.detect_all(
            logs_text=logs_combined,
            metrics_dict=canonical_metric_values,
            config_entries=config_entries,
            bundle_path=bundle_path,
        )

        can_diagnose = len(mech_results) > 0 and mech_results[0].confidence >= 0.50
        candidate_mechs = [res.to_dict() for res in mech_results]
        missing_evidence: List[str] = []
        for res in mech_results:
            missing_evidence.extend(res.missing_evidence)
        missing_evidence = sorted(set(missing_evidence))

        diagnosis_cap = StageCapability(
            can_execute=can_diagnose,
            status="supported" if can_diagnose else "unsupported",
            reasons=[
                f"Identified {len(mech_results)} candidate mechanisms",
                f"Top mechanism: {mech_results[0].mechanism_id} ({mech_results[0].confidence:.2f})"
                if mech_results
                else "No supported mechanism detected with sufficient confidence",
            ],
            details={"candidates": [r.mechanism_id for r in mech_results]},
        )

        # 4. Simulation evaluation
        # Check if calibrated mathematical or digital-twin model exists for top mechanism
        top_mech = mech_results[0].mechanism_id if mech_results else None
        simulatable_mechanisms = {
            "resource_exhaustion",
            "dependency_timeout",
            "lock_contention",
            "connection_pool_exhaustion",
            "queue_overflow_backpressure",
            "worker_saturation",
            "transport_loss_jitter",
            "clock_skew",
            "arrival_overload",
        }
        can_simulate = bool(top_mech and top_mech in simulatable_mechanisms)
        simulation_cap = StageCapability(
            can_execute=can_simulate,
            status="supported" if can_simulate else "unsupported",
            reasons=[
                f"Digital twin model available for {top_mech}"
                if can_simulate
                else "No matching analytical simulation model for detected anomalies"
            ],
            details={"simulatable": can_simulate, "top_mechanism": top_mech},
        )

        # 5. Repair evaluation: Is an editable control available with safe editor?
        patchable_controls: List[Dict[str, Any]] = []
        for cfg_p in config_files:
            plugin = self.config_registry.select_plugin(cfg_p)
            if plugin is not None:
                # Check for patchable needles related to top_mech
                needles = [
                    "batch_window", "batching_window", "timeout", "deadline",
                    "memory_limit", "workers", "queue_depth", "buffer_size",
                    "pool_size", "max_connections", "max_pool", "max_active",
                ]
                loc = plugin.locate_parameter(cfg_p, needles)
                if loc is not None:
                    k, v = loc
                    rel = str(cfg_p.relative_to(bundle_path)).replace("\\", "/")
                    patchable_controls.append({
                        "file": rel,
                        "key": k,
                        "current_value": v,
                        "format": plugin.format_name,
                        "editor": plugin.__class__.__name__,
                    })

        can_repair = can_diagnose and can_simulate and len(patchable_controls) > 0
        repair_cap = StageCapability(
            can_execute=can_repair,
            status="supported" if can_repair else "unsupported",
            reasons=[
                f"Found {len(patchable_controls)} patchable configuration controls"
                if patchable_controls
                else "No safe editable configuration control discovered in bundle"
            ],
            details={"patchable_controls_count": len(patchable_controls)},
        )

        # 6. Verification evaluation
        # Check regression tests or workspace validation
        has_tests = any("test" in art.relative_path.lower() for art in inventory_entries)
        can_verify = can_repair and (has_tests or can_simulate)
        verification_cap = StageCapability(
            can_execute=can_verify,
            status="supported" if can_verify else "unsupported",
            reasons=[
                "Verification adapter and invariant checking available"
                if can_verify
                else "No verification adapter or regression harness available"
            ],
            details={"has_regression_tests": has_tests, "twin_verifier_available": can_simulate},
        )

        # 7. Overall decision and honest handling
        decision = "PERMIT_REPAIR" if can_repair else "REFUSE"
        limitations: List[str] = []
        if unsupported_arts:
            limitations.append(f"{len(unsupported_arts)} bundle artifacts could not be parsed")
        if not can_diagnose:
            limitations.append("Incident mechanism could not be diagnosed from provided logs/metrics")
        if not patchable_controls:
            limitations.append("No safe, patchable configuration parameter was located")
        if not can_simulate:
            limitations.append("No calibrated simulation model covers the active anomaly")

        manual_suggestions: List[str] = []
        if decision == "REFUSE":
            if not can_diagnose:
                manual_suggestions.append("Inspect application crash logs and core dumps for unhandled exceptions.")
            if missing_evidence:
                manual_suggestions.append(f"Collect missing telemetry: {', '.join(missing_evidence[:3])}.")
            if not patchable_controls:
                manual_suggestions.append("Provide application deployment manifest or config file (YAML/JSON/TOML/INI).")
            manual_suggestions.append("Verify network ingress routing and upstream dependency availability.")

        return CapabilityReport(
            ingestion=ingestion_cap,
            diagnosis=diagnosis_cap,
            simulation=simulation_cap,
            repair=repair_cap,
            verification=verification_cap,
            unsupported_artifacts=unsupported_arts,
            missing_evidence=missing_evidence,
            candidate_mechanisms=candidate_mechs,
            patchable_controls=patchable_controls,
            limitations=limitations,
            honest_repair_decision=decision,
            manual_investigation_suggestions=manual_suggestions,
        )
