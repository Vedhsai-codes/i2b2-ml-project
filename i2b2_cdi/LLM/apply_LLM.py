# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""``run_label`` — the "apply" step for ``jobType: llm-label``.

End-to-end per concept_blob:
    1. Resolve target patient cohort + note concept paths from the blob.
    2. Pull notes from ``observation_fact``, group by patient_num.
    3. For each patient, render the prompt, call the provider with retries,
       validate the structured output, run the hallucination guard, and
       write one audit row per attempt (plus an extra "exhausted" row on
       terminal failure per D-4.2).
    4. Aggregate successful labels into a DataFrame and call ``send_facts``.
    5. Return a summary dict populated as ``self.output`` by the orchestrator.

Retry semantics: the inner ``_one_attempt`` closure raises
``RetryableValidationError`` for schema/guardrail failures so that the
``retry_with_backoff`` helper drives both transient (network) and semantic
retries through one path. The retry tuple is narrow:
``(TimeoutError, ConnectionError, RetryableValidationError)``.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import pandas as pd
from loguru import logger

from i2b2_cdi.LLM.audit import PromptAuditLogger
from i2b2_cdi.LLM.llm_helper import (
    RetryableValidationError,
    compute_prompt_hash,
    render_prompt,
    retry_with_backoff,
)
from i2b2_cdi.LLM.providers import get_provider
from i2b2_cdi.LLM.validators import HallucinationGuard, SchemaValidator, coerce_text_to_dict


def _schema_prefix() -> str:
    """Return ``"{CRC_DB_NAME}."`` for schema-qualified table names, or empty.

    Matches the existing i2b2-etl convention (see ``i2b2_cdi/job/jobs.py:69``)
    of prefixing all table references with the schema name. Removes the
    implicit dependency on the PG user's ``search_path`` being configured.
    """
    schema = os.environ.get("CRC_DB_NAME", "")
    return f"{schema}." if schema else ""


def _resolve_target_patients(crc_ds, target_paths: List[str]) -> List[int]:
    """Return distinct patient_num for patients in any of the given paths."""
    if not target_paths:
        return []
    db_type = os.environ.get("CRC_DB_TYPE", "pg")
    prefix = _schema_prefix()
    patients: List[int] = []
    with crc_ds as cursor:
        for path in target_paths:
            if db_type == "pg":
                cursor.execute(
                    f"SELECT DISTINCT patient_num FROM {prefix}observation_fact "
                    f"WHERE concept_cd IN ("
                    f"  SELECT concept_cd FROM {prefix}concept_dimension WHERE concept_path = %(p)s"
                    f")",
                    {"p": path},
                )
            else:
                cursor.execute(
                    f"SELECT DISTINCT patient_num FROM {prefix}observation_fact "
                    f"WHERE concept_cd IN ("
                    f"  SELECT concept_cd FROM {prefix}concept_dimension WHERE concept_path = ?"
                    f")",
                    (path,),
                )
            for row in cursor.fetchall():
                patients.append(int(row[0]))
    return sorted(set(patients))


