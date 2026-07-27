import os
import re
import json
import time
import httpx
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse, Response
from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from app.core.pipeline import AegisPipeline
from rate_limiter import RedisRateLimiter

app = FastAPI(
    title="Aegis Security Proxy",
    description="Sub-30ms High-Performance Security Gateway for LLM Applications",
    version="1.0.0"
)

# ---------------------------------------------------------
# Configuration & Environment Variables
# ---------------------------------------------------------
UPSTREAM_LLM_URL = os.getenv("UPSTREAM_LLM_URL", "https://api.openai.com/v1/chat/completions")
CANARY_TOKENS = os.getenv("CANARY_TOKENS", "AEGIS_SECRET_CANARY").split(",")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")

# Initialize Rate Limiter & Security Pipeline
rate_limiter = RedisRateLimiter(host=REDIS_HOST, max_requests=10, window_seconds=60)
pipeline = AegisPipeline(
    l2_model_dir="./models/l2_intent_model",
    canary_tokens=CANARY_TOKENS,
    l2_confidence_threshold=0.85
)

# ---------------------------------------------------------
# Prometheus Telemetry Metrics
# ---------------------------------------------------------
REQUEST_COUNT = Counter(
    "aegis_requests_total",
    "Total requests processed by Aegis Proxy",
    ["status", "blocked_by"]
)
RATE_LIMIT_COUNTER = Counter(
    "aegis_rate_limit_exceeded_total",
    "Total requests blocked by rate limiter"
)
SCAN_LATENCY = Histogram(
    "aegis_input_scan_latency_seconds",
    "Latency of Aegis input security scan in seconds",
    buckets=[0.001, 0.005, 0.010, 0.025, 0.050, 0.100, 0.250, 0.500]
)

# ---------------------------------------------------------
# Rate Limiting Middleware (Step 0 Security Check)
# ---------------------------------------------------------
@app.middleware("http")
async def security_pipeline_middleware(request: Request, call_next):
    # Exclude non-proxy system endpoints from rate limiting
    if request.url.path in ["/health", "/metrics", "/docs", "/openapi.json", "/"]:
        return await call_next(request)

    # Extract client IP (or API key header if present)
    client_ip = request.client.host if request.client else "unknown"

    try:
        rate_limiter.check_rate_limit(client_ip)
    except HTTPException as exc:
        RATE_LIMIT_COUNTER.inc()
        # Explicitly return standard 429 JSON payload
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
            headers=exc.headers
        )

    response = await call_next(request)
    return response

# ---------------------------------------------------------
# Helper Functions & Schemas
# ---------------------------------------------------------
def sanitize_output(content: str) -> tuple[str, bool]:
    """Scans response content for canary tokens or exposed API keys/secrets and redacts them."""
    redacted = False
    
    # 1. Redact defined Canary Tokens
    for canary in CANARY_TOKENS:
        if canary and canary in content:
            content = content.replace(canary, "[REDACTED_CANARY_TOKEN]")
            redacted = True

    # 2. Redact potential API keys / secrets
    secret_pattern = r'(sk-[a-zA-Z0-9]{32,}|ghp_[a-zA-Z0-9]{36})'
    if re.search(secret_pattern, content):
        content = re.sub(secret_pattern, "[REDACTED_SECRET_KEY]", content)
        redacted = True

    return content, redacted


class ChatMessage(BaseModel):
    role: str = Field(..., example="user")
    content: str = Field(..., example="Explain quantum computing in standard terms.")

class ChatCompletionRequest(BaseModel):
    model: str = Field(..., example="llama3.2:1b")
    messages: List[ChatMessage]
    temperature: Optional[float] = Field(default=0.7, example=0.7)
    top_p: Optional[float] = Field(default=1.0, example=1.0)
    stream: Optional[bool] = Field(default=False, example=False)

    class Config:
        extra = "allow"

# ---------------------------------------------------------
# Utility Endpoints
# ---------------------------------------------------------
@app.get("/")
async def root():
    return {
        "service": "Aegis Security Proxy Gateway",
        "status": "online",
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics",
        "chat_endpoint": "/v1/chat/completions"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "Aegis Security Proxy"}

