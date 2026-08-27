A high-performance, multi-layered security and telemetry guardrail proxy designed to protect upstream Large Language Model (LLM) endpoints from prompt injection attacks, sensitive data leaks, and denial-of-service (DoS) abuse.

---

## 🏗️ System Architecture

Aegis sits transparently between client applications and upstream LLM providers (e.g., Ollama, OpenAI). Every request passes through a synchronous multi-stage security pipeline:

              ┌─────────────────────────────────────────┐
              │              Client Request             │
              └────────────────────┬────────────────────┘
                                   │
                                   ▼
              ┌─────────────────────────────────────────┐
              │      L0: Redis Sliding-Window           │
              │             Rate Limiter                │
              └────────────────────┬────────────────────┘
                                   │ (Allowed)
                                   ▼
              ┌─────────────────────────────────────────┐
              │       L1: Fast Heuristics Engine        │
              │   (Regex, Keywords, Pattern Matching)   │
              └────────────────────┬────────────────────┘
                                   │ (Passed)
                                   ▼
              ┌─────────────────────────────────────────┐
              │      L2: Deep NLP Intent Classifier     │
              │       (DistilBERT ONNX Model)           │
              └────────────────────┬────────────────────┘
                                   │ (Passed)
                                   ▼
              ┌─────────────────────────────────────────┐
              │             Upstream LLM                │
              │           (Ollama / Local)              │
              └────────────────────┬────────────────────┘
                                   │
                                   ▼
              ┌─────────────────────────────────────────┐
              │      L3: Output Guardrail Engine        │
              │    (PII Redaction / Toxicity Check)     │
              └────────────────────┬────────────────────┘
                                   │
                                   ▼
              ┌─────────────────────────────────────────┐
              │       Client Response + Telemetry       │
              └─────────────────────────────────────────┘

---

## 🔒 Key Security Features

* **L0 — Sliding-Window Rate Limiting:** Enforces strict client IP request limits using Redis (`10 requests / 60s` default) to prevent DoS attacks.
* **L1 — Heuristics Guard:** Instantly drops known jailbreaks, prompt injection patterns, and forbidden system instruction keywords in sub-5ms.
* **L2 — DistilBERT ONNX Classification:** Runs local high-speed transformer inference on incoming prompts to detect nuanced intent vectors without high latency overhead.
* **L3 — Output Safety & Telemetry:** Scans model outputs before returning them to the client, masking sensitive content and appending timing metrics (`_aegis_telemetry`).
* **Real-time Observability:** Exposes Prometheus `/metrics` scraped directly into pre-configured Grafana dashboards.

---

## 📊 Benchmarks & Performance Summary

Tested under concurrent asynchronous load against local `llama3.2:1b`:

| Metric | Measured Value | Description |
Aegis Proxy is a FastAPI-based security gateway for LLM applications.  
It sits between your clients and an upstream model endpoint, applying layered input/output safeguards, rate limiting, and telemetry.

---

## What this project does

Aegis provides:

- **L0 rate limiting** via Redis sliding window
- **L1 heuristic prompt scanning** (regex + entropy + secret pattern checks)
- **L2 intent classification** using ONNX inference for adversarial intent detection
- **L3 output guardrails** for secret/PII detection and redaction
- **Proxy forwarding** to OpenAI-compatible `/v1/chat/completions` endpoints
- **Observability** with Prometheus metrics (and optional Grafana via Docker Compose)

---

## Request lifecycle

Every request to `POST /v1/chat/completions` follows this path:

1. **Rate limit check** (per client IP)
2. **L1 input scan** for known malicious patterns/secrets
3. **L2 input scan** for semantic intent risk
4. **Forward to upstream LLM** if input passes
5. **L3 output scan/redaction** on non-streaming responses
6. **Return response + `_aegis_telemetry`**

If a check blocks:
- Rate limiting returns **HTTP 429**
- Security checks return **HTTP 400** with reason metadata

---

## Tech stack

- **API framework:** FastAPI + Uvicorn
- **Rate limiting:** Redis
- **HTTP client:** httpx
- **ML inference:** ONNX Runtime + Hugging Face tokenizer
- **Monitoring:** Prometheus client
- **Optional ops stack:** Docker Compose + Prometheus + Grafana

---

## Repository layout

```text
Aegis-Proxy/
├── main.py                      # FastAPI gateway + routing + telemetry
├── rate_limiter.py              # Redis sliding-window limiter
├── app/
│   ├── core/pipeline.py         # Unified L1/L2/L3 orchestration
│   └── scanners/
│       ├── l1_heuristics.py     # Pattern/secret/entropy checks
│       ├── l1_cache.py          # Optional semantic cache scanner (Qdrant)
│       ├── l2_intent.py         # ONNX intent scanner helper
│       └── l3_output_guard.py   # Output redaction/guardrails
├── scripts/
│   ├── download_datasets.py
│   ├── preprocess_datasets.py
│   ├── train_l2_classifier.py
│   └── index_l1_cache.py
├── tests/                       # Script-style test/benchmark utilities
├── docker-compose.yml
├── Dockerfile
└── prometheus.yml
```

---

## Prerequisites

### Runtime prerequisites

- Python **3.11+**
- Redis (local or container)
- L2 model artifacts in `./models/l2_intent_model/`:
  - `aegis_l2_classifier_quant.onnx` (or `aegis_l2_classifier.onnx`)
  - `tokenizer/` directory

