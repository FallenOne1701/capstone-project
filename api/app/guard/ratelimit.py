"""In-memory sliding-window limits for the public routes: the page is open and every question costs LLM calls.

Single process only (one uvicorn worker), which is how the app is deployed.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.config import get_settings

RATE_MSG = "You've asked a lot of questions quickly — please wait a few minutes."


class RateLimiter:
    def __init__(self, limit: int, window_s: float, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window_s, clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> bool:
        """Record one request for `key`; False when it would exceed the limit (the request is not counted)."""
        now = self.clock()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


def _fresh():
    return (RateLimiter(10, 600), RateLimiter(30, 600), RateLimiter(3, 60), RateLimiter(300, 86_400))


_ask, _preview, _voice, _ask_daily = _fresh()


def reset_limits() -> None:
    global _ask, _preview, _voice, _ask_daily
    _ask, _preview, _voice, _ask_daily = _fresh()


def client_key(request: Request) -> str:
    """Behind a proxy (Railway) every visitor arrives from the proxy's IP: use the forwarded client when trusted."""
    if get_settings().trust_proxy:
        fwd = request.headers.get("x-forwarded-for", "")
        first = fwd.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def _check(limiter: RateLimiter, key: str) -> None:
    if not limiter.hit(key):
        raise HTTPException(429, RATE_MSG)


def limit_ask(request: Request) -> None:
    key = client_key(request)
    _check(_ask, key)
    _check(_ask_daily, "all")


def limit_preview(request: Request) -> None:
    _check(_preview, client_key(request))


def limit_voice(request: Request) -> None:
    _check(_voice, client_key(request))