def _fetch_notes_for_patient(
    crc_ds,
    patient_num: int,
    note_paths: List[str],
    period_start: Optional[str],
    period_end: Optional[str],
) -> str:
    """Concatenate all note text for a patient within the date range."""
    db_type = os.environ.get("CRC_DB_TYPE", "pg")
    prefix = _schema_prefix()
    pieces: List[str] = []
    with crc_ds as cursor:
        for path in note_paths:
            if db_type == "pg":
                sql = (
                    f"SELECT observation_blob FROM {prefix}observation_fact "
                    f"WHERE patient_num = %(p)s "
                    f"AND concept_cd IN ("
                    f"  SELECT concept_cd FROM {prefix}concept_dimension WHERE concept_path = %(path)s"
                    f")"
                )
                params: Dict[str, Any] = {"p": patient_num, "path": path}
                if period_start:
                    sql += " AND start_date >= %(s)s"
                    params["s"] = period_start
                if period_end:
                    sql += " AND start_date <= %(e)s"
                    params["e"] = period_end
                cursor.execute(sql, params)
            else:
                sql = (
                    f"SELECT observation_blob FROM {prefix}observation_fact "
                    f"WHERE patient_num = ? AND concept_cd IN ("
                    f"  SELECT concept_cd FROM {prefix}concept_dimension WHERE concept_path = ?"
                    f")"
                )
                args: List[Any] = [patient_num, path]
                if period_start:
                    sql += " AND start_date >= ?"
                    args.append(period_start)
                if period_end:
                    sql += " AND start_date <= ?"
                    args.append(period_end)
                cursor.execute(sql, tuple(args))
            for row in cursor.fetchall():
                if row[0]:
                    pieces.append(str(row[0]))
    return "\n\n".join(pieces)


