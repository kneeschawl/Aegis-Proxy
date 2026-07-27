import time
import redis
from fastapi import HTTPException, Request

class RedisRateLimiter:
    def __init__(self, host: str = "redis", port: int = 6379, max_requests: int = 10, window_seconds: int = 60):
        self.r = redis.Redis(host=host, port=port, db=0, decode_responses=True)
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    def check_rate_limit(self, client_identifier: str):
        current_time = time.time()
        key = f"rate_limit:{client_identifier}"

        # Pipeline operations for speed and atomicity
        pipe = self.r.pipeline()
        # 1. Remove timestamps older than the window
        pipe.zremrangebyscore(key, 0, current_time - self.window_seconds)
        # 2. Count requests remaining in window
        pipe.zcard(key)
        # 3. Add current timestamp
        pipe.zadd(key, {str(current_time): current_time})
        # 4. Set TTL on the key so unused keys expire automatically
        pipe.expire(key, self.window_seconds)
        
        _, request_count, _, _ = pipe.execute()

        if request_count >= self.max_requests:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Allowed maximum of {self.max_requests} requests per {self.window_seconds} seconds."
                },
                headers={"Retry-After": str(self.window_seconds)}
            )