### Optional prerequisites

- Docker + Docker Compose (for full local stack)
- Local LLM server (e.g., Ollama) or any OpenAI-compatible upstream

---

## Configuration

Environment variables used by `main.py`:

| Variable | Default | Description |
|---|---|---|
| **Input Scanning Overhead** | `4.5ms – 19.4ms` | Combined L1 + L2 execution latency |
| **Rate Limit Interception** | `11.4ms – 46.6ms` | Blocked requests dropped before upstream call |
| **Default Threshold** | `10 req / 60s` | Fully configurable sliding window per IP |
| **Pipeline Reliability** | `100% Pass Rate` | Sustained concurrent async requests with zero memory leaks |
| `UPSTREAM_LLM_URL` | `https://api.openai.com/v1/chat/completions` | Upstream chat completion URL |
| `CANARY_TOKENS` | `AEGIS_SECRET_CANARY` | Comma-separated canary tokens for output leak detection/redaction |
| `REDIS_HOST` | `redis` | Redis host for rate limiter |

Rate limiter defaults (from code):
- `max_requests = 10`
- `window_seconds = 60`

L2 threshold default:
- `l2_confidence_threshold = 0.85`

---

## 🚀 Quick Start Guide
## Quick start (Docker Compose)

The repository includes an app + Redis + Prometheus + Grafana stack.

```bash
docker-compose up -d --build
```

Services:
- Aegis Proxy: `http://localhost:8000`
- Swagger docs: `http://localhost:8000/docs`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000` (admin password from compose file)

Stop services:

```bash
docker-compose down
```

---

## Quick start (local Python)

1. Create and activate a virtual environment
2. Install dependencies
3. Ensure Redis is reachable
4. Ensure L2 model/tokenizer files exist under `./models/l2_intent_model`
5. Run the API

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

---

## API usage

### Root

```bash
curl http://localhost:8000/
```

### Non-streaming completion

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: ******" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [
      {"role": "user", "content": "Explain the CAP theorem in simple terms."}
    ],
    "stream": false
  }'
```

### Streaming completion

```bash
curl -N -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: ******" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [
      {"role": "user", "content": "Give me a short poem about secure coding."}
    ],
    "stream": true
  }'
```

> Note: output redaction is implemented for the non-streaming path in `main.py`.
---

## Blocking and redaction behavior

### Input blocked

When malicious input is detected, response shape includes:

- `error.message`
- `error.type = "security_blocked"`
- `error.code` (`L1_HEURISTICS` or `L2_DISTILBERT`)
- latency telemetry (`l1_latency_ms`, `l2_latency_ms`, `total_latency_ms`)

### Rate limited

When limit is exceeded:
- HTTP `429`
- `Retry-After` header
- JSON body with `RATE_LIMIT_EXCEEDED`

### Output redaction

The output scanner can redact:
- canary tokens
- OpenAI-style keys
- emails
- credit cards
- US SSNs
- phone numbers
- database connection URIs

The proxy also appends:

```json
"_aegis_telemetry": {
  "status": "PASSED",
  "input_scan_latency_ms": 12.345,
  "output_redacted": true
}
```

---

## Observability

Metrics endpoint:

- `GET /metrics`

Exposed metric families:

- `aegis_requests_total{status,blocked_by}`
- `aegis_rate_limit_exceeded_total`
- `aegis_input_scan_latency_seconds` (histogram)

Prometheus configuration is provided in `prometheus.yml`.

---

## Running tests and benchmarks

This repository’s `tests/` directory currently contains script-style checks/benchmarks (not strict unit tests with assertions in every file).

Examples:

```bash
python tests/test_l1_heuristics_scanner.py
python tests/test_l2_scanner.py
python tests/test_l3_scanner.py
python tests/test_pipeline.py
python tests/test_api_gateway.py
python tests/benchmark_proxy.py
python tests/load_test.py
```

---

## Model training/data pipeline (optional)

If you want to retrain the L2 classifier:

1. Download datasets
2. Preprocess/merge datasets
3. Train + export ONNX
4. (Optional) build semantic signature index in Qdrant

```bash
python scripts/download_datasets.py
python scripts/preprocess_datasets.py
python scripts/train_l2_classifier.py
python scripts/index_l1_cache.py
```

Artifacts expected by runtime are under `models/`.

---

## Troubleshooting

- **`FileNotFoundError` for L2 model/tokenizer**  
  Ensure `models/l2_intent_model/` contains ONNX model + tokenizer.

- **Upstream unreachable / HTTP 502**  
  Verify `UPSTREAM_LLM_URL`, upstream service status, and auth header forwarding.

- **Rate limiting blocks too aggressively**  
  Adjust defaults in `main.py` / `rate_limiter.py`.

- **Redis connection issues**  
  Confirm `REDIS_HOST` points to a reachable Redis instance.

---

## Security notes

- Do not hardcode real credentials in prompts, tests, or config.
- Use `CANARY_TOKENS` to detect accidental internal secret leakage.
- Review scanner regexes and thresholds for your risk profile before production rollout.

---

### Prerequisites
* Docker Desktop & Docker Compose installed
* Local LLM running (e.g., Ollama serving `llama3.2:1b` on port `11434`)
## License

### 1. Start the Proxy Stack
```powershell
docker-compose up -d --build
```

This project is licensed under the terms in [LICENSE](LICENSE).
