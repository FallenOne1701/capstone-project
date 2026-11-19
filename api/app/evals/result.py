"""Eval results: one CaseResult per checked case, grouped by suite, saved as a numbered JSON file per run."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

_RUN = re.compile(r"^run-(\d+)-")


@dataclass
class CaseResult:
    suite: str
    case_id: str
    passed: bool
    detail: str = ""
    data: dict = field(default_factory=dict)


@dataclass
class SuiteResult:
    name: str
    cases: list[CaseResult]

    @property
    def passed(self) -> int:
        return sum(c.passed for c in self.cases)

    @property
    def total(self) -> int:
        return len(self.cases)


def next_result_path(results_dir: Path, today: date) -> Path:
    """`run-<n>-<date>.json`, n one above the highest existing run, so no earlier run is ever overwritten."""
    nums = [int(m.group(1)) for p in (results_dir.glob("run-*.json") if results_dir.exists() else [])
            if (m := _RUN.match(p.name))]
    return results_dir / f"run-{max(nums, default=0) + 1}-{today.isoformat()}.json"


def write_result(results_dir: Path, suites: list[SuiteResult], *, today: date, meta: dict) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    path = next_result_path(results_dir, today)
    body = {"meta": meta, "suites": [
        {"name": s.name, "passed": s.passed, "total": s.total, "cases": [asdict(c) for c in s.cases]}
        for s in suites]}
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def score_card(suites: list[SuiteResult]) -> str:
    lines = [f"{s.name}  {s.passed}/{s.total}" for s in suites]
    for s in suites:
        for c in s.cases:
            if not c.passed:
                lines.append(f"  FAIL {s.name}/{c.case_id}: {c.detail}")
    return "\n".join(lines)
