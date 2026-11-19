"""README samples: a redacted reviews CSV and sample Q&As picked from an eval run's passed cases."""

from __future__ import annotations

import csv
import io

from app.guard.pii import redact

CSV_COLUMNS = ["review_id", "date", "rating", "text_redacted", "app_version"]


def reviews_csv(rows: list[dict]) -> str:
    """rows: dicts with id, date, rating, text_redacted, app_version. Text is redacted again, defensively."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_COLUMNS)
    for r in rows:
        w.writerow([r.get("id", ""), str(r.get("date", "")), r.get("rating", ""),
                    redact(str(r.get("text_redacted") or "")).text, r.get("app_version") or ""])
    return buf.getvalue()


def pick_qas(result_json: dict, n: int = 5) -> list[dict]:
    """Passed cases with a reply, one per intent (first seen wins), in run order."""
    out, seen = [], set()
    for suite in result_json.get("suites", []):
        for c in suite.get("cases", []):
            d = c.get("data") or {}
            if not c.get("passed") or not d.get("reply") or not d.get("question") or d.get("intent") in seen:
                continue
            if d.get("expect") not in ("answer", "refuse"):
                continue
            seen.add(d.get("intent"))
            out.append({"question": d["question"], "answer": d["reply"], "source": d.get("citation"),
                        "last_checked": d.get("last_checked"), "kind": d.get("expect")})
            if len(out) == n:
                return out
    return out
