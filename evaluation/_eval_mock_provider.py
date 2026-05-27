# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Note-aware mock provider for the eval harness.

The plain ``tests.LLM.fixtures.mock_provider.MockProvider`` generates a
deterministic label per prompt-hash, but its synthesized ``evidence``
field is just the first 40 characters of the prompt — and the prompt
includes Jinja-rendered boilerplate, NOT the note text first. So the
hallucination guard's ``require_evidence_substring`` check rejects
every output.

For demonstration runs on synthetic data we want a mock that:
  1. Looks at the rendered prompt for the embedded note text
  2. Heuristically labels HF based on clinical keywords (EF, BNP, HFrEF)
  3. Returns an evidence substring that actually appears in the note

This is **not** intended to replace a real LLM — it's a test double that
lets the eval harness end-to-end produce plausible-looking metrics on
the synthetic cohort. Real eval runs swap in Anthropic, Ollama, etc.

Register via env var: ``LLM_EVAL_MOCK=1`` triggers the registration in
``evaluation.run_demonstration``.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from i2b2_cdi.LLM.providers.base import LLMProvider, LLMResponse


# Phrases that strongly suggest heart failure in a discharge summary.
_HF_PATTERNS = [
    re.compile(r"\bHFrEF\b", re.IGNORECASE),
    re.compile(r"\bHFpEF\b", re.IGNORECASE),
    re.compile(r"\bHFmrEF\b", re.IGNORECASE),
    re.compile(r"\bheart failure\b", re.IGNORECASE),
    re.compile(r"\bsystolic HF\b", re.IGNORECASE),
    re.compile(r"\bdilated\s+(?:cardiomyopathy|CM)\b", re.IGNORECASE),
    re.compile(r"\b(?:non-?ischemic\s+)?cardiomyopathy\b", re.IGNORECASE),
    re.compile(r"\bdecompensated\b", re.IGNORECASE),
    re.compile(r"\bNYHA\s*I{1,4}V?\b", re.IGNORECASE),
    re.compile(r"\bEF\s*(?:of\s*)?(\d{1,2})\s*%", re.IGNORECASE),
    re.compile(r"\bBNP\s*(\d{3,})", re.IGNORECASE),
]


class EvalMockProvider(LLMProvider):
    """Deterministic note-aware HF-label mock for the demonstration eval."""

    name = "mock"
    is_external = False

    def __init__(self, model: str = "eval-mock-v1", **_: Any) -> None:
        self.model = model

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
        output_schema: Optional[Dict[str, Any]] = None,
        timeout_s: int = 60,
    ) -> LLMResponse:
        # Extract the embedded note text. Our cohort_labeling template
        # wraps it in triple-quotes; if not present, fall back to the
        # whole prompt.
        m = re.search(r'"""\s*(.*?)\s*"""', prompt, re.DOTALL)
        note = m.group(1) if m else prompt

        evidence: Optional[str] = None
        label = 0
        confidence = 0.55

        for pat in _HF_PATTERNS:
            m = pat.search(note)
            if m:
                label = 1
                # Quote a verbatim chunk around the match
                start = max(0, m.start() - 5)
                end = min(len(note), m.end() + 25)
                evidence = note[start:end].strip()
                # Higher confidence the more specific the match
                if "EF" in m.group(0).upper() or "BNP" in m.group(0).upper():
                    confidence = 0.92
                elif "HFrEF" in m.group(0) or "HFpEF" in m.group(0) or "HFmrEF" in m.group(0):
                    confidence = 0.95
                else:
                    confidence = 0.85
                break

        if evidence is None:
            # Negative: pick a verbatim short quote from the note as
            # "evidence of no HF". Trim to satisfy the substring guard.
            evidence = note[:60].strip()

        import json as _json

        body = _json.dumps({
            "label": label,
            "confidence": round(confidence, 2),
            "evidence": evidence,
        })
        return LLMResponse(
            text=f"<json>{body}</json>",
            finish_reason="stop",
            usage={"prompt_tokens": 200, "completion_tokens": 30, "total_tokens": 230},
            latency_ms=1,
            cost_usd=0.0,
            raw={"eval_mock": True},
        )

    def health_check(self) -> bool:
        return True
