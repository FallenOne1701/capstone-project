"""Classify a question once: Continue (preview), Send (ask) and the desk worker share the result for the same text.

In memory, one process (Railway runs one): after a redeploy the cache is empty and the question is simply classified
again, with the same answer. Keyed by the exact redacted text, so a different wording is never given another's intent.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Callable

from app.intent.classifier import IntentResult, classify_intent


class IntentCache:
    def __init__(self, ttl_s: float = 600, max_items: int = 500, clock: Callable[[], float] = time.monotonic) -> None:
        self.ttl, self.max, self.clock = ttl_s, max_items, clock
        self._items: OrderedDict[str, tuple[float, IntentResult]] = OrderedDict()
        self._lock = threading.Lock()   # the desk worker runs in threads

    def get(self, text: str) -> IntentResult | None:
        with self._lock:
            hit = self._items.get(text)
            if hit is None:
                return None
            at, intent = hit
            if self.clock() - at > self.ttl:
                del self._items[text]
                return None
            return intent.model_copy(deep=True)

    def put(self, text: str, intent: IntentResult) -> None:
        with self._lock:
            self._items.pop(text, None)
            self._items[text] = (self.clock(), intent.model_copy(deep=True))
            while len(self._items) > self.max:
                self._items.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


intent_cache = IntentCache()


async def classify_cached(redacted_text: str) -> IntentResult:
    hit = intent_cache.get(redacted_text)
    if hit is not None:
        return hit
    intent = await classify_intent(redacted_text)
    intent_cache.put(redacted_text, intent)
    return intent.model_copy(deep=True)
