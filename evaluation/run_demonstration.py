#!/usr/bin/env python
# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Run the i2b2-ML LLM demonstration eval on a cohort CSV.

End-to-end pipeline: cohort CSV in → results table + metrics out. Uses
the i2b2_cdi.LLM module as a LIBRARY — no Flask app, no jobWatcher, no
live i2b2 Postgres. The audit log lands in a per-run sqlite file under
the results directory so this script runs anywhere.

Usage::

    python evaluation/run_demonstration.py \
        --cohort  evaluation/synthetic_cohort.csv \
        --config  evaluation/sample_config.json \
        --out-root evaluation/results

Outputs (under ``<out-root>/<timestamp>/``):

    raw_predictions.csv     one row per cohort patient
    metrics_summary.json    kappa, sens, spec, PPV, NPV, AUROC, accuracy, runtime, cost
    confusion_matrix.csv    2x2 table
    error_analysis.csv      every patient where llm_label != hf_gold + note excerpt
    run_config.json         provider + prompt + git commit hash + timestamp + cohort path
    run_log.txt             loguru output of the entire run
    audit.sqlite            per-call audit rows via PromptAuditLogger
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from loguru import logger


# ---------------------------------------------------------------------------
# Sqlite audit shim: present a fake CRC data source to PromptAuditLogger.
# ---------------------------------------------------------------------------

_NAMED_PLACEHOLDER_RE = re.compile(r"%\(([A-Za-z_][A-Za-z0-9_]*)\)s")


class _SqliteCursorShim:
    """Translates PG-style SQL placeholders to sqlite forms.

    Mirrors the pattern in ``tests/LLM/conftest.py`` so the production
    audit code can run unchanged against a per-run sqlite file. Also
    strips any ``$CRC_DB_NAME.`` schema prefix (sqlite has no schemas).
    """

    def __init__(self, real_cursor, schema_prefix_re):
        self._real = real_cursor
        self._schema_prefix_re = schema_prefix_re

    def _translate(self, sql: str) -> str:
        sql = self._schema_prefix_re.sub("", sql)
        sql = _NAMED_PLACEHOLDER_RE.sub(r":\1", sql)
        sql = sql.replace("%s", "?")
        return sql

    def execute(self, sql, params=None):
        sql = self._translate(sql)
        if params is None:
            return self._real.execute(sql)
        if isinstance(params, dict):
            return self._real.execute(sql, params)
        return self._real.execute(sql, tuple(params))

    def fetchone(self):
        return self._real.fetchone()

    def fetchall(self):
        return self._real.fetchall()


