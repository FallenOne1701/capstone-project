import logging

from app.guard.logfilter import RedactingFilter, install_log_redaction


def test_filter_redacts_message_and_args(caplog):
    logger = logging.getLogger("t.redact")
    logger.addFilter(RedactingFilter())
    with caplog.at_level(logging.INFO, logger="t.redact"):
        logger.info("user said %s", "my pan is ABCDE1234F and phone 9876543210")
    text = caplog.text
    assert "ABCDE1234F" not in text and "9876543210" not in text
    assert "[PAN]" in text and "[PHONE]" in text


def test_filter_keeps_args_shape_for_formatters_that_read_them():
    # uvicorn's AccessFormatter unpacks record.args (5-tuple); emptying args breaks every access log line.
    rec = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                            ("127.0.0.1:1", "GET", "/api/tickets?phone=9876543210", "1.1", 200), None)
    RedactingFilter().filter(rec)
    assert isinstance(rec.args, tuple) and len(rec.args) == 5
    assert rec.args[4] == 200
    assert "9876543210" not in rec.getMessage() and "[PHONE]" in rec.getMessage()


def test_install_is_idempotent():
    install_log_redaction()
    install_log_redaction()
    root = logging.getLogger()
    n = sum(isinstance(f, RedactingFilter) for h in root.handlers for f in h.filters)
    assert n <= len(root.handlers)
