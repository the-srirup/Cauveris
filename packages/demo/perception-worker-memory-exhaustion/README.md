# Cauveris Incident Demonstration Package: DEMO-PERCEPTION-MEMORY-002

## Incident Story
During an intensive perception workload in staging, the `perception-worker` process was terminated by the host kernel after its resident set size (620 MiB) exceeded the configured container ceiling (`resources.memory_limit_mb: 512`). The failure caused dropped perception frames, leading to an automated emergency stop event.

## Artifact Inventory
- `manifest.yaml`: Incident metadata declaring affected components, expected evidence, and target capability.
- `config/worker.yaml`: Service runtime and resource definitions, including `resources.memory_limit_mb` (512 MiB), host capacity (6144 MiB available), and repair policy (20% headroom, 1024 MiB cap).
- `config/component_aliases.yaml`: Component alias mapping (`perception-worker`, `perception_worker`, `worker.perception`).
- `telemetry/oom-events.log`: Chronological event sequence capturing startup, memory pressure warnings, allocation failure, OOMKilled termination, and container restart.
- `telemetry/heap.csv`: Time-series telemetry tracking working set, heap usage, memory limit, host available capacity, and restarts.
- `telemetry/runtime-metrics.jsonl`: Structured telemetry confirming CPU and queue depth remained within bounds while memory violated ceiling.
- `traces/inference-spans.jsonl`: Distributed tracing spans showing batch inference operations active during the memory fault without dependency timeouts.
- `source/worker.py`: Syntactically valid worker implementation exposing resource parameter bindings and batch processing interfaces.
- `notes/operator-observations.md`: Operator context noting healthy host headroom and absence of full heap dumps.
- `unknown/diagnostic-context.bin`: Unstructured binary diagnostic payload demonstrating safe universal inventory and selective parser engagement.

## Capability & Expected Repair
- **Mechanism**: `resource_exhaustion` (Failure Family: `memory_or_resource_exhaustion`)
- **Editable Control**: `resources.memory_limit_mb` in `config/worker.yaml`
- **Observed Peak Demand**: 620 MiB
- **Initial Limit**: 512 MiB
- **Headroom Policy**: 1.20x minimum headroom ratio
- **Calculated Requirement**: 620 * 1.20 = 744 MiB -> 768 MiB (aligned to 128 MiB boundary, <= 1024 MiB ceiling)
- **Feasibility**: Host has 6144 MiB available for services, easily accommodating the 256 MiB increase.

## Verification & Limitations
- **Verification Level**: Achieves `STAGING_VERIFIED` / `MODEL_VERIFIED`.
- **Limitation**: The repair resolves the demonstrated memory-limit violation for the observed workload. The available evidence is insufficient to prove that the service has no memory leak. Full leak elimination would require heap profiling over multi-hour runtimes.
