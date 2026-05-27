# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""OpenAI-compatible provider (official ``openai`` SDK with custom ``base_url``).

Works against OpenAI, Azure OpenAI, self-hosted vLLM, LM Studio, etc.
Requires both ``base_url`` and ``model`` at construction; fails fast at
concept-build with a clear error rather than at first-job-run with an SDK error.

``api_key`` defaults to the literal string ``"not-needed"`` — self-hosted vLLM
/ LM Studio convention. This is a foot-gun for real OpenAI/Azure: those
endpoints will return 401. Operator should set a real key for real services.
A future hardening pass should detect requires-real-key hosts and reject the
default (banked in CHANGES.md).
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from loguru import logger

from i2b2_cdi.LLM.providers.base import LLMProvider, LLMResponse


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI-API-shaped provider with a configurable base_url.

    is_external is True by default. Self-hosted operators can register a
    LOCAL-flagged subclass via ``register_provider`` if their base_url stays
    inside the Docker network.
    """

    name = "openai_compatible"
    is_external = True

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: str = "not-needed",
        **_: Any,
    ) -> None:
        if not base_url:
            raise ValueError(
                "OpenAICompatibleProvider requires 'base_url' in provider config."
            )
        if not model:
            raise ValueError(
                "OpenAICompatibleProvider requires 'model' in provider config."
            )
        self.base_url = base_url
        self.model = model
        self._api_key = api_key or "not-needed"
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import openai
            except ImportError as e:
                raise RuntimeError(
                    "openai SDK not installed. Add 'openai' to requirements.txt."
                ) from e
            self._client = openai.OpenAI(api_key=self._api_key, base_url=self.base_url)
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
            import openai
        except ImportError as e:
            raise RuntimeError("openai SDK not installed.") from e
        client = self._get_client()
        start = time.time()
        try:
            resp = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout_s,
            )
        except openai.APITimeoutError as e:
            raise TimeoutError(f"OpenAI-compat timeout: {e}") from e
        except openai.APIConnectionError as e:
            raise ConnectionError(f"OpenAI-compat connection error: {e}") from e
        except openai.RateLimitError as e:
            raise ConnectionError(f"OpenAI-compat rate limit: {e}") from e
        except openai.APIStatusError as e:
            status = getattr(e, "status_code", None)
            if status and 500 <= status < 600:
                raise ConnectionError(f"OpenAI-compat 5xx ({status}): {e}") from e
            raise
        latency_ms = int((time.time() - start) * 1000)

        choice = resp.choices[0]
        text = choice.message.content or ""
        finish = choice.finish_reason or "stop"
        usage_obj = getattr(resp, "usage", None)
        usage = {
            "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0) if usage_obj else 0,
            "completion_tokens": getattr(usage_obj, "completion_tokens", 0) if usage_obj else 0,
            "total_tokens": getattr(usage_obj, "total_tokens", 0) if usage_obj else 0,
        }
        return LLMResponse(
            text=text,
            finish_reason=finish,
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
            logger.warning("OpenAI-compat health_check failed: {!r}", e)
            return False
