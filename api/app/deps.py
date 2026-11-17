from __future__ import annotations

from functools import lru_cache

from fastapi import Header, HTTPException

from app.config import get_settings


@lru_cache
def get_retriever():
    from app.corpus.retriever import Retriever
    return Retriever()


def get_themes_provider():
    return lambda db: []


def require_console(x_console_key: str = Header(default="")) -> None:
    if x_console_key != get_settings().console_password:
        raise HTTPException(status_code=401, detail="console key required")
