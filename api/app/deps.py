from __future__ import annotations

import secrets
from functools import lru_cache

from fastapi import Header, HTTPException

from app.config import get_settings


@lru_cache
def get_retriever():
    from app.corpus.retriever import Retriever
    return Retriever()


def get_themes_provider():
    return lambda db: []


UNSAFE_PASSWORDS = {"", "change-me"}


def require_console(x_console_key: str = Header(default="")) -> None:
    expected = get_settings().console_password
    if expected in UNSAFE_PASSWORDS:
        raise HTTPException(status_code=503, detail="console password not configured")
    if not secrets.compare_digest(x_console_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="console key required")
