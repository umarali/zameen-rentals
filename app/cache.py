"""Cache (backed by SQLite) and rate limiter."""
import asyncio, hashlib, json, time

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database import db_cache_get, db_cache_set

limiter = Limiter(key_func=get_remote_address)

CACHE_TTL = 300

def cache_key(**kw):
    return hashlib.md5(json.dumps(kw, sort_keys=True).encode()).hexdigest()

def cache_get(key):
    return db_cache_get(key)

def cache_set(key, data):
    db_cache_set(key, data)

class RateLimiter:
    def __init__(self, rate=2.0, burst=3, min_rate=0.3):
        self.rate = rate
        self.target_rate = rate
        self.burst = burst
        self.min_rate = min_rate
        self.tokens = float(burst)
        self.last = time.monotonic()
        self.consecutive_429s = 0
        self._lock = asyncio.Lock()

    async def acquire(self):
        while True:
            async with self._lock:
                now = time.monotonic()
                rate = max(float(self.rate), 0.001)
                self.tokens = min(self.burst, self.tokens + (now - self.last) * rate)
                self.last = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                wait = (1 - self.tokens) / rate
            await asyncio.sleep(wait)

    def record_success(self):
        self.consecutive_429s = max(0, self.consecutive_429s - 1)
        if self.consecutive_429s == 0 and self.rate < self.target_rate:
            self.rate = min(self.target_rate, max(self.rate * 1.1, self.rate + 0.05))
        return self.consecutive_429s

    def record_429(self):
        self.consecutive_429s += 1
        slowed = False
        if self.consecutive_429s >= 3:
            adaptive_floor = min(self.min_rate, self.target_rate)
            self.rate = max(adaptive_floor, self.rate * 0.7)
            slowed = True
        return self.consecutive_429s, slowed

    def set_target_rate(self, rate):
        self.target_rate = max(float(rate), 0.001)
        self.rate = min(self.rate, self.target_rate)

    def reset(self, rate=None):
        if rate is not None:
            self.target_rate = max(float(rate), 0.001)
        self.rate = self.target_rate
        self.consecutive_429s = 0

rate_limiter = RateLimiter()
