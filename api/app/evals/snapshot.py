"""Whole-database snapshots for the edit-isolation eval: every table, every row, keyed by primary key."""

from __future__ import annotations

from sqlalchemy import select

from app.db import Base


def snapshot(db) -> dict[str, dict]:
    from app import models  # noqa: F401  (register every table)
    db.expire_all()
    out: dict[str, dict] = {}
    for table in Base.metadata.sorted_tables:
        pk = [c.name for c in table.primary_key.columns]
        rows = {}
        for r in db.execute(select(table)).mappings():
            key = r[pk[0]] if len(pk) == 1 else tuple(r[k] for k in pk)
            rows[key] = dict(r)
        out[table.name] = rows
    return out


def diff(a: dict, b: dict) -> dict[str, list]:
    """table -> keys of rows added, removed or changed between two snapshots (tables with no change omitted)."""
    out = {}
    for table in set(a) | set(b):
        ra, rb = a.get(table, {}), b.get(table, {})
        changed = sorted((k for k in set(ra) | set(rb) if ra.get(k) != rb.get(k)), key=str)
        if changed:
            out[table] = changed
    return out
