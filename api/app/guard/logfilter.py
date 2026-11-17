from __future__ import annotations

import logging

from app.guard.pii import redact

_FMT = logging.Formatter()


def _redact_arg(a):
    # Numbers stay numbers so "%d" formats still work; everything else (incl. exceptions) is stringified + redacted.
    if isinstance(a, (int, float)) and not isinstance(a, bool):
        return a
    return redact(a if isinstance(a, str) else str(a)).text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Redact in place and keep args' shape: some formatters (uvicorn access logs) unpack record.args.
        if isinstance(record.msg, str):
            record.msg = redact(record.msg).text
        if isinstance(record.args, tuple):
            record.args = tuple(_redact_arg(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: _redact_arg(v) for k, v in record.args.items()}
        # Tracebacks: Formatter.format() reuses record.exc_text when set, so pre-render it redacted.
        if record.exc_info and not record.exc_text:
            record.exc_text = redact(_FMT.formatException(record.exc_info)).text
        if record.stack_info:
            record.stack_info = redact(record.stack_info).text
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
