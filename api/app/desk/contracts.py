"""Agent desk contracts (ported from M3; scheme/theme ids widened to str for the 15-scheme corpus)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

SchemeId = str
ThemeId = str
PatternSignal = Literal["one-off", "recurring", "rising"]
Disposition = Literal["reply", "escalate", "handoff", "refuse", "disagree", "account"]
ReviewStatus = Literal["pass", "fail", "blocked"]
ReviewCheck = Literal["citation", "advice", "performance", "pii", "shape"]
Priority = Literal["P1", "P2", "P3"]
PiiType = str


class DateWindow(BaseModel):
    start: str
    end: str


class FactsResult(BaseModel):
    status: Literal["covered", "not_covered"]
    scheme_id: SchemeId | None = None
    section_title: str | None = None
    fact: str | None = None
    citation: str | None = None
    last_checked: str | None = None
    searched: list[str]

    @model_validator(mode="after")
    def _covered_requires_citation(self) -> "FactsResult":
        if self.status == "covered":
            if not self.fact or not self.citation or not self.last_checked or not self.scheme_id:
                raise ValueError("covered FactsResult requires fact, citation, last_checked, scheme_id")
        if self.status == "not_covered":
            if self.fact is not None or self.citation is not None:
                raise ValueError("not_covered FactsResult must null fact and citation")
        return self


class PatternResult(BaseModel):
    theme_id: ThemeId
    theme_name: str
    signal: PatternSignal
    count: int
    recent_count: int
    window: DateWindow
    recent_window: DateWindow


class ComplianceResult(BaseModel):
    flags: list[Literal["advice", "performance_claim", "pii"]]
    pii_types: list[PiiType]
    advice_refusal: bool
    redacted_text: str


class RoutingNote(BaseModel):
    team: str
    priority: Priority
    why: str


class OrchestratorOutput(BaseModel):
    reply: str
    last_checked: str | None
    citation: str | None
    disposition: Disposition
    disagreement: bool
    routing_note: RoutingNote


class ReviewerFailure(BaseModel):
    check: ReviewCheck
    detail: str


class ReviewerResult(BaseModel):
    status: ReviewStatus
    round: int = Field(ge=1, le=2)
    failures: list[ReviewerFailure] = Field(default_factory=list)


class ThemeStat(BaseModel):
    """Weekly-loop theme snapshot consumed by the Pattern agent (populated in Plan 2)."""
    theme_id: str
    name: str
    team: str
    cues: list[str]
    count: int
    recent_count: int
    window: DateWindow
    recent_window: DateWindow