class SqliteAuditDataSource:
    """Context manager that yields a translating cursor against a sqlite file."""

    def __init__(self, db_path: Path):
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._init_schema()
        schema_name = os.environ.get("CRC_DB_NAME", "")
        if schema_name:
            self._schema_re = re.compile(r"\b" + re.escape(schema_name) + r"\.")
        else:
            # Match nothing
            self._schema_re = re.compile(r"^$")

    def _init_schema(self):
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS llm_audit (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                patient_num INTEGER,
                concept_cd TEXT,
                provider_name TEXT NOT NULL,
                model_name TEXT NOT NULL,
                prompt_hash TEXT NOT NULL,
                prompt_text TEXT,
                response_text TEXT,
                parsed_output TEXT,
                finish_reason TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                cost_usd REAL,
                latency_ms INTEGER,
                guardrail_outcome TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self._conn.commit()

    def __enter__(self):
        return _SqliteCursorShim(self._conn.cursor(), self._schema_re)

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self._conn.commit()
        return False

    def close(self):
        self._conn.close()


# ---------------------------------------------------------------------------
# Core run loop.
# ---------------------------------------------------------------------------


def _git_commit_hash() -> Optional[str]:
    """Best-effort git short-hash for the reproducibility receipt."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(Path(__file__).resolve().parent.parent),
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except Exception:
        return None


def _git_dirty() -> Optional[bool]:
    """True if the working tree has uncommitted changes; None if not a git checkout."""
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=str(Path(__file__).resolve().parent.parent),
            stderr=subprocess.DEVNULL,
        )
        return bool(out.decode().strip())
    except Exception:
        return None


def _make_results_dir(out_root: Path) -> Path:
    """Create ``<out_root>/<timestamp>/`` and return it."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    p = out_root / ts
    p.mkdir(parents=True, exist_ok=False)
    return p


def _process_one(
    patient_row: Dict[str, Any],
    job_id: int,
    provider,
    validator,
    guard,
    audit_logger,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Run the LLM on a single cohort row. Returns a dict suitable for a results CSV row."""
    from i2b2_cdi.LLM.llm_helper import (
        RetryableValidationError,
        compute_prompt_hash,
        render_prompt,
        retry_with_backoff,
    )
    from i2b2_cdi.LLM.validators import coerce_text_to_dict

    template_name = config.get("prompt_template", "cohort_labeling")
    prompt_variables = dict(config.get("prompt_variables") or {})
    output_schema = config.get("output_schema")
    sampling = dict(config.get("sampling") or {})
    max_tokens = int(sampling.get("max_tokens", 512))
    temperature = float(sampling.get("temperature", 0.0))
    max_retries = int((config.get("guardrails") or {}).get("max_retries", 2))

    note_text = str(patient_row.get("text") or "")
    prompt_vars = dict(prompt_variables)
    prompt_vars["note_text"] = note_text
    prompt = render_prompt(template_name, prompt_vars)
    prompt_hash = compute_prompt_hash(prompt)

    subject_id = int(patient_row["subject_id"])
    hf_gold = int(patient_row.get("hf_gold", 0))
    provider_name = getattr(provider, "name", "unknown")
    model_name = getattr(provider, "model", "unknown")

    state = {"attempts": 0}

    def _attempt():
        state["attempts"] += 1
        llm_resp = provider.generate(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            output_schema=output_schema,
        )
        parsed = coerce_text_to_dict(llm_resp.text)
        ok_schema, schema_err = (
            validator.validate(parsed) if parsed is not None else (False, "parse failed")
        )
        if not ok_schema:
            outcome = "failed_validation"
            err = schema_err or "parse failed"
        else:
            ok_guard, guard_err = guard.check(parsed, source_note=note_text)
            if not ok_guard:
                outcome = "failed_guardrail"
                err = guard_err
            else:
                outcome = "passed"
                err = None
        audit_logger.log(
            job_id=job_id,
            patient_num=subject_id,
            concept_cd=None,
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

    start = time.time()
    try:
        parsed, llm_resp = retry_with_backoff(
            _attempt, max_retries=max_retries, base_delay_s=0.0
        )
        llm_label: Optional[int] = None
        llm_conf: Optional[float] = None
        llm_evidence: Optional[str] = None
        try:
            llm_label = int(parsed.get("label")) if parsed and parsed.get("label") is not None else None
        except (TypeError, ValueError):
            llm_label = None
        try:
            llm_conf = float(parsed.get("confidence")) if parsed and parsed.get("confidence") is not None else None
        except (TypeError, ValueError):
            llm_conf = None
        llm_evidence = (parsed or {}).get("evidence")
        status = "ok"
        return {
            "subject_id": subject_id,
            "hadm_id": patient_row.get("hadm_id"),
            "note_id": patient_row.get("note_id"),
            "hf_gold": hf_gold,
            "llm_label": llm_label,
            "llm_confidence": llm_conf,
            "llm_evidence": llm_evidence,
            "status": status,
            "attempts": state["attempts"],
            "runtime_ms": int((time.time() - start) * 1000),
            "prompt_tokens": (llm_resp.usage or {}).get("prompt_tokens"),
            "completion_tokens": (llm_resp.usage or {}).get("completion_tokens"),
            "cost_usd": llm_resp.cost_usd,
            "note_excerpt": note_text[:300],
        }
    except (RetryableValidationError, TimeoutError, ConnectionError) as e:
        # Terminal failure — write the "exhausted" audit row per D-4.2
        audit_logger.log(
            job_id=job_id,
            patient_num=subject_id,
            concept_cd=None,
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
        logger.warning("Patient {} exhausted retries: {!r}", subject_id, e)
        return {
            "subject_id": subject_id,
            "hadm_id": patient_row.get("hadm_id"),
            "note_id": patient_row.get("note_id"),
            "hf_gold": hf_gold,
            "llm_label": None,
            "llm_confidence": None,
            "llm_evidence": None,
            "status": "failed",
            "attempts": state["attempts"],
            "runtime_ms": int((time.time() - start) * 1000),
            "prompt_tokens": None,
            "completion_tokens": None,
            "cost_usd": 0.0,
            "note_excerpt": note_text[:300],
        }


# ---------------------------------------------------------------------------
# Metric computation.
# ---------------------------------------------------------------------------


def _compute_metrics(raw_df: pd.DataFrame) -> Dict[str, Any]:
    """Compute the demonstration metrics. Reports n_failed separately so
    the metrics table reflects only successfully labeled patients."""
    from sklearn.metrics import (
        cohen_kappa_score,
        confusion_matrix,
        roc_auc_score,
    )

    n_total = len(raw_df)
    n_failed = int((raw_df["status"] != "ok").sum())
    ok = raw_df[raw_df["status"] == "ok"].copy()
    n_processed = len(ok)

    metrics: Dict[str, Any] = {
        "n_total": int(n_total),
        "n_processed": int(n_processed),
        "n_failed": n_failed,
    }
    if n_processed == 0:
        return metrics

    y_true = ok["hf_gold"].astype(int).tolist()
    y_pred = ok["llm_label"].astype(int).tolist()

    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()

    metrics["true_negative"] = int(tn)
    metrics["false_positive"] = int(fp)
    metrics["false_negative"] = int(fn)
    metrics["true_positive"] = int(tp)
    metrics["accuracy"] = round((tp + tn) / max(tp + tn + fp + fn, 1), 4)
    metrics["sensitivity"] = round(tp / max(tp + fn, 1), 4)  # recall+
    metrics["specificity"] = round(tn / max(tn + fp, 1), 4)  # recall-
    metrics["ppv"] = round(tp / max(tp + fp, 1), 4) if (tp + fp) else 0.0
    metrics["npv"] = round(tn / max(tn + fn, 1), 4) if (tn + fn) else 0.0
    metrics["cohen_kappa"] = round(float(cohen_kappa_score(y_true, y_pred)), 4)

    confs = ok["llm_confidence"].dropna().tolist()
    truths = ok.loc[ok["llm_confidence"].notna(), "hf_gold"].astype(int).tolist()
    if len(set(truths)) > 1 and confs:
        try:
            metrics["auroc_confidence"] = round(float(roc_auc_score(truths, confs)), 4)
        except ValueError:
            metrics["auroc_confidence"] = None
    else:
        metrics["auroc_confidence"] = None

    metrics["total_runtime_s"] = round(float(raw_df["runtime_ms"].sum() / 1000.0), 3)
    metrics["total_cost_usd"] = round(float(raw_df["cost_usd"].fillna(0.0).sum()), 6)
    return metrics


def _confusion_csv(raw_df: pd.DataFrame, out: Path) -> None:
    """Write a 2x2 confusion matrix CSV."""
    ok = raw_df[raw_df["status"] == "ok"]
    rows = [
        ["", "pred_neg", "pred_pos"],
        [
            "actual_neg",
            int(((ok["hf_gold"] == 0) & (ok["llm_label"] == 0)).sum()),
            int(((ok["hf_gold"] == 0) & (ok["llm_label"] == 1)).sum()),
        ],
        [
            "actual_pos",
            int(((ok["hf_gold"] == 1) & (ok["llm_label"] == 0)).sum()),
            int(((ok["hf_gold"] == 1) & (ok["llm_label"] == 1)).sum()),
        ],
    ]
    pd.DataFrame(rows).to_csv(out, index=False, header=False)


def _error_analysis_csv(raw_df: pd.DataFrame, out: Path) -> None:
    """Subset: every row where llm_label != hf_gold (or failed)."""
    mask = (raw_df["status"] != "ok") | (raw_df["llm_label"] != raw_df["hf_gold"])
    err = raw_df.loc[mask].copy()
    err.to_csv(out, index=False)


# ---------------------------------------------------------------------------
# Main entry point.
# ---------------------------------------------------------------------------


def run(
    cohort_path: Path,
    config_path: Path,
    out_root: Path,
    job_id: int = 1,
) -> Path:
    """Run the demonstration. Returns the per-run results directory."""
    from i2b2_cdi.LLM.audit import PromptAuditLogger
    from i2b2_cdi.LLM.providers import get_provider, register_provider, PROVIDER_REGISTRY
    from i2b2_cdi.LLM.validators import HallucinationGuard, SchemaValidator

    # Convenience: register the eval-only note-aware mock provider if
    # the config asks for it. This is purely for offline demos against
    # the synthetic cohort; real runs use anthropic / ollama / local_hf.
    config_for_check = json.loads(Path(config_path).read_text())
    provider_name = (config_for_check.get("provider") or {}).get("name")
    if provider_name == "mock" and "mock" not in PROVIDER_REGISTRY:
        from evaluation._eval_mock_provider import EvalMockProvider

        register_provider("mock", EvalMockProvider)
        logger.info("registered eval-only EvalMockProvider (note-aware)")

    results_dir = _make_results_dir(out_root)

    log_path = results_dir / "run_log.txt"
    log_sink = logger.add(log_path, level="DEBUG")

    try:
        logger.info("=== eval start === results -> {}", results_dir)
        cohort_df = pd.read_csv(cohort_path)
        config = json.loads(Path(config_path).read_text())
        logger.info(
            "loaded cohort: {} rows | provider: {} | model: {}",
            len(cohort_df),
            config.get("provider", {}).get("name"),
            config.get("provider", {}).get("model"),
        )

        # Snapshot config + reproducibility receipt
        run_config = {
            "config": config,
            "cohort_path": str(cohort_path),
            "cohort_row_count": int(len(cohort_df)),
            "git_commit": _git_commit_hash(),
            "git_dirty": _git_dirty(),
            "python": sys.version,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        (results_dir / "run_config.json").write_text(
            json.dumps(run_config, indent=2, default=str)
        )

        provider = get_provider(config["provider"])
        validator = SchemaValidator(config.get("output_schema"))
        guard = HallucinationGuard(config.get("guardrails") or {})

        audit_ds = SqliteAuditDataSource(results_dir / "audit.sqlite")
        audit_logger = PromptAuditLogger(audit_ds, audit_level=config.get("audit_level", "full"))

        rows: List[Dict[str, Any]] = []
        for _, patient in cohort_df.iterrows():
            rows.append(
                _process_one(
                    patient_row=patient.to_dict(),
                    job_id=job_id,
                    provider=provider,
                    validator=validator,
                    guard=guard,
                    audit_logger=audit_logger,
                    config=config,
                )
            )

        raw_df = pd.DataFrame(rows)
        raw_df.to_csv(results_dir / "raw_predictions.csv", index=False)

        metrics = _compute_metrics(raw_df)
        metrics["audit_rows_written"] = int(audit_logger.audit_rows_written)
        (results_dir / "metrics_summary.json").write_text(
            json.dumps(metrics, indent=2)
        )

        _confusion_csv(raw_df, results_dir / "confusion_matrix.csv")
        _error_analysis_csv(raw_df, results_dir / "error_analysis.csv")

        audit_ds.close()
        logger.success(
            "=== eval done === kappa={} sens={} spec={} n_processed={} n_failed={}",
            metrics.get("cohen_kappa"),
            metrics.get("sensitivity"),
            metrics.get("specificity"),
            metrics.get("n_processed"),
            metrics.get("n_failed"),
        )
    finally:
        with contextlib.suppress(Exception):
            logger.remove(log_sink)

    return results_dir


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description="Run the i2b2-ML LLM demonstration eval.")
    p.add_argument("--cohort", type=Path, required=True, help="Path to cohort CSV.")
    p.add_argument(
        "--config", type=Path, required=True, help="Path to eval config JSON."
    )
    p.add_argument(
        "--out-root",
        type=Path,
        default=Path("evaluation/results"),
        help="Root directory for per-run output (default: evaluation/results).",
    )
    p.add_argument(
        "--job-id", type=int, default=1, help="Pseudo job_id used in the audit log."
    )
    return p.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    results_dir = run(
        cohort_path=args.cohort,
        config_path=args.config,
        out_root=args.out_root,
        job_id=args.job_id,
    )
    print(f"results: {results_dir}")
    return results_dir


if __name__ == "__main__":
    main()
