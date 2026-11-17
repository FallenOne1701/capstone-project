from __future__ import annotations

from datetime import date, timedelta

from app.desk.contracts import DateWindow, PatternResult, ThemeStat

DEFAULT_TEAM = "General support"


def _signal(t: ThemeStat) -> str:
    if t.count < 20:
        return "one-off"
    start, end = date.fromisoformat(t.window.start), date.fromisoformat(t.window.end)
    weeks = max(1, ((end - start).days + 1) // 7)
    earlier_weekly = (t.count - t.recent_count) / max(1, weeks - 1)
    return "rising" if t.recent_count >= 2 * earlier_weekly else "recurring"


def run_pattern(redacted_text: str, themes: list[ThemeStat], *, today: date) -> PatternResult:
    low = redacted_text.lower()
    scored = [(sum(c in low for c in t.cues), t.count, t) for t in themes]
    scored = [s for s in scored if s[0] > 0]
    if not scored:
        w = DateWindow(start=(today - timedelta(days=6)).isoformat(), end=today.isoformat())
        return PatternResult(theme_id="other", theme_name="Other", signal="one-off", count=0,
                             recent_count=0, window=w, recent_window=w)
    t = max(scored, key=lambda s: (s[0], s[1]))[2]
    return PatternResult(theme_id=t.theme_id, theme_name=t.name, signal=_signal(t), count=t.count,
                         recent_count=t.recent_count, window=t.window, recent_window=t.recent_window)


def team_for(theme_id: str, themes: list[ThemeStat]) -> str:
    return next((t.team for t in themes if t.theme_id == theme_id), DEFAULT_TEAM)
