"""Smoke test for the evidence-driven hypothesis generator."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cauveris.hypothesis.generator import HypothesisGenerator  # noqa: E402
from cauveris.schemas.incident import Incident  # noqa: E402

BUNDLE = ROOT / "golden_incident" / "incident-CAU-0001"


def build_incident() -> Incident:
    manifest = {}
    manifest_path = BUNDLE / "manifest.yaml"
    if manifest_path.exists():
        import yaml

        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    return Incident(
        id="CAU-0001",
        title=manifest.get("title", "incident"),
        manifest=manifest,
        bundle_path=str(BUNDLE),
    )


async def main() -> None:
    incident = build_incident()
    hypotheses = await HypothesisGenerator().generate(incident)

    print("=" * 78)
    print(f"HYPOTHESES ({len(hypotheses)})")
    print("=" * 78)
    for hyp in hypotheses:
        print(f"\n[{hyp.hypothesis_id}]  confidence={hyp.confidence_prior:.3f}")
        print(f"  claim      : {hyp.causal_claim}")
        print(f"  expected   : {hyp.expected_observation}")
        print(f"  falsifying : {hyp.falsifying_observation}")
        print(f"  intervention: {hyp.intervention}")
        print(f"  supporting : {hyp.supporting_artifact_ids}")
        if hyp.contradicting_artifact_ids:
            print(f"  contradicting: {hyp.contradicting_artifact_ids}")
        print(f"  missing    : {hyp.missing_evidence}")
        print(f"  params     : {hyp.likely_parameters}  files={hyp.likely_files}")
        print(f"  trials={hyp.estimated_trials} cost={hyp.estimated_cost}")

    print()
    print("=" * 78)
    print("AS JSON")
    print("=" * 78)
    print(json.dumps([h.model_dump(mode="json") for h in hypotheses], indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
