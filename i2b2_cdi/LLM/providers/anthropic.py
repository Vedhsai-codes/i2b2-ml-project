# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Anthropic provider (official ``anthropic`` SDK).

Default model: ``claude-sonnet-4-5`` (D-Anthropic-default).
- NOT ``claude-opus-4-7`` (does not exist)
- NOT ``claude-opus-4-5`` (too expensive at MIMIC scale for a default)
- Sonnet handles structured clinical labeling at near-Opus quality, much cheaper per token

Override via ``blob['provider']['model']`` for harder reasoning tasks.

Prompt caching defaults to OFF (D-5.2): caching has a 1024+ token minimum
input length (short prompts silently don't cache) and cache writes cost
1.25x base. For a reference implementation in a research paper, predictable
billing > optimistic optimization. Opt in via ``blob['provider']['cache_prompt']: true``.
Recommended for cohorts > 1000 patients with stable prompt templates.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from loguru import logger

from i2b2_cdi.LLM.providers.base import LLMProvider, LLMResponse

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-5"


class AnthropicProvider(LLMProvider):
    """External provider that calls api.anthropic.com via the official SDK."""

    name = "anthropic"
    is_external = True

    def __init__(
        self,
        model: str = DEFAULT_ANTHROPIC_MODEL,
        api_key: Optional[str] = None,
        cache_prompt: bool = False,
        max_retries: int = 0,
        **_: Any,
    ) -> None:
        self.model = model or DEFAULT_ANTHROPIC_MODEL
        self.cache_prompt = bool(cache_prompt)
        self._api_key = api_key
        self._max_retries = max_retries
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError as e:
                raise RuntimeError(
                    "anthropic SDK not installed. Add 'anthropic' to requirements.txt."
                ) from e
            kwargs: Dict[str, Any] = {"max_retries": self._max_retries}
            if self._api_key:
                kwargs["api_key"] = self._api_key
            self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
        output_schema: Optional[Dict[str, Any]] = None,
        timeout_s: int = 60,
    ) -> LLMResponse:
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError(
                "anthropic SDK not installed. Add 'anthropic' to requirements.txt."
            ) from e
        client = self._get_client()
        system_text = (
            "You are a careful clinical assistant. When asked for structured output, "
            "return the JSON object inside <json>...</json> tags."
        )
        user_content: Any
        if self.cache_prompt:
            user_content = [
                {
                    "type": "text",
                    "text": prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        else:
            user_content = prompt

        start = time.time()
        try:
            resp = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_text,
                messages=[{"role": "user", "content": user_content}],
                timeout=timeout_s,
            )
        except anthropic.APITimeoutError as e:
            raise TimeoutError(f"Anthropic timeout: {e}") from e
        except anthropic.APIConnectionError as e:
            raise ConnectionError(f"Anthropic connection error: {e}") from e
        except anthropic.RateLimitError as e:
            raise ConnectionError(f"Anthropic rate limit (429): {e}") from e
        except anthropic.APIStatusError as e:
            status = getattr(e, "status_code", None)
            if status and 500 <= status < 600:
                raise ConnectionError(f"Anthropic 5xx ({status}): {e}") from e
            raise
        latency_ms = int((time.time() - start) * 1000)

        text_parts = []
        for block in resp.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(getattr(block, "text", ""))
        text = "".join(text_parts)

        usage_obj = getattr(resp, "usage", None)
        usage = {
            "prompt_tokens": getattr(usage_obj, "input_tokens", 0) if usage_obj else 0,
            "completion_tokens": getattr(usage_obj, "output_tokens", 0) if usage_obj else 0,
        }
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]

        return LLMResponse(
            text=text,
            finish_reason=getattr(resp, "stop_reason", "stop") or "stop",
            usage=usage,
            latency_ms=latency_ms,
            cost_usd=0.0,
            raw={"id": getattr(resp, "id", None), "model": getattr(resp, "model", self.model)},
        )

    def health_check(self) -> bool:
        try:
            self._get_client()
            return True
        except Exception as e:
            logger.warning("Anthropic health_check failed: {!r}", e)
            return False
