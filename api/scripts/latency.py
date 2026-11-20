"""Time the live desk from a client: Continue (preview), Send (ask), and Send → draft ready for a person (in_review).

Runs against the LIVE site, so use it sparingly (Plan 6: once before, once after a change):
- it asks three ordinary questions (one clear, one unclear, one Hinglish) and **no brokerage question**, so the
  demo's "Asked repeatedly: Brokerage & charges" and explainer reuse counts are never touched;
- each question key gets one ask per run, far below the 5-asks threshold of "Asked repeatedly";
- afterwards it rejects its own tickets, so nothing it asked is ever published or left in the Queue.

Times include the network between this machine and Railway. Server-side step times are in the API logs
(`app.desk.timing`: `desk ticket=<id> step=<name> ms=<n>`).

    .venv/Scripts/python scripts/latency.py [--api URL]
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request

DEFAULT_API = "https://api-production-c6d78bb8.up.railway.app"
QUESTIONS = [
    ("clear", "What is the expense ratio of HDFC Mid Cap Fund?"),
    ("unclear", "how much yearly charge for hdfc small cap"),
    ("hinglish", "HDFC Mid Cap Fund ka exit load kitna hai?"),
]


def _call(api: str, path: str, body: dict | None = None):
    req = urllib.request.Request(api + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"content-type": "application/json"},
                                 method="POST" if body is not None else "GET")
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.load(r)
    return out, time.perf_counter() - start


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--api", default=DEFAULT_API)
    api = ap.parse_args().api
    codes = []
    print("| Question | Continue | Send | Send → draft ready |\n|---|---|---|---|")
    try:
        for kind, q in QUESTIONS:
            _, t_prev = _call(api, "/api/ask/preview", {"text": q})
            r, t_ask = _call(api, "/api/ask", {"text": q})
            codes.append(r["code"])
            start = time.perf_counter()
            while _call(api, f"/api/tickets/{r['code']}")[0]["status"] == "received":
                time.sleep(0.25)
            print(f"| {kind} | {t_prev:.2f} s | {t_ask:.2f} s | {time.perf_counter() - start:.2f} s |")
    finally:
        for item in _call(api, "/api/desk/queue")[0]:
            if item["code"] in codes and item["action"] and item["action"]["status"] == "pending":
                _call(api, f"/api/desk/actions/{item['action']['id']}/reject", {})
        print(f"(rejected its tickets: {', '.join(codes)})")


if __name__ == "__main__":
    main()
