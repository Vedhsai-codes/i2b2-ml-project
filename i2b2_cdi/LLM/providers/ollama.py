# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Ollama provider — local model server, stdlib urllib (no SDK dependency).

Default ``base_url`` is ``http://localhost:11434`` per Ollama's documented default.
"""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from loguru import logger

from i2b2_cdi.LLM.providers.base import LLMProvider, LLMResponse


class OllamaProvider(LLMProvider):
    """Local Ollama HTTP server. Marked is_external=False (loopback)."""

    name = "ollama"
    is_external = False

    def __init__(
        self,
        model: str = "llama3",
        base_url: str = "http://localhost:11434",
        **_: Any,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
        output_schema: Optional[Dict[str, Any]] = None,
        timeout_s: int = 60,
    ) -> LLMResponse:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if output_schema is not None:
            payload["format"] = "json"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        start = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                body = resp.read().decode("utf-8")
        except socket.timeout as e:
            raise TimeoutError(f"Ollama timeout: {e}") from e
        except urllib.error.HTTPError as e:
            if 500 <= e.code < 600:
                raise ConnectionError(f"Ollama 5xx ({e.code}): {e}") from e
            raise
        except urllib.error.URLError as e:
            raise ConnectionError(f"Ollama connection error: {e}") from e
        latency_ms = int((time.time() - start) * 1000)
        parsed_body = json.loads(body)
        text = parsed_body.get("response", "")
        usage = {
            "prompt_tokens": parsed_body.get("prompt_eval_count", 0),
            "completion_tokens": parsed_body.get("eval_count", 0),
        }
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
        return LLMResponse(
            text=text,
            finish_reason=parsed_body.get("done_reason", "stop") or "stop",
            usage=usage,
            latency_ms=latency_ms,
            cost_usd=0.0,
            raw={"model": parsed_body.get("model", self.model)},
        )

    def health_check(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception as e:
            logger.warning("Ollama health_check failed: {!r}", e)
            return False
