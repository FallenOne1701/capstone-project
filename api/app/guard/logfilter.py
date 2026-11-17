from __future__ import annotations

import logging

from app.guard.pii import redact


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        record.msg = redact(msg).text
        record.args = ()
        return True


def install_log_redaction() -> None:
    logging.basicConfig(level=logging.INFO)
    targets = [logging.getLogger()] + [logging.getLogger(n) for n in ("uvicorn", "uvicorn.access", "uvicorn.error")]
    for lg in targets:
        if not any(isinstance(f, RedactingFilter) for f in lg.filters):
            lg.addFilter(RedactingFilter())
        for h in lg.handlers:
            if not any(isinstance(f, RedactingFilter) for f in h.filters):
                h.addFilter(RedactingFilter())
