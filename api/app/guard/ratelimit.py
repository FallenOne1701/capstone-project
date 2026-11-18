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
DESK_MSG = "Too many clicks in a short time — please wait a few minutes."
WEEKLY_MSG = "The weekly pulse was run in the last hour — please try again later."


class RateLimiter:
    def __init__(self, limit: int, window_s: float, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window_s, clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._swept = clock()

    def hit(self, key: str) -> bool:
        """Record one request for `key`; False when it would exceed the limit (the request is not counted)."""
        now = self.clock()
        with self._lock:
            if now - self._swept >= min(self.window, 60):   # forget idle clients so memory can't grow forever
                self._hits = defaultdict(deque, {k: q for k, q in self._hits.items() if q and now - q[-1] < self.window})
                self._swept = now
            q = self._hits[key]
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


def _fresh():
    return (RateLimiter(10, 600), RateLimiter(30, 600), RateLimiter(3, 60),
            RateLimiter(300, 86_400), RateLimiter(900, 86_400), RateLimiter(150, 86_400),
            RateLimiter(30, 600), RateLimiter(1, 3600))


_ask, _preview, _voice, _ask_daily, _preview_daily, _voice_daily, _desk, _weekly = _fresh()


def reset_limits() -> None:
    global _ask, _preview, _voice, _ask_daily, _preview_daily, _voice_daily, _desk, _weekly
    _ask, _preview, _voice, _ask_daily, _preview_daily, _voice_daily, _desk, _weekly = _fresh()


def client_key(request: Request) -> str:
    """Behind a proxy (Railway) every visitor arrives from the proxy's IP. The proxy APPENDS the real client to
    X-Forwarded-For, so trust only the last hop — earlier hops are whatever the client chose to send."""
    if get_settings().trust_proxy:
        hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
        if hops:
            return hops[-1]
    return request.client.host if request.client else "unknown"


def _check(limiter: RateLimiter, key: str, msg: str = RATE_MSG) -> None:
    if not limiter.hit(key):
        raise HTTPException(429, msg)


def limit_ask(request: Request) -> None:
    key = client_key(request)
    _check(_ask, key)
    _check(_ask_daily, "all")


def limit_preview(request: Request) -> None:
    _check(_preview, client_key(request))
    _check(_preview_daily, "all")


def limit_voice(request: Request) -> None:
    _check(_voice, client_key(request))
    _check(_voice_daily, "all")


def limit_desk(request: Request) -> None:
    """The page's approve / edit / reject / retry / re-run clicks: open to anyone, so capped per visitor."""
    _check(_desk, client_key(request), DESK_MSG)


def limit_weekly_run(request: Request) -> None:
    """One weekly run an hour for everyone: each run fetches reviews and makes LLM calls."""
    _check(_weekly, "all", WEEKLY_MSG)
