# Cauveris Production Deployment on Nebius Cloud

This directory provides the production container definitions and orchestration manifests for deploying Cauveris with Nebius Token Factory and NVIDIA open-source model inference (`nvidia/Llama-3.1-Nemotron-70B-Instruct-HF`).

## Architecture Overview

```mermaid
flowchart TD
    subgraph Client ["Client & Browser"]
        User["Operator / Engineer"]
    end

    subgraph IngressLayer ["Ingress & Routing"]
        Ingress["Nginx Ingress / Reverse Proxy (Port 80/443)"]
    end

    subgraph CauverisStack ["Cauveris Container Cluster"]
        Web["Next.js Web UI (Port 3000)<br/>UID 10001 (nextjs)"]
        API["FastAPI Orchestrator (Port 8000)<br/>UID 10001 (cauveris)"]
        
        subgraph PipelineSubsystem ["Pipeline & Analysis Engine"]
            Twin["Kinematic & Digital Twin"]
            DetCheck["Deterministic Verifier"]
            Gateway["Nebius Model Gateway<br/>(Circuit Breaker & Cost Control)"]
        end
    end

    subgraph NebiusCloud ["Nebius Cloud AI Services"]
        TokenFactory["Nebius Token Factory API<br/>https://api.tokenfactory.nebius.com/v1"]
        Nemotron["NVIDIA Model<br/>nvidia/Llama-3.1-Nemotron-70B-Instruct-HF"]
    end

    User --> Ingress
    Ingress -->|/api, /health, /ready| API
    Ingress -->|/| Web
    Web --> API
    API --> Twin
    API --> DetCheck
    API --> Gateway
    Gateway -->|Bounded Assistance (HTTPS)| TokenFactory
    TokenFactory --> Nemotron
```

## Prerequisites

1. **Nebius Cloud Account & Token Factory Access:**
   - Active Nebius Cloud project with access to Token Factory API.
   - API Key created in Nebius Console with permissions to invoke inference endpoints.
2. **Infrastructure Choices:**
   - **Option A (VM):** Ubuntu 22.04 LTS or Debian 12 compute instance with Docker and Docker Compose v2 installed.
   - **Option B (Kubernetes):** Nebius Managed Kubernetes (MK8s) cluster (v1.27+) with `kubectl` configured and an NGINX ingress controller.
3. **Environment Security:**
   - Generate a cryptographically secure random string (at least 32 characters) for `CAUVERIS_JWT_SECRET`.

---

## Environment Variable Reference

| Variable Name | Required | Default Value | Description |
|---|---|---|---|
| `NEBIUS_API_KEY` | Yes (in prod) | *None* | Secret Nebius Token Factory API key. Must never be committed. |
| `NEBIUS_BASE_URL` | No | `https://api.tokenfactory.nebius.com/v1` | Nebius endpoint. `api.nebius.ai` is auto-normalized if provided. |
| `NEBIUS_MODEL_ID` | No | `nvidia/Llama-3.1-Nemotron-70B-Instruct-HF` | NVIDIA open-source model hosted by Nebius. |
| `NEBIUS_REQUEST_TIMEOUT_SECONDS` | No | `60.0` | HTTP request timeout in seconds for inference calls. |
| `NEBIUS_MAX_RETRIES` | No | `3` | Maximum retry attempts on transient 429/503 errors. |
| `NEBIUS_MAX_CONCURRENT_REQUESTS` | No | `4` | Concurrency limiter to protect against thread starvation. |
| `NEBIUS_DAILY_BUDGET_LIMIT` | No | `50.0` | Maximum estimated daily spending in USD before circuit breaker trips. |
| `CAUVERIS_MODEL_PROVIDER_REQUIRED` | No | `true` | When true, container startup fails readiness if Nebius key is missing. |
| `CAUVERIS_JWT_SECRET` | Yes | *None* | Shared secret for signing session and API tokens. |
| `CAUVERIS_DEMO_MODE` | No | `false` | Disable sample/demo mock overrides in production. |
| `CAUVERIS_DEMO_AUTH` | No | `false` | Enforce explicit user credentials; no automatic demo user login. |