def run_label(
    *,
    conceptPath: str,
    conceptCode: str,
    crc_ds,
    job_id: int,
    project_name: str,
    concept_blob: Dict[str, Any],
    input_params: Dict[str, Any],
    send_facts: Callable[[pd.DataFrame], None],
    provider=None,
    audit_logger: Optional[PromptAuditLogger] = None,
) -> Dict[str, Any]:
    """Apply an LLM label to each patient in the target cohort. Returns summary dict."""
    target_paths: List[str] = list(input_params.get("target_patient_set") or [])
    if not target_paths:
        target_paths = list(concept_blob.get("target_patient_set") or [])
    note_paths: List[str] = list(concept_blob.get("note_concept_paths") or [])
    template_name = concept_blob.get("prompt_template", "cohort_labeling")
    prompt_variables = dict(concept_blob.get("prompt_variables") or {})
    output_schema = concept_blob.get("output_schema")
    guardrail_cfg = dict(concept_blob.get("guardrails") or {})
    sampling = dict(concept_blob.get("sampling") or {})
    max_tokens = int(sampling.get("max_tokens", 512))
    temperature = float(sampling.get("temperature", 0.0))
    period_start = concept_blob.get("data_period_start")
    period_end = concept_blob.get("data_period_end")
    audit_level = str(concept_blob.get("audit_level", "full"))
    max_retries = int(guardrail_cfg.get("max_retries", 2))

    if provider is None:
        provider = get_provider(concept_blob["provider"])
    validator = SchemaValidator(output_schema)
    guard = HallucinationGuard(guardrail_cfg)
    if audit_logger is None:
        audit_logger = PromptAuditLogger(crc_ds, audit_level=audit_level)

    patient_nums = _resolve_target_patients(crc_ds, target_paths)
    logger.info("LLM label job {} — {} target patients", job_id, len(patient_nums))

    n_processed = 0
    n_positive = 0
    n_failed_validation = 0
    confidence_sum = 0.0
    confidence_n = 0
    total_latency_ms = 0
    total_cost = 0.0
    fact_rows: List[Dict[str, Any]] = []

    for patient_num in patient_nums:
        note_text = _fetch_notes_for_patient(
            crc_ds, patient_num, note_paths, period_start, period_end
        )
        prompt_vars = dict(prompt_variables)
        prompt_vars["note_text"] = note_text
        prompt = render_prompt(template_name, prompt_vars)
        prompt_hash = compute_prompt_hash(prompt)
        provider_name = getattr(provider, "name", "unknown")
        model_name = getattr(provider, "model", "unknown")

        def _one_attempt():
            llm_resp = provider.generate(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                output_schema=output_schema,
            )
            parsed = coerce_text_to_dict(llm_resp.text)
            ok_schema, schema_err = validator.validate(parsed) if parsed is not None else (False, "parse failed")
            outcome = "passed"
            err: Optional[str] = None
            if not ok_schema:
                outcome = "failed_validation"
                err = schema_err or "parse failed"
            else:
                ok_guard, guard_err = guard.check(parsed, source_note=note_text)
                if not ok_guard:
                    outcome = "failed_guardrail"
                    err = guard_err
            audit_logger.log(
                job_id=job_id,
                patient_num=patient_num,
                concept_cd=conceptCode,
                provider_name=provider_name,
                model_name=model_name,
                prompt_hash=prompt_hash,
                prompt_text=prompt,
                response_text=llm_resp.text,
                parsed_output=parsed,
                finish_reason=llm_resp.finish_reason,
                prompt_tokens=llm_resp.usage.get("prompt_tokens"),
                completion_tokens=llm_resp.usage.get("completion_tokens"),
                cost_usd=llm_resp.cost_usd,
                latency_ms=llm_resp.latency_ms,
                guardrail_outcome=outcome,
            )
            if outcome != "passed":
                raise RetryableValidationError(err or outcome)
            return parsed, llm_resp

        try:
            parsed, llm_resp = retry_with_backoff(
                _one_attempt,
                max_retries=max_retries,
                base_delay_s=0.0,
            )
        except RetryableValidationError as e:
            n_failed_validation += 1
            audit_logger.log(
                job_id=job_id,
                patient_num=patient_num,
                concept_cd=conceptCode,
                provider_name=provider_name,
                model_name=model_name,
                prompt_hash=prompt_hash,
                prompt_text=prompt,
                response_text=None,
                parsed_output=None,
                finish_reason=None,
                prompt_tokens=None,
                completion_tokens=None,
                cost_usd=0.0,
                latency_ms=None,
                guardrail_outcome="exhausted",
            )
            logger.warning("Patient {} exhausted retries: {}", patient_num, e)
            n_processed += 1
            continue
        except (TimeoutError, ConnectionError) as e:
            n_failed_validation += 1
            audit_logger.log(
                job_id=job_id,
                patient_num=patient_num,
                concept_cd=conceptCode,
                provider_name=provider_name,
                model_name=model_name,
                prompt_hash=prompt_hash,
                prompt_text=prompt,
                response_text=None,
                parsed_output=None,
                finish_reason=None,
                prompt_tokens=None,
                completion_tokens=None,
                cost_usd=0.0,
                latency_ms=None,
                guardrail_outcome="exhausted",
            )
            logger.warning("Patient {} exhausted provider retries: {!r}", patient_num, e)
            n_processed += 1
            continue

        n_processed += 1
        total_latency_ms += llm_resp.latency_ms or 0
        total_cost += llm_resp.cost_usd or 0.0
        label_val = parsed.get("label") if parsed else None
        conf = parsed.get("confidence") if parsed else None
        try:
            label_int = int(label_val) if label_val is not None else None
        except (TypeError, ValueError):
            label_int = None
        if label_int == 1:
            n_positive += 1
        if conf is not None:
            try:
                confidence_sum += float(conf)
                confidence_n += 1
            except (TypeError, ValueError):
                pass
        if label_int is not None:
            fact_rows.append(
                {
                    "mrn": patient_num,
                    "code": conceptCode,
                    "start-date": _today(),
                    "value": label_int,
                }
            )

    if fact_rows:
        df = pd.DataFrame(fact_rows, columns=["mrn", "code", "start-date", "value"])
        try:
            send_facts(df)
        except Exception as e:
            logger.exception("send_facts failed: {!r}", e)
            raise

    mean_conf = (confidence_sum / confidence_n) if confidence_n else 0.0
    return {
        "n_processed": n_processed,
        "n_labeled_positive": n_positive,
        "n_failed_validation": n_failed_validation,
        "mean_confidence": round(mean_conf, 4),
        "total_cost_usd": round(total_cost, 6),
        "total_latency_s": round(total_latency_ms / 1000.0, 3),
        "audit_rows_written": audit_logger.audit_rows_written,
    }


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
