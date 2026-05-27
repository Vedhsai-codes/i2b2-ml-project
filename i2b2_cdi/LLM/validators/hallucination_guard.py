# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Hallucination guard — rule-based checks on parsed LLM output.

Two checks are configured per concept:

1. ``min_confidence`` — if the parsed output has a ``confidence`` field, it
   must meet or exceed this threshold.
2. ``require_evidence_substring`` — the parsed output's ``evidence`` field
   must appear (case-insensitively by default, D-4.6) somewhere in the
   source note. LLMs normalize casing on clinical abbreviations
   ("ef 30%" → "EF 30%"), and MIMIC notes are inconsistently capitalized;
   case-sensitive matching produces false-positive hallucination flags.
   Opt-in case-sensitive via ``case_sensitive_evidence=True``.

Empty config = opt-out (``check`` always returns True). LLM-judge mode is
deferred to Sprint 3+.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


class HallucinationGuard:
    """Configurable rule-based guard. ``check(parsed, source_note)`` is the API."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        config = dict(config or {})
        min_conf = config.get("min_confidence")
        if min_conf is not None:
            try:
                min_conf = float(min_conf)
            except (TypeError, ValueError) as e:
                raise ValueError(f"min_confidence must be numeric, got {min_conf!r}") from e
            if not (0.0 <= min_conf <= 1.0):
                raise ValueError(
                    f"min_confidence must be in [0.0, 1.0], got {min_conf}"
                )
        self.min_confidence: Optional[float] = min_conf
        self.require_evidence_substring: bool = bool(
            config.get("require_evidence_substring", False)
        )
        self.case_sensitive_evidence: bool = bool(
            config.get("case_sensitive_evidence", False)
        )
        self.max_retries: int = int(config.get("max_retries", 2))
        if self.max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {self.max_retries}")

    def check(
        self,
        parsed: Optional[Dict[str, Any]],
        source_note: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Return (ok, error_message_or_None). Empty config => always passes."""
        if parsed is None:
            return False, "parsed output is None (cannot guard)"
        if self.min_confidence is not None:
            conf = parsed.get("confidence")
            if conf is None:
                return False, "missing 'confidence' field required by guardrail"
            try:
                conf_f = float(conf)
            except (TypeError, ValueError):
                return False, f"non-numeric confidence: {conf!r}"
            if conf_f < self.min_confidence:
                return False, (
                    f"confidence {conf_f:.3f} below threshold {self.min_confidence:.3f}"
                )
        if self.require_evidence_substring:
            evidence = parsed.get("evidence")
            if not evidence:
                return False, "missing 'evidence' field required by guardrail"
            if not isinstance(evidence, str):
                return False, f"evidence must be string, got {type(evidence).__name__}"
            if source_note is None:
                return False, "require_evidence_substring set but source_note=None"
            if self.case_sensitive_evidence:
                if evidence not in source_note:
                    return False, "evidence substring not present in source note (case-sensitive)"
            else:
                if evidence.lower() not in source_note.lower():
                    return False, "evidence substring not present in source note"
        return True, None
