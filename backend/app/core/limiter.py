"""Rate limiting helpers.

- `limiter`: slowapi Limiter, used as a decorator for IP-based limits on
  individual endpoints (e.g. `@limiter.limit("5/minute")`).
- `EmailRateLimiter`: a small in-memory sliding-window limiter for limits
  keyed on email (or any other body-derived key) since slowapi's key_func
  is sync and can't read the request body.

Single-instance only — both pieces live in process memory. If we scale out,
swap in a Redis backend for both.
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta
from threading import Lock
from typing import Deque, Dict

from slowapi import Limiter
from slowapi.util import get_remote_address


limiter = Limiter(key_func=get_remote_address)


class EmailRateLimiter:
    """Sliding-window in-memory limiter, keyed on an arbitrary string."""

    def __init__(self) -> None:
        self._buckets: Dict[str, Deque[datetime]] = defaultdict(deque)
        self._lock = Lock()
        self.enabled = True

    def hit(self, key: str, limit: int, window: timedelta) -> bool:
        """Record a hit. Returns True if allowed, False if rate-limited."""
        if not self.enabled:
            return True
        now = datetime.utcnow()
        cutoff = now - window
        with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True

    def reset(self) -> None:
        """Clear all buckets — used by tests."""
        with self._lock:
            self._buckets.clear()


email_limiter = EmailRateLimiter()
