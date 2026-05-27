# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Shared helpers for the LLM module.

Public surface:
- ``render_prompt(template_name, variables)``: Jinja2 template render
- ``chunk_notes(text, max_tokens, tokenizer=None)``: text chunker with token-or-char proxy
- ``retry_with_backoff(fn, ...)``: narrow-contract exponential backoff
- ``compute_prompt_hash(prompt)``: sha256 of the rendered prompt
- ``RetryableValidationError``: raised by validators/guardrails to signal "retry me"

The retry tuple is intentionally narrow: providers translate SDK-specific
exceptions to ``(TimeoutError, ConnectionError)`` (see providers/base.py
contract). Configuration mistakes (``PermissionError``, ``ValueError``,
``KeyError``) are NOT retried — retrying won't fix them.
"""
from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple, Type

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound
from loguru import logger


PROMPTS_DIR = Path(__file__).parent / "prompts"

_jinja_env = Environment(
    loader=FileSystemLoader(str(PROMPTS_DIR)),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    autoescape=False,
)


class RetryableValidationError(Exception):
    """Signals a semantic failure (schema/guardrail) that should retry.

    Lives in ``llm_helper`` (not ``apply_LLM``) so any future caller of
    ``retry_with_backoff`` can signal "retry me for semantic reasons".
    """


def render_prompt(template_name: str, variables: dict) -> str:
    """Render a Jinja2 prompt template from ``prompts/`` by stem.

    ``template_name`` may be ``"cohort_labeling"`` or ``"cohort_labeling.txt"``.
    Variables marked with StrictUndefined: missing variables raise rather than
    silently rendering empty strings.
    """
    name = template_name if template_name.endswith(".txt") else f"{template_name}.txt"
    try:
        template = _jinja_env.get_template(name)
    except TemplateNotFound as e:
        available = sorted(p.name for p in PROMPTS_DIR.glob("*.txt"))
        raise FileNotFoundError(
            f"Prompt template {name!r} not found in {PROMPTS_DIR}. Available: {available}"
        ) from e
    return template.render(**(variables or {}))


def compute_prompt_hash(prompt: str) -> str:
    """SHA-256 hex digest of the rendered prompt string."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _approx_tokens(text: str, tokenizer=None) -> int:
    """Token count via tokenizer if given, else 4-chars-per-token proxy."""
    if tokenizer is not None:
        try:
            return len(tokenizer.encode(text))
        except Exception:
            pass
    return max(1, len(text) // 4)


def _split_sentences(text: str) -> List[str]:
    """Naive sentence splitter (period/newline/exclamation/question)."""
    import re

    parts = re.split(r"(?<=[\.\!\?])\s+|\n+", text)
    return [p.strip() for p in parts if p and p.strip()]


def chunk_notes(text: str, max_tokens: int, tokenizer=None) -> List[str]:
    """Chunk ``text`` into pieces under ``max_tokens`` each.

    Strategy:
        - Split on sentence boundaries first.
        - Greedily fill chunks up to max_tokens (approx).
        - If a single sentence exceeds max_tokens, hard-cut at char boundary.
        - Empty text returns ``[]``.

    Uses 4-chars-per-token proxy if no tokenizer is provided (GPT-3-era heuristic,
    conservative for clinical text).
    """
    if not text or not text.strip():
        return []
    if max_tokens <= 0:
        raise ValueError(f"max_tokens must be > 0, got {max_tokens}")

    char_budget = max_tokens * 4 if tokenizer is None else None
    sentences = _split_sentences(text)
    chunks: List[str] = []
    buf: List[str] = []
    buf_tokens = 0

    def flush() -> None:
        nonlocal buf, buf_tokens
        if buf:
            chunks.append(" ".join(buf))
        buf, buf_tokens = [], 0

    for sent in sentences:
        s_tokens = _approx_tokens(sent, tokenizer)
        if s_tokens > max_tokens:
            flush()
            step = char_budget or (max_tokens * 4)
            for i in range(0, len(sent), step):
                chunks.append(sent[i : i + step])
            continue
        if buf_tokens + s_tokens > max_tokens:
            flush()
        buf.append(sent)
        buf_tokens += s_tokens
    flush()
    return chunks


def retry_with_backoff(
    fn: Callable,
    *,
    max_retries: int = 2,
    base_delay_s: float = 1.0,
    max_delay_s: float = 30.0,
    exceptions: Tuple[Type[BaseException], ...] = (
        TimeoutError,
        ConnectionError,
        RetryableValidationError,
    ),
    sleep: Callable[[float], None] = time.sleep,
) -> any:
    """Call ``fn()`` with exponential backoff, retrying only on ``exceptions``.

    Args:
        fn: zero-arg callable. Wrap arguments with functools.partial or closure.
        max_retries: number of retries *after* the initial attempt. Total
            attempts = max_retries + 1.
        base_delay_s: initial backoff in seconds. ``0`` disables sleep (tests).
        max_delay_s: ceiling for backoff.
        exceptions: which exceptions are retryable. Anything else propagates immediately.
        sleep: injectable for tests.

    Returns:
        Whatever ``fn()`` returns on success.

    Raises:
        The last raised retryable exception after exhausting retries, or any
        non-retryable exception immediately.
    """
    if max_retries < 0:
        raise ValueError(f"max_retries must be >= 0, got {max_retries}")
    attempt = 0
    last_exc: Optional[BaseException] = None
    while True:
        try:
            return fn()
        except exceptions as e:
            last_exc = e
            if attempt >= max_retries:
                logger.warning(
                    "retry_with_backoff exhausted after {} attempts: {!r}",
                    attempt + 1,
                    e,
                )
                raise
            delay = min(max_delay_s, base_delay_s * (2 ** attempt))
            logger.info(
                "retry_with_backoff attempt {}/{} failed ({!r}), sleeping {}s",
                attempt + 1,
                max_retries + 1,
                e,
                delay,
            )
            if delay > 0:
                sleep(delay)
            attempt += 1
