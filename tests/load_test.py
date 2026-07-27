import asyncio
import time
import httpx

URL = "http://localhost:8000/v1/chat/completions"
TOTAL_REQUESTS = 30
CONCURRENCY = 3  # Adjust based on local Ollama speed

PAYLOAD = {
    "model": "llama3.2:1b",
    "messages": [{"role": "user", "content": "Hello! Give me a 1-sentence joke."}]
}

async def send_request(client, req_id, latencies):
    start = time.perf_counter()
    try:
        response = await client.post(URL, json=PAYLOAD, timeout=60.0)
        elapsed = (time.perf_counter() - start) * 1000
        latencies.append(elapsed)
        print(f"Req {req_id:02d}: Status {response.status_code} | Total Latency: {elapsed:.2f}ms")
    except Exception as e:
        print(f"Req {req_id:02d} failed: {e}")

async def main():
    latencies = []
    sem = asyncio.Semaphore(CONCURRENCY)

    async def bounded_send(client, req_id):
        async with sem:
            await send_request(client, req_id, latencies)

    async with httpx.AsyncClient() as client:
        start_time = time.perf_counter()
        tasks = [bounded_send(client, i) for i in range(1, TOTAL_REQUESTS + 1)]
        await asyncio.gather(*tasks)
        total_time = time.perf_counter() - start_time

    if latencies:
        latencies.sort()
        p50 = latencies[int(len(latencies) * 0.50)]
        p95 = latencies[int(len(latencies) * 0.95)]
        print("\n" + "=" * 40)
        print("     PHASE 7 BENCHMARK RESULTS")
        print("=" * 40)
        print(f"Total Requests: {len(latencies)}")
        print(f"Total Time:     {total_time:.2f}s")
        print(f"Throughput:     {len(latencies) / total_time:.2f} req/sec")
        print(f"p50 Latency:    {p50:.2f}ms")
        print(f"p95 Latency:    {p95:.2f}ms")

if __name__ == "__main__":
    asyncio.run(main())