# Incident Package: `payments-gateway-pool-exhaustion` (CAU-9001)

A complete, self-contained incident bundle that exercises the **full Cauveris
pipeline** — ingestion → evidence extraction → timeline → invariants →
**model-assisted hypothesis generation** → sandbox baseline → counterfactual
interventions → patch synthesis → 9-point verification → downloadable,
reversible repair package.

## The incident (what happened)

On **2026-10-24 at 18:00 UTC** the `payments-gateway` service started returning
**503 Service Unavailable** on `/v1/charge` during a flash-sale traffic spike
(~420 rps → ~1000 rps). Every failing request shares one signature:

> the **database connection pool was exhausted** — 35 active connections
> against a configured pool of **10** (`database.max_connections` in
> `config/payments.toml`), remaining slots 0, checkout denied after the
> 5000 ms `connection_timeout_ms`.

The database itself (`logs/postgres.log`) corroborates: *"remaining connection
slots are 0"*, *"too many connections"*. Host metrics (`metrics/host.csv`)
stay healthy (CPU ~41%, memory ~1.4 GB / 8 GB), ruling out OOM. Deployment
`v17` (`deployments/events.json`) only changed `cache.ttl_seconds` 60 → 300 —
a red herring the causal engine must dismiss.

**Expected root cause:** `connection_pool_exhaustion`
**Expected hypothesis:** `h_connection_pool_exhaustion`
**Expected patch:** raise `database.max_connections` in `config/payments.toml`
from `10` to `ceil(35 * 1.5) = 53` — a one-line, parser-aware, reversible diff
verified by the 9-point invariant checker (patched pool ≥ measured peak demand).

## Why this bundle needs the model (Nebius Token Factory / NVIDIA Nemotron)

The logs speak **vendor dialect** (HikariCP: *"Connection is not available,
request timed out"*; PostgreSQL: *"remaining connection slots are 0"*) and the
bundle contains a **plausible decoy** (the v17 cache change 15 min before
onset). The evidence is enough for the deterministic rules to detect the pool
mechanism, but the *causal arbitration* — "the pool limit, not the deploy, not
the host, not the network, is the root cause; scale `max_connections`" — is
exactly the `HYPOTHESIS_PROPOSAL` task Cauveris sends to the hosted model when
`NEBIUS_API_KEY` is set:

- `POST /api/v1/incidents/{id}/reconstruct` → stage `hypotheses_generated`
  calls `HypothesisGenerator._gateway_hypothesis()` →
  `NebiusModelGateway.generate(schema=Hypothesis, task_type=HYPOTHESIS_PROPOSAL)`
  against `NEBIUS_MODEL_ID` / `NEBIUS_MODEL_REASONING`
  (`nvidia/Llama-3.1-Nemotron-70B-Instruct-HF` by default), with secret
  scrubbing, JSON `response_format`, circuit breaker and daily budget.
- The model's answer lands as an extra hypothesis `hyp-<incident>-nebius`
  alongside the rule-based ones; every call is recorded under
  `GET /api/v1/incidents/{id}/model-executions` and provider health/latency is
  on `GET /api/v1/model-health`.
- **Without** a key the system degrades *truthfully* to deterministic local
  analysis (no fabricated "model" output) — same patch, same verification —
  which is what you want when testing before spending credits.

See `docs/model-usage.md` for exactly which calls hit the API, and
`docs/pipeline-walkthrough.md` for the stage-by-stage walkthrough.

## Bundle layout

```
manifest.yaml               incident id, title, required_evidence, e2e expectations
README.md                   this file (read as the operator note)
config/payments.toml        [database].max_connections = 10  <- the patchable knob
config/routes.json          retry/cache routes (context)
deployments/events.json     v17 deploy: cache.ttl_seconds 60->300 (red herring)
logs/gateway.log            syslog: pool exhaustion + checkout failures
logs/api-events.jsonl       structured JSONL events
logs/postgres.log           DB side: remaining connection slots are 0
metrics/connections.csv     active_connections 4 -> 35 vs pool_capacity 10
metrics/http.csv            rps, p50/p99, 5xx counts, error rate
metrics/host.csv            CPU/memory of the pod (healthy -> not OOM)
traces/otel.json            spans: db.checkout blocked 5000 ms -> 503
observations/operator_note.md  human write-up
source/gateway/             db.py (pool bootstrap), main.py (checkout path), Dockerfile
docs/                       expected-analysis.md, pipeline-walkthrough.md, model-usage.md
checksums.sha256            SHA-256 of every other file in this bundle
```

## How to run it (pipelines)

The zipped form of this folder is `packages/payments-gateway-pool-exhaustion.zip`
(rebuilt deterministically by `python scripts/build_package_zip.py <dir>`).

### Option A — one-command demo (starts its own backend, zero model spend)

```bash
# deterministic mode: NEBIUS key is stripped for the child process
.venv\Scripts\python.exe scripts/demo_incident_package.py \
  --package packages/payments-gateway-pool-exhaustion --start-backend

# live model mode: forwards NEBIUS_API_KEY so hypothesis generation calls
# Nebius Token Factory (NVIDIA Nemotron) - this is the only mode that spends
.venv\Scripts\python.exe scripts/demo_incident_package.py \
  --package packages/payments-gateway-pool-exhaustion --start-backend --live-model
```

The script logs in (demo mode), creates the incident with `custom_id: CAU-9001`,
uploads the zip, validates, runs `reconstruct`, polls `/events` to SUCCESS,
prints hypotheses / experiments / patches / model executions, and **downloads
the repair package** (`/incidents/{id}/download-patch-package`) into
`report/demo-payments-gateway-pool-exhaustion/` together with a summary JSON.

### Option B — against your already-running stack (backend :8000, web :3000)

```bash
.venv\Scripts\python.exe scripts/demo_incident_package.py \
  --package packages/payments-gateway-pool-exhaustion \
  --base http://127.0.0.1:8000/api/v1
```

or manually: upload the zip in the Mission Control UI
(or `POST /api/v1/incidents/upload`), then watch the pipeline at
`GET /api/v1/incidents/{id}/events` (SSE: `/incidents/{id}/stream`).

### Option C — pure in-process pipeline (no HTTP, no credits — used by tests)

```python
from cauveris.hypothesis.generator import HypothesisGenerator
from cauveris.sandbox.controller import SandboxController
from cauveris.simulation.runner import SimulationRunner
from cauveris.patch.generator import PatchGenerator
from cauveris.verifier.engine import VerificationEngine
from cauveris.schemas.incident import Incident
# see scripts/verify_incident_package.py for a ready-made runner
```

## What "working" looks like

- pipeline reaches `SUCCESS` with all stages green;
- hypotheses include `h_connection_pool_exhaustion` (plus competing ones, and
  `hyp-CAU-9001-nebius` when the model key is live);
- ≥1 experiment reports `failure_oracle.hypothesis_supported` on baseline and
  the intervention clears it;
- a **verified, non-empty unified diff** against `config/payments.toml`
  changing `max_connections` 10 → 53;
- `GET /incidents/{id}/download-patch-package` returns a zip containing
  `manifest.json`, `patch.patch`/`fix.patch`, `rollback.patch`, `rollback.sh`,
  `diagnosis.json/.md`, `provenance.json`, `capability-report.json`,
  `baseline-results.json`, `post-intervention-results.json`,
  `verification-report.json`, `limitations.md`, `application-instructions.md`,
  `checksums.sha256` — each checksum verifiable against the archive bytes.
