"""In-memory cache and rate limiter."""
import asyncio, hashlib, json, time

_cache = {}
CACHE_TTL = 300

def cache_key(**kw):
    return hashlib.md5(json.dumps(kw, sort_keys=True).encode()).hexdigest()

def cache_get(key):
    if key in _cache:
        ts, data = _cache[key]
        if time.time() - ts < CACHE_TTL: return data
        del _cache[key]
    return None

def cache_set(key, data):
    _cache[key] = (time.time(), data)
    if len(_cache) > 200:
        for k in sorted(_cache, key=lambda k: _cache[k][0])[:50]: del _cache[k]

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
