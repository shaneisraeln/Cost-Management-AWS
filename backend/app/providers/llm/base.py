"""LLM provider interface and the fact contract passed to it.

The AI layer is strictly downstream of deterministic computation. It receives
only already-derived facts and must not compute numbers or invent AWS
events/resources (Requirement 17, PRD P4/AI-not-source-of-truth).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ExplanationFacts:
    """Deterministic facts the model may rephrase — never extend."""

    subject: str                    # e.g. "EC2 cost anomaly on 2026-09-10"
    baseline: str | None = None
    observed: str | None = None
    difference: str | None = None
    classification: str | None = None
    confidence: float | None = None
    evidence: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class Explanation:
    text: str
    generated_by: str  # "ai" | "template"


@runtime_checkable
class LlmProvider(Protocol):
    def explain(self, facts: ExplanationFacts) -> Explanation: ...
