# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Local HuggingFace transformers provider.

Fallback chain (D-5.4):
    1. 4-bit quantized (bitsandbytes)
    2. fp16/bf16 on GPU
    3. fp32 on CPU

Auto-fallback decided by what's importable + ``torch.cuda.is_available()``.
Override flags:
    - ``force_cpu=True``      — skip GPU entirely
    - ``force_no_quant=True`` — GPU yes, but no bitsandbytes (e.g. broken bnb)

Exception translation:
    - ``torch.cuda.OutOfMemoryError`` — RAW (never retry OOM; will reoccur)
    - ``OSError`` during model download — ``ConnectionError`` (retryable)
    - other load failures — wrapped in ``RuntimeError``
    - inference errors other than OOM — propagate raw
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from loguru import logger

from i2b2_cdi.LLM.providers.base import LLMProvider, LLMResponse


class LocalHFProvider(LLMProvider):
    """In-process HuggingFace transformers model. is_external=False."""

    name = "local_hf"
    is_external = False

    def __init__(
        self,
        model: str = "meta-llama/Meta-Llama-3-8B-Instruct",
        force_cpu: bool = False,
        force_no_quant: bool = False,
        device_map: str = "auto",
        **_: Any,
    ) -> None:
        self.model = model
        self.force_cpu = bool(force_cpu)
        self.force_no_quant = bool(force_no_quant)
        self.device_map = device_map
        self._pipeline = None
        self._load_mode: Optional[str] = None

    def _load(self):
        if self._pipeline is not None:
            return self._pipeline
        try:
            import torch
            from transformers import (
                AutoModelForCausalLM,
                AutoTokenizer,
                pipeline,
            )
        except ImportError as e:
            raise RuntimeError(
                "transformers / torch not installed. "
                "pip install 'transformers' 'accelerate' 'torch' for LocalHFProvider."
            ) from e

        use_gpu = (not self.force_cpu) and torch.cuda.is_available()
        try_quant = use_gpu and (not self.force_no_quant)
        load_kwargs: Dict[str, Any] = {}

        if try_quant:
            try:
                import bitsandbytes  # noqa: F401
                from transformers import BitsAndBytesConfig

                load_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.bfloat16,
                )
                load_kwargs["device_map"] = self.device_map
                self._load_mode = "4bit-bnb"
            except ImportError:
                logger.info("bitsandbytes unavailable, falling back to fp16/bf16 GPU.")
                try_quant = False

        if not try_quant and use_gpu:
            load_kwargs["torch_dtype"] = torch.bfloat16
            load_kwargs["device_map"] = self.device_map
            self._load_mode = self._load_mode or "fp16-gpu"
        elif not use_gpu:
            load_kwargs["torch_dtype"] = torch.float32
            self._load_mode = "fp32-cpu"

        try:
            tokenizer = AutoTokenizer.from_pretrained(self.model)
            model_obj = AutoModelForCausalLM.from_pretrained(self.model, **load_kwargs)
        except OSError as e:
            raise ConnectionError(f"HuggingFace download failed: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to load local model {self.model!r}: {e}") from e

        self._pipeline = pipeline(
            "text-generation",
            model=model_obj,
            tokenizer=tokenizer,
            device_map=None if not use_gpu else self.device_map,
        )
        logger.info("LocalHFProvider loaded {} in {} mode", self.model, self._load_mode)
        return self._pipeline

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
        output_schema: Optional[Dict[str, Any]] = None,
        timeout_s: int = 60,
    ) -> LLMResponse:
        pipe = self._load()
        start = time.time()
        gen_kwargs = {
            "max_new_tokens": max_tokens,
            "do_sample": temperature > 0,
            "temperature": max(temperature, 1e-5),
            "return_full_text": False,
        }
        out = pipe(prompt, **gen_kwargs)
        latency_ms = int((time.time() - start) * 1000)
        text = ""
        if isinstance(out, list) and out:
            text = out[0].get("generated_text", "") if isinstance(out[0], dict) else str(out[0])
        usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        return LLMResponse(
            text=text,
            finish_reason="stop",
            usage=usage,
            latency_ms=latency_ms,
            cost_usd=0.0,
            raw={"model": self.model, "load_mode": self._load_mode},
        )

    def health_check(self) -> bool:
        try:
            import torch  # noqa: F401
            import transformers  # noqa: F401

            return True
        except ImportError as e:
            logger.warning("LocalHF health_check failed: {!r}", e)
            return False
