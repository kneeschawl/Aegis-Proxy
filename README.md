# 🛡️ Aegis Security Proxy

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
|---|---|---|
| **Input Scanning Overhead** | `4.5ms – 19.4ms` | Combined L1 + L2 execution latency |
| **Rate Limit Interception** | `11.4ms – 46.6ms` | Blocked requests dropped before upstream call |
| **Default Threshold** | `10 req / 60s` | Fully configurable sliding window per IP |
| **Pipeline Reliability** | `100% Pass Rate` | Sustained concurrent async requests with zero memory leaks |

---

## 🚀 Quick Start Guide

### Prerequisites
* Docker Desktop & Docker Compose installed
* Local LLM running (e.g., Ollama serving `llama3.2:1b` on port `11434`)

### 1. Start the Proxy Stack
```powershell
docker-compose up -d --build