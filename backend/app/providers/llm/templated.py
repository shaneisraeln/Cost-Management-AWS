"""Deterministic templated explanation.

Used as a fallback when Groq is unavailable or unconfigured, and always
available so the system never depends on the LLM for a usable answer.
"""
from __future__ import annotations

from app.providers.llm.base import Explanation, ExplanationFacts


class TemplatedLlmProvider:
    def explain(self, facts: ExplanationFacts) -> Explanation:
        parts = [facts.subject + "."]
        if facts.baseline is not None and facts.observed is not None:
            parts.append(
                f"Observed spend was {facts.observed} against a baseline of "
                f"{facts.baseline}"
                + (f" (a change of {facts.difference})." if facts.difference else ".")
            )
        if facts.classification:
            parts.append(f"Classified as {facts.classification}.")
        creation = [
            e for e in facts.evidence if e.get("type") in ("correlated_events",)
        ]
        if creation:
            parts.append("Correlated activity was found around this time (see evidence).")
        else:
            parts.append("No correlated activity was found for this change.")
        if facts.confidence is not None:
            parts.append(f"Confidence: {int(facts.confidence * 100)}%.")
        return Explanation(text=" ".join(parts), generated_by="template")
