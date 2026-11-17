from __future__ import annotations

import secrets
from functools import lru_cache

from fastapi import Header, HTTPException

from app.config import get_settings


@lru_cache
def get_retriever():
    from app.corpus.retriever import Retriever
    return Retriever()


def latest_theme_stats(db):
    """Themes of the latest completed weekly run, shaped for the Pattern agent."""
    from datetime import timedelta

    from app.desk.contracts import DateWindow, ThemeStat
    from app.models import Theme, WeeklyRun
    from app.weekly.vocab import CUES, TEAMS
    run = (db.query(WeeklyRun).filter(WeeklyRun.status.in_(("awaiting_approval", "done")))
           .order_by(WeeklyRun.id.desc()).first())
    if run is None:
        return []
    w = DateWindow(start=run.window_start.isoformat(), end=run.window_end.isoformat())
    rw = DateWindow(start=(run.window_end - timedelta(days=6)).isoformat(), end=run.window_end.isoformat())
    return [ThemeStat(theme_id=t.theme_id, name=t.label, team=TEAMS.get(t.theme_id, "General support"),
                      cues=CUES.get(t.theme_id, []), count=t.count, recent_count=t.recent_count, window=w,
                      recent_window=rw)
            for t in db.query(Theme).filter_by(run_id=run.id).order_by(Theme.rank)]


def get_themes_provider():
    return latest_theme_stats


UNSAFE_PASSWORDS = {"", "change-me"}


def require_console(x_console_key: str = Header(default="")) -> None:
    expected = get_settings().console_password
    if expected in UNSAFE_PASSWORDS:
        raise HTTPException(status_code=503, detail="console password not configured")
    if not secrets.compare_digest(x_console_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="console key required")
