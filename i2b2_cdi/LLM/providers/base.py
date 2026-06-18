# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Abstract base class + LLMResponse schema for LLM providers.

Exception translation contract (D-5.7) — every concrete provider MUST
catch SDK-specific exceptions and re-raise as one of:

- ``TimeoutError``   — request exceeded timeout (retryable)
- ``ConnectionError`` — network / 5xx / rate limit (retryable)
- ``RuntimeError``   — wrap unrecoverable load/config failures (NOT retried)
- Configuration errors (4xx, bad input) propagate raw (NOT retried)

The retry helper (``llm_helper.retry_with_backoff``) only retries the first
two classes (plus ``RetryableValidationError`` from semantic validators).
Per-provider mapping is documented in CHANGES.md.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class LLMResponse(BaseModel):
    """Canonical response shape returned by every provider."""

    text: str
    parsed: Optional[Dict[str, Any]] = None
    finish_reason: str = "stop"
    usage: Dict[str, int] = Field(default_factory=lambda: {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    })
    latency_ms: int = 0
    cost_usd: float = 0.0
    raw: Dict[str, Any] = Field(default_factory=dict)


class LLMProvider(ABC):
    """Abstract provider. Subclasses set ``name`` and ``is_external``.

    ``is_external = True`` means a ``generate()`` call sends text out of the
    Docker boundary. Such providers require ``external_provider: true`` opt-in
    in the concept_blob; see ``providers.__init__.get_provider``.
    """

    name: str = ""
    is_external: bool = False

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
        output_schema: Optional[Dict[str, Any]] = None,
        timeout_s: int = 60,
    ) -> LLMResponse:
        """Generate a completion. See exception translation contract above."""

    @abstractmethod
    def health_check(self) -> bool:
        """Cheap, side-effect-free check that the provider is reachable.

        Returns True on success. Should NOT raise — catch and return False.
        """
