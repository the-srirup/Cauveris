# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary users are robotics-fleet and cyber-physical-system operators — SREs and field engineers — in the middle of a live operational incident (thermal throttling, sensor drift, batching latency spikes, memory leaks, mechanical stall events). Their job: get from a raw incident bundle to a verified root cause and a deployable, reversible repair, fast, from the Mission Control web console. (Confirmed in the init interview, 2026-10-31.)

## Product Purpose

Cauveris is an autonomous reality debugger and digital-twin investigation platform for cyber-physical and robototic systems. It ingests an incident `.zip` bundle, reconstructs a high-fidelity holographic digital twin, generates evidence-grounded causal hypotheses, validates them through counterfactual physics simulation, synthesizes targeted configuration patches, and packages verifiable, reversible repair archives for field deployment. Success means the operator leaves with a root-cause diagnosis they can trust and a repair they can roll back.

## Positioning

Truthful execution architecture (confirmed in the init interview): Cauveris never fabricates telemetry, model output, or canned outcomes. When hosted cloud inference is disabled or unreachable, it degrades to deterministic local simulation engines and formal rule-based causal analysis. Combined with holographic twin reconstruction, counterfactual verification, and reversible repair ZIPs, that honesty-under-degradation is the mechanism a neighboring product could not truthfully copy.

## Operating Context

- Two runnable surfaces: FastAPI REST & SSE API on port 8000 (Swagger at `/docs`) and the Next.js "Mission Control" web console on port 3000 (`apps/web`, routes: holographic-reconstruction, causal-constellation, ghost-lab, evidence-vault, patch-forge, reality-rewind, victory-replay, reports, settings, login).
- Core workflow, drivable from the console or the API: login (JWT session, RBAC) → upload incident `.zip` → reconstruct digital twin → generate hypotheses → verify via sandboxed counterfactual simulation → download the reversible repair package.
- Run locally with `uv run cauveris serve` + `cd apps/web && npm run dev`, or the one-command rehearsal stack `python scripts/start_live_demo.py`. State lives in local SQLite under `data/`.
- Built as a Nebius/NVIDIA hackathon submission: three-tier Nemotron model gateway on Nebius Token Factory (fast triage, 70B reasoning, 340B escalation) with JSON-schema outputs, secret scrubbing, circuit breakers, and token metering. `CAUVERIS_DEMO_MODE=true` seeds demo users for presentations.

## Capabilities and Constraints

- Safe ingestion of arbitrary incident `.zip` bundles (JSON, JSONL, YAML, CSV, ROS logs, config files, kernel traces) without executing untrusted code: MIME detection, SHA-256 checksums, path-traversal guards.
- Holographic digital twin: physical topology graph, multi-channel clock synchronization, temporal state reconstruction.
- Model gateway with deterministic local fallback. Binding constraint (confirmed): never fabricate results — offline or degraded cloud means local simulation and rule-based causal analysis, not synthetic telemetry.
- Counterfactual verification in sandboxed workspaces: baseline failure reproduction, parameter perturbation sweeps, invariant satisfaction checks.
- Reversible repair packaging: `.zip` containing patch diffs, metadata manifest, verification evidence, and zero-dependency `rollback.sh` / `rollback.ps1`.
- Security posture: JWT session auth with RBAC, cost-class rate limiting, automatic secret redaction.
- Terminology: incident IDs like `CAU-0001`, hypothesis IDs like `hyp-001`.
- Undecided per deployment: whether hosted Nebius tiers are active depends on `NEBIUS_API_KEY`; zero-spend demos run with Nebius disabled (`CAUVERIS_NEBIUS_ENABLED=false`) against the packaged demo incident.

## Brand Commitments

- Name: Cauveris. 100% open source under the Apache License 2.0 (OSI-approved); see `LICENSE` at the repo root.
- The no-fabrication rule is a product behavior, not a slogan: it is implemented as the local-fallback path and must survive every future change.

## Evidence on Hand

- `packages/golden_incident/incident-CAU-0001/` — reference golden incident bundle (including `recordings/robot_run.mcap`).
- `packages/payments-gateway-pool-exhaustion.zip` — packaged demo incident with a demo runner.
- `datasets/` — reference incident bundles and benchmark sets.
- `docs/CAPABILITY_ASSESSMENT_2026-10.md` — October 2026 assessment of which capabilities are real vs for-show.
- `docs/MASTER_REFERENCE_MANUAL.md`, `docs/FRONTEND_BACKEND_INTEGRATION.md`, `docs/HOLOGRAPHIC_RECONSTRUCTION_*.md`, `README.md`.
- `tests/` — 500+ pytest tests; `apps/web` has vitest suites and Playwright e2e.
- Absences future work must not invent: no customer testimonials, case studies, pricing, licensing sales terms, or third-party benchmark claims exist. Do not fabricate any.

## Product Principles

1. Truthful execution over impressive output: when the cloud is unreachable, say so with a deterministic local answer — never invent data.
2. Every claim carries evidence: hypotheses, verifications, and patches are traceable to ingested artifacts and simulation runs.
3. Reversibility by default: every repair ships with a manifest and a working rollback path.
4. Keep the operator in the loop: the console shows real pipeline state, model-health, and token/cost metering in real time instead of hiding it.
