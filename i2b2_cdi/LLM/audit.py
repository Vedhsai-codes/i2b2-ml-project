# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""PromptAuditLogger — writes one row per provider call to ``llm_audit``.

Audit modes:
    - ``full``     — store prompt + response verbatim (OK for de-identified MIMIC)
    - ``redacted`` — null prompt_text / response_text, keep hash + parsed + counts
    - ``off``      — skip entirely (use only for stress tests)

Invariants:
    - One row per provider call (every retry attempt writes a row)
    - On terminal failure (retries exhausted), an extra row is written with
      ``guardrail_outcome='exhausted'`` so terminal failures are grep-able
      from the log without reconstructing per-patient retry sequences (D-4.2)
    - DB INSERT failure is logged via loguru but does NOT raise (sidecar
      pattern; observability never blocks the primary clinical workflow, D-4.3)
    - ``audit_rows_written`` counter exposes successful inserts so the operator
      can reconcile against ``SELECT COUNT(*) FROM llm_audit WHERE job_id = ?``

PG / MSSQL branching follows the existing ``os.environ['CRC_DB_TYPE']`` pattern.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from loguru import logger


_VALID_LEVELS = ("full", "redacted", "off")
_VALID_OUTCOMES = (
    "passed",
    "failed_validation",
    "failed_guardrail",
    "retried",
    "exhausted",
    "provider_error",
)


class PromptAuditLogger:
    """Writes audit rows for the LLM module's provider calls."""

    def __init__(self, crc_ds, audit_level: str = "full") -> None:
        if audit_level not in _VALID_LEVELS:
            raise ValueError(
                f"audit_level must be one of {_VALID_LEVELS}, got {audit_level!r}"
            )
        self.crc_ds = crc_ds
        self.audit_level = audit_level
        self.audit_rows_written = 0

    def log(
        self,
        *,
        job_id: int,
        patient_num: Optional[int],
        concept_cd: Optional[str],
        provider_name: str,
        model_name: str,
        prompt_hash: str,
        prompt_text: Optional[str],
        response_text: Optional[str],
        parsed_output: Optional[Dict[str, Any]],
        finish_reason: Optional[str],
        prompt_tokens: Optional[int],
        completion_tokens: Optional[int],
        cost_usd: float = 0.0,
        latency_ms: Optional[int] = None,
        guardrail_outcome: str = "passed",
    ) -> bool:
        """Write one audit row. Returns True on success, False on swallowed failure."""
        if self.audit_level == "off":
            return False
        if guardrail_outcome not in _VALID_OUTCOMES:
            logger.warning(
                "Unknown guardrail_outcome {!r}; coercing to 'provider_error'",
                guardrail_outcome,
            )
            guardrail_outcome = "provider_error"

        if self.audit_level == "redacted":
            prompt_text_to_store: Optional[str] = None
            response_text_to_store: Optional[str] = None
        else:
            prompt_text_to_store = prompt_text
            response_text_to_store = response_text

        parsed_json = (
            json.dumps(parsed_output, default=str) if parsed_output is not None else None
        )

        db_type = os.environ.get("CRC_DB_TYPE", "pg")
        # Schema-qualify the table name. Matches the existing i2b2-etl
        # convention in i2b2_cdi/job/jobs.py:69-71 and removes the
        # implicit dependency on the PG user's search_path being set to
        # i2b2demodata. See SELF_REVIEW.md H-5.
        schema = os.environ.get("CRC_DB_NAME", "")
        prefix = f"{schema}." if schema else ""
        try:
            with self.crc_ds as cursor:
                if db_type == "pg":
                    sql = (
                        f"INSERT INTO {prefix}llm_audit ("
                        "job_id, patient_num, concept_cd, provider_name, model_name, "
                        "prompt_hash, prompt_text, response_text, parsed_output, "
                        "finish_reason, prompt_tokens, completion_tokens, "
                        "cost_usd, latency_ms, guardrail_outcome"
                        ") VALUES ("
                        "%(job_id)s, %(patient_num)s, %(concept_cd)s, %(provider_name)s, "
                        "%(model_name)s, %(prompt_hash)s, %(prompt_text)s, %(response_text)s, "
                        "%(parsed_output)s, %(finish_reason)s, %(prompt_tokens)s, "
                        "%(completion_tokens)s, %(cost_usd)s, %(latency_ms)s, "
                        "%(guardrail_outcome)s)"
                    )
                    params = {
                        "job_id": job_id,
                        "patient_num": patient_num,
                        "concept_cd": concept_cd,
                        "provider_name": provider_name,
                        "model_name": model_name,
                        "prompt_hash": prompt_hash,
                        "prompt_text": prompt_text_to_store,
                        "response_text": response_text_to_store,
                        "parsed_output": parsed_json,
                        "finish_reason": finish_reason,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "cost_usd": float(cost_usd or 0.0),
                        "latency_ms": latency_ms,
                        "guardrail_outcome": guardrail_outcome,
                    }
                    cursor.execute(sql, params)
                elif db_type == "mssql":
                    sql = (
                        f"INSERT INTO {prefix}llm_audit ("
                        "job_id, patient_num, concept_cd, provider_name, model_name, "
                        "prompt_hash, prompt_text, response_text, parsed_output, "
                        "finish_reason, prompt_tokens, completion_tokens, "
                        "cost_usd, latency_ms, guardrail_outcome"
                        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                    )
                    cursor.execute(
                        sql,
                        (
                            job_id,
                            patient_num,
                            concept_cd,
                            provider_name,
                            model_name,
                            prompt_hash,
                            prompt_text_to_store,
                            response_text_to_store,
                            parsed_json,
                            finish_reason,
                            prompt_tokens,
                            completion_tokens,
                            float(cost_usd or 0.0),
                            latency_ms,
                            guardrail_outcome,
                        ),
                    )
                else:
                    logger.warning("Unsupported CRC_DB_TYPE={!r} for audit; skipping", db_type)
                    return False
        except Exception as e:
            logger.exception("llm_audit INSERT failed (sidecar; not raising): {!r}", e)
            return False
        self.audit_rows_written += 1
        return True
