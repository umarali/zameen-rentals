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
    def __init__(self, rate=2.0, burst=3):
        self.rate, self.burst, self.tokens, self.last = rate, burst, float(burst), time.monotonic()
        self._lock = asyncio.Lock()
    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            self.tokens = min(self.burst, self.tokens + (now - self.last) * self.rate)
            self.last = now
            if self.tokens < 1:
                await asyncio.sleep((1 - self.tokens) / self.rate)
                self.tokens = 0
            else: self.tokens -= 1

rate_limiter = RateLimiter()
