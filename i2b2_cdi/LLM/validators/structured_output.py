# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""JSON-schema validator for structured LLM output.

``coerce_text_to_dict`` resolution order (D-4.5 + Step-5 correction):
    1. whole text already parses as a dict
    2. ``<json>...</json>`` XML-tagged block (Claude convention)
    3. ```json ... ``` markdown fence
    4. widest top-level ``{ ... }`` brace block
    5. None (conservative — refuse to invent)

Top-level JSON arrays return None — they have a different shape than the
``object`` schema this validator expects.

``SchemaValidator.__init__`` calls ``Draft7Validator.check_schema(schema)`` so
that a malformed ``output_schema`` fails at concept-build time (in
``perform_LLM.build_llm_concept``) instead of silently at 2 AM on Discovery.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional, Tuple

import jsonschema
from jsonschema import Draft7Validator


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)
_XML_RE = re.compile(r"<json>\s*([\s\S]*?)\s*</json>", re.IGNORECASE)


def _try_parse(s: str) -> Optional[Dict[str, Any]]:
    try:
        obj = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def _widest_brace_block(text: str) -> Optional[str]:
    """Return the widest top-level ``{...}`` substring, or None."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def coerce_text_to_dict(text: str) -> Optional[Dict[str, Any]]:
    """Extract a JSON object dict from arbitrary LLM text. None if uncertain."""
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None

    direct = _try_parse(text)
    if direct is not None:
        return direct

    m = _XML_RE.search(text)
    if m:
        candidate = _try_parse(m.group(1).strip())
        if candidate is not None:
            return candidate

    m = _FENCE_RE.search(text)
    if m:
        candidate = _try_parse(m.group(1).strip())
        if candidate is not None:
            return candidate

    block = _widest_brace_block(text)
    if block:
        candidate = _try_parse(block)
        if candidate is not None:
            return candidate

    return None


class SchemaValidator:
    """Wraps a JSON-schema dict; validates parsed LLM outputs against it.

    Calls ``Draft7Validator.check_schema`` at construction — bad schemas fail
    at concept-build time, not silently at first job execution.
    """

    def __init__(self, schema: Optional[Dict[str, Any]]) -> None:
        if schema is None:
            self.schema = None
            self._validator = None
            return
        if not isinstance(schema, dict):
            raise TypeError(f"output_schema must be a dict, got {type(schema).__name__}")
        try:
            Draft7Validator.check_schema(schema)
        except jsonschema.SchemaError as e:
            raise ValueError(f"Invalid JSON schema for output_schema: {e.message}") from e
        self.schema = schema
        self._validator = Draft7Validator(schema)

    def validate(self, value: Any) -> Tuple[bool, Optional[str]]:
        """Return (ok, error_message_or_None). Off-schema if no schema given is OK."""
        if self._validator is None:
            return True, None
        errors = sorted(self._validator.iter_errors(value), key=lambda e: list(e.path))
        if not errors:
            return True, None
        msg = "; ".join(f"{list(e.path) or '<root>'}: {e.message}" for e in errors[:3])
        return False, msg