@app.get("/metrics")
async def metrics():
    """Prometheus metrics scraping endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

async def stream_upstream_response(upstream_response: httpx.Response, client: httpx.AsyncClient):
    """Generates Server-Sent Events (SSE) while forwarding streaming chunks and ensures client cleanup."""
    try:
        async for chunk in upstream_response.aiter_bytes():
            yield chunk
    finally:
        await client.aclose()

# ---------------------------------------------------------
# Core Proxy Endpoint (/v1/chat/completions)
# ---------------------------------------------------------
@app.post("/v1/chat/completions")
async def proxy_chat_completions(payload: ChatCompletionRequest, raw_request: Request):
    body = payload.model_dump(exclude_unset=True)

    messages = body.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="Missing 'messages' array in request body")

    user_prompt = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_prompt = msg.get("content", "")
            break

    # 1. RUN INPUT SECURITY SCAN (L1 + L2)
    start_time = time.perf_counter()
    scan_res = pipeline.scan_input(user_prompt)
    scan_duration = time.perf_counter() - start_time
    SCAN_LATENCY.observe(scan_duration)

    if scan_res["action"] == "BLOCK":
        REQUEST_COUNT.labels(status="blocked", blocked_by=scan_res["blocked_by"]).inc()
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "message": "Security Violation: Request blocked by Aegis Proxy.",
                    "type": "security_blocked",
                    "code": scan_res["blocked_by"],
                    "reason": scan_res["reason"],
                    "telemetry": {
                        "l1_latency_ms": round(scan_res["l1_latency_ms"], 3),
                        "l2_latency_ms": round(scan_res["l2_latency_ms"], 3),
                        "total_latency_ms": round(scan_res["total_latency_ms"], 3)
                    }
                }
            }
        )

    REQUEST_COUNT.labels(status="passed", blocked_by="none").inc()

    # 2. FORWARD CLEAN REQUEST TO UPSTREAM LLM
    headers = {k: v for k, v in raw_request.headers.items() if k.lower() in ["authorization", "content-type"]}
    is_streaming = body.get("stream", False)

    client = httpx.AsyncClient(timeout=60.0)

    if is_streaming:
        try:
            req = client.build_request("POST", UPSTREAM_LLM_URL, json=body, headers=headers)
            upstream_response = await client.send(req, stream=True)
            return StreamingResponse(
                stream_upstream_response(upstream_response, client),
                status_code=upstream_response.status_code,
                media_type="text/event-stream"
            )
        except Exception as e:
            await client.aclose()
            raise HTTPException(status_code=502, detail=f"Upstream LLM Provider unreachable: {str(e)}")
    else:
        try:
            upstream_response = await client.post(UPSTREAM_LLM_URL, json=body, headers=headers)
            upstream_data = upstream_response.json()
            await client.aclose()
        except Exception as e:
            await client.aclose()
            raise HTTPException(status_code=502, detail=f"Upstream LLM Provider unreachable: {str(e)}")

        # 3. RUN OUTPUT SECURITY SCAN (L3 Output Redaction & Secret Guardrail)
        was_redacted = False
        if "choices" in upstream_data and len(upstream_data["choices"]) > 0:
            choice = upstream_data["choices"][0]
            if "message" in choice and "content" in choice["message"]:
                original_content = choice["message"]["content"]
                
                if hasattr(pipeline, "scan_output"):
                    l3_res = pipeline.scan_output(original_content, redact=True)
                    original_content = l3_res.get("sanitized_text", original_content)
                
                sanitized_content, was_redacted = sanitize_output(original_content)
                choice["message"]["content"] = sanitized_content

        # Attach Telemetry Summary
        upstream_data["_aegis_telemetry"] = {
            "status": "PASSED",
            "input_scan_latency_ms": round(scan_res["total_latency_ms"], 3),
            "output_redacted": was_redacted
        }

        return JSONResponse(content=upstream_data, status_code=upstream_response.status_code)