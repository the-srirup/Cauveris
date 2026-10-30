# Operator Incident Note — CAU-9001 (payments-gateway)

**When:** 2026-10-24, first 503s at 18:00:02 UTC, recovered 18:00:40 UTC after manual intervention.
**Where:** payments-gateway pods in region eu-central, fronting pg-orders.internal.

## What we saw
- Flash-sale campaign started 17:55 UTC; traffic climbed from ~420 rps to ~1000 rps.
- At 18:00:02 the gateway started returning 503 on /v1/charge. Every failure shares one
  signature: the database connection pool was exhausted — active connections 35 against
  a configured pool of 10, remaining slots 0.
- The database itself logged "remaining connection slots are 0" and "too many connections".
- p99 latency went from ~80 ms to >5 s; the pool checkout wait hit the 5000 ms ceiling.

## What we ruled out
- Not memory: pod memory stayed at ~1.4 GB of 8 GB, CPU ~41%. No OOM, no pressure.
- Not the v17 deploy: it changed only cache.ttl_seconds (60 -> 300) and a banner flag.
  database.max_connections has been 10 since v9 and was never revisited.
- Not the network: no packet loss or jitter on the link; the waits are queueing on the
  pool, not in transit.

## What fixed it manually
On-call raised the per-pod pool headroom; 5xx rate fell back under 1% within a minute.
The permanent fix is a configuration change to database.max_connections sized for the
measured peak concurrent demand (35), with headroom — i.e. exactly the kind of patch
Cauveris is supposed to synthesise and verify.
