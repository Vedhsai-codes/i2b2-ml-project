# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""MockProvider — deterministic in-memory provider for tests.

Supports five named fail modes (D-2.8):
- ``schema_invalid``  — returns text that parses but violates the schema
- ``hallucinate``     — returns valid-shape output whose evidence is NOT in the note
- ``empty``           — returns empty text
- ``timeout``         — raises TimeoutError on every call
- ``low_confidence``  — returns valid output with confidence below typical thresholds

Construction-time validation rejects unknown modes.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from i2b2_cdi.LLM.providers.base import LLMProvider, LLMResponse


FAIL_MODES = (
    "schema_invalid",
    "hallucinate",
    "empty",
    "timeout",
    "low_confidence",
)


class MockProvider(LLMProvider):
    """Deterministic provider for tests."""

    name = "mock"
    is_external = False

    def __init__(
        self,
        model: str = "mock-model",
        fail_mode: Optional[str] = None,
        canned_response: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> None:
        if fail_mode is not None and fail_mode not in FAIL_MODES:
            raise ValueError(
                f"MockProvider fail_mode must be one of {FAIL_MODES}, got {fail_mode!r}"
            )
        self.model = model
        self.fail_mode = fail_mode
        self.canned_response = canned_response
        self.call_count = 0
        self.last_prompt: Optional[str] = None

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
        output_schema: Optional[Dict[str, Any]] = None,
        timeout_s: int = 60,
    ) -> LLMResponse:
        self.call_count += 1
        self.last_prompt = prompt

        if self.fail_mode == "timeout":
            raise TimeoutError("MockProvider injected timeout")
        if self.fail_mode == "empty":
            return self._wrap("")
        if self.fail_mode == "schema_invalid":
            return self._wrap('<json>{"label": "not-an-integer", "confidence": 0.9}</json>')
        if self.fail_mode == "hallucinate":
            return self._wrap(
                '<json>{"label": 1, "confidence": 0.95, "evidence": "patient has zzqxk syndrome"}</json>'
            )
        if self.fail_mode == "low_confidence":
            return self._wrap(
                '<json>{"label": 1, "confidence": 0.2, "evidence": "borderline"}</json>'
            )
        if self.canned_response is not None:
            text = f"<json>{json.dumps(self.canned_response)}</json>"
            return self._wrap(text)
        # default deterministic happy-path response — confidence depends on prompt hash
        import hashlib

        h = int(hashlib.md5(prompt.encode("utf-8")).hexdigest()[:8], 16)
        label = h % 2
        conf = 0.75 + (h % 25) / 100.0  # 0.75 .. 0.99
        ev = prompt[:40] if prompt else "note"
        body = json.dumps({"label": label, "confidence": round(conf, 2), "evidence": ev})
        return self._wrap(f"<json>{body}</json>")

    def _wrap(self, text: str) -> LLMResponse:
        return LLMResponse(
            text=text,
            finish_reason="stop",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            latency_ms=1,
            cost_usd=0.0,
            raw={"mock": True},
        )

    def health_check(self) -> bool:
        return True
