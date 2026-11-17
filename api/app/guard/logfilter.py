from __future__ import annotations

import logging

from app.guard.pii import redact


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Redact in place and keep args' shape: some formatters (uvicorn access logs) unpack record.args.
        if isinstance(record.msg, str):
            record.msg = redact(record.msg).text
        if isinstance(record.args, tuple):
            record.args = tuple(redact(a).text if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: redact(v).text if isinstance(v, str) else v for k, v in record.args.items()}
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
