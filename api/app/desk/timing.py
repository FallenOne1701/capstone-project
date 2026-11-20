"""How long each desk step takes, per ticket. Step names, durations and the ticket id only: never question text or PII."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator

log = logging.getLogger("app.desk.timing")


@contextmanager
def step(name: str, ticket_id: int) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        log.info("desk ticket=%d step=%s ms=%d", ticket_id, name, round((time.perf_counter() - start) * 1000))