---

## Deployment Option 1: Docker Compose on Nebius VM

### 1. Clone & Set Environment
```bash
git clone https://github.com/your-org/cauveris.git
cd cauveris

cat <<EOF > .env
NEBIUS_API_KEY=your-actual-nebius-api-key
CAUVERIS_JWT_SECRET=$(openssl rand -hex 32)
MODEL_PROVIDER_REQUIRED=true
EOF
```

### 2. Build and Launch
```bash
docker compose -f deploy/nebius/docker-compose.nebius.yml up -d --build
```

### 3. Verify Health
```bash
# Check container status
docker compose -f deploy/nebius/docker-compose.nebius.yml ps

# Verify API Readiness (returns HTTP 200)
curl -i http://localhost:8000/api/v1/ready

# Check Model Health & Provider Status
curl -s http://localhost:8000/api/v1/model-health | jq .
```

---

## Deployment Option 2: Nebius Managed Kubernetes (MK8s)

### 1. Configure Secrets and ConfigMap
```bash
kubectl apply -f deploy/nebius/k8s-deployment.yaml

# Patch in your actual credentials
kubectl create secret generic cauveris-nebius-credentials \
  --namespace cauveris \
  --from-literal=NEBIUS_API_KEY="your-actual-nebius-api-key" \
  --from-literal=CAUVERIS_JWT_SECRET="$(openssl rand -hex 32)" \
  --dry-run=client -o yaml | kubectl apply -f -
```

### 2. Verify Pod Health and Rollout
```bash
kubectl rollout status deployment/cauveris-api -n cauveris
kubectl rollout status deployment/cauveris-web -n cauveris

kubectl get pods -n cauveris -o wide
```

---

## Verification & Smoke Testing

To test the live Nebius Token Factory connection and the NVIDIA Nemotron model without modifying production state:

```bash
python scripts/smoke_test_nebius.py --live
```

Expected output:
```
================================================================================
Cauveris Live Nebius and NVIDIA Nemotron Smoke Test
================================================================================
[INFO] Endpoint: https://api.tokenfactory.nebius.com/v1
[INFO] Model: nvidia/Llama-3.1-Nemotron-70B-Instruct-HF
[PASS] API Key configured (scrubbed: ************)
[PASS] Liveness & Readiness: OK
[PASS] Model Health Check: NEBIUS_NVIDIA_ACTIVE
[PASS] Live Inference Request dispatched...
[PASS] Model returned 200 OK (Latency: 1.42s, Tokens: 384, Cost: $0.0003)
[PASS] Execution Record verified in audit store.
================================================================================
STATUS: NEBIUS NVIDIA INTEGRATION OPERATIONAL
================================================================================
```

---

## Teardown

### Docker Compose:
```bash
docker compose -f deploy/nebius/docker-compose.nebius.yml down -v
```

### Kubernetes:
```bash
kubectl delete namespace cauveris
```

---

## Troubleshooting Guide

1. **Readiness Probe Failing (`/api/v1/ready` returns 503):**
   - Check if `CAUVERIS_MODEL_PROVIDER_REQUIRED=true` and `NEBIUS_API_KEY` is empty. If running in offline robot mode without Nebius access, set `CAUVERIS_MODEL_PROVIDER_REQUIRED=false`.
2. **Circuit Breaker Open:**
   - If consecutive 5xx errors from the provider exceed 5 failures within 60 seconds, the breaker trips to `OPEN`. Check network egress rules or firewall settings blocking outbound HTTPS traffic to `api.tokenfactory.nebius.com`.
3. **Budget Exceeded:**
   - If estimated cost exceeds `NEBIUS_DAILY_BUDGET_LIMIT` ($50.00 default), the controller throttles requests until the next UTC day or until the limit is raised.
