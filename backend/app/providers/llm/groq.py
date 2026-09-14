"""Groq-backed explanation provider.

Turns already-derived facts into plain language. The prompt hard-constrains
the model: rephrase only, never compute numbers, never invent AWS
events/resources. Any failure falls back to the templated provider so the
system remains usable (Requirement 17.1-17.4).
"""
from __future__ import annotations

import json
import logging

from app.core.config import get_settings
from app.providers.llm.base import Explanation, ExplanationFacts
from app.providers.llm.templated import TemplatedLlmProvider

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a cloud cost assistant. You are given a JSON object of facts that "
    "were already computed by a deterministic system. Write 1-3 short sentences "
    "explaining the cost change in plain, developer-friendly language. "
    "Rules: use ONLY the provided facts. Do NOT compute or change any numbers. "
    "Do NOT invent AWS services, resources, events, or causes. If evidence is "
    "absent, say the cause is unclear. Never claim causality without evidence."
)


class GroqLlmProvider:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._fallback = TemplatedLlmProvider()

    def explain(self, facts: ExplanationFacts) -> Explanation:
        if not self._settings.groq_api_key:
            return self._fallback.explain(facts)
        try:
            from groq import Groq

            client = Groq(api_key=self._settings.groq_api_key)
            payload = {
                "subject": facts.subject,
                "baseline": facts.baseline,
                "observed": facts.observed,
                "difference": facts.difference,
                "classification": facts.classification,
                "confidence": facts.confidence,
                "evidence": facts.evidence,
            }
            resp = client.chat.completions.create(
                model=self._settings.groq_model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, default=str)},
                ],
                temperature=0.2,
                max_tokens=200,
            )
            text = (resp.choices[0].message.content or "").strip()
            if not text:
                return self._fallback.explain(facts)
            return Explanation(text=text, generated_by="ai")
        except Exception:  # noqa: BLE001 - any failure -> deterministic fallback
            logger.exception("groq explanation failed; using template")
            return self._fallback.explain(facts)
