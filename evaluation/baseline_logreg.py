#!/usr/bin/env python
# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""TF-IDF + Logistic Regression baseline for HF cohort labeling.

The "traditional NLP" baseline against which the LLM extension is
compared in the paper. Same inputs and same output schema as
``run_demonstration.py`` so ``quick_inspect.py`` reads both kinds of
results identically.

Architecture (kept deliberately simple — this is the strawman the
paper compares against, not a fully tuned model):

    TfidfVectorizer(ngram_range=(1, 2), max_features=20000, min_df=2,
                    stop_words='english', sublinear_tf=True)
      → LogisticRegression(class_weight='balanced', max_iter=1000,
                           C=1.0, solver='liblinear')

Cross-validation: StratifiedKFold(n_splits=5, shuffle=True,
random_state=42). Predicted labels come from
``cross_val_predict``; predicted probabilities from
``cross_val_predict(..., method='predict_proba')`` to compute AUROC.

Outputs (mirrors evaluation/run_demonstration.py):
    raw_predictions.csv
    metrics_summary.json
    confusion_matrix.csv
    error_analysis.csv
    run_config.json
    run_log.txt

Usage::

    python evaluation/baseline_logreg.py \
        --cohort ~/mimic_data/cohort_v1.csv \
        --out-root evaluation/results
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _git_commit_hash() -> Optional[str]:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(Path(__file__).resolve().parent.parent),
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return None


def _git_dirty() -> Optional[bool]:
    try:
        return bool(subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=str(Path(__file__).resolve().parent.parent),
            stderr=subprocess.DEVNULL,
        ).decode().strip())
    except Exception:
        return None


def _make_results_dir(out_root: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    p = out_root / f"baseline_{ts}"
    p.mkdir(parents=True, exist_ok=False)
    return p


def run(cohort_path: Path, out_root: Path, random_state: int = 42) -> Path:
    import numpy as np
    import pandas as pd
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import (
        cohen_kappa_score,
        confusion_matrix,
        roc_auc_score,
    )
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.pipeline import Pipeline

    results_dir = _make_results_dir(out_root)

    # ─── logging ────────────────────────────────────────────────────
    log_path = results_dir / "run_log.txt"
    log_lines = []

    def log(msg):
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line)
        log_lines.append(line)

    log(f"=== baseline LogReg eval start === results -> {results_dir}")
    cohort_df = pd.read_csv(cohort_path)
    log(f"loaded cohort: {len(cohort_df)} rows ({int(cohort_df['hf_gold'].sum())} HF+, "
        f"{int((cohort_df['hf_gold']==0).sum())} HF-)")

    # ─── reproducibility receipt ────────────────────────────────────
    run_config = {
        "method": "TF-IDF(1-2grams, max_features=20000, min_df=2, sublinear_tf, english stops) + LogisticRegression(class_weight='balanced', C=1.0, solver='liblinear', max_iter=1000)",
        "cv": "StratifiedKFold(n_splits=5, shuffle=True, random_state=42)",
        "cohort_path": str(cohort_path),
        "cohort_row_count": int(len(cohort_df)),
        "config": {
            "provider": {
                "name": "baseline",
                "model": "TF-IDF+LogReg",
            },
        },
        "git_commit": _git_commit_hash(),
        "git_dirty": _git_dirty(),
        "python": sys.version,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "random_state": random_state,
    }
    (results_dir / "run_config.json").write_text(json.dumps(run_config, indent=2, default=str))

    # ─── train / predict ────────────────────────────────────────────
    X = cohort_df["text"].fillna("").astype(str).values
    y = cohort_df["hf_gold"].astype(int).values

    pipe = Pipeline([
        ("tfidf", TfidfVectorizer(
            ngram_range=(1, 2),
            max_features=20000,
            min_df=2,
            stop_words="english",
            sublinear_tf=True,
        )),
        ("clf", LogisticRegression(
            class_weight="balanced",
            C=1.0,
            solver="liblinear",
            max_iter=1000,
            random_state=random_state,
        )),
    ])
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=random_state)

    start = time.time()
    log("running 5-fold cross_val_predict (predict)...")
    y_pred = cross_val_predict(pipe, X, y, cv=cv, n_jobs=-1)
    log("running 5-fold cross_val_predict (predict_proba)...")
    y_prob = cross_val_predict(pipe, X, y, cv=cv, n_jobs=-1, method="predict_proba")[:, 1]
    runtime_s = time.time() - start
    log(f"5-fold CV done in {runtime_s:.1f}s")

    # ─── metrics (computed on the SAME shape as run_demonstration.py) ─
    cm = confusion_matrix(y, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()

    metrics = {
        "n_total": int(len(y)),
        "n_processed": int(len(y)),
        "n_failed": 0,
        "true_negative": int(tn),
        "false_positive": int(fp),
        "false_negative": int(fn),
        "true_positive": int(tp),
        "accuracy": round(float((tp + tn) / max(tp + tn + fp + fn, 1)), 4),
        "sensitivity": round(float(tp / max(tp + fn, 1)), 4),
        "specificity": round(float(tn / max(tn + fp, 1)), 4),
        "ppv": round(float(tp / max(tp + fp, 1)), 4) if (tp + fp) else 0.0,
        "npv": round(float(tn / max(tn + fn, 1)), 4) if (tn + fn) else 0.0,
        "cohen_kappa": round(float(cohen_kappa_score(y, y_pred)), 4),
    }
    try:
        metrics["auroc_confidence"] = round(float(roc_auc_score(y, y_prob)), 4)
    except ValueError:
        metrics["auroc_confidence"] = None
    metrics["total_runtime_s"] = round(runtime_s, 3)
    metrics["total_cost_usd"] = 0.0
    metrics["audit_rows_written"] = 0  # baseline has no audit log

    (results_dir / "metrics_summary.json").write_text(json.dumps(metrics, indent=2))
    log(f"kappa={metrics['cohen_kappa']}  sens={metrics['sensitivity']}  "
        f"spec={metrics['specificity']}  auroc={metrics['auroc_confidence']}")

    # ─── confusion matrix CSV ────────────────────────────────────────
    pd.DataFrame([
        ["", "pred_neg", "pred_pos"],
        ["actual_neg", int(tn), int(fp)],
        ["actual_pos", int(fn), int(tp)],
    ]).to_csv(results_dir / "confusion_matrix.csv", index=False, header=False)

    # ─── raw predictions ─────────────────────────────────────────────
    raw = pd.DataFrame({
        "subject_id": cohort_df["subject_id"],
        "hadm_id": cohort_df["hadm_id"],
        "note_id": cohort_df["note_id"],
        "hf_gold": y,
        "llm_label": y_pred,
        "llm_confidence": np.round(y_prob, 4),
        "llm_evidence": "",  # baseline doesn't produce evidence
        "status": "ok",
        "attempts": 1,
        "runtime_ms": int(runtime_s * 1000 / max(len(y), 1)),
        "prompt_tokens": None,
        "completion_tokens": None,
        "cost_usd": 0.0,
        "note_excerpt": cohort_df["text"].astype(str).str[:300],
    })
    raw.to_csv(results_dir / "raw_predictions.csv", index=False)

    # ─── error analysis ─────────────────────────────────────────────
    err_mask = raw["hf_gold"] != raw["llm_label"]
    raw[err_mask].to_csv(results_dir / "error_analysis.csv", index=False)

    log(f"=== baseline done === {metrics}")
    log_path.write_text("\n".join(log_lines))
    return results_dir


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description="TF-IDF + LogReg baseline for the HF cohort.")
    p.add_argument("--cohort", type=Path, required=True, help="Path to cohort CSV.")
    p.add_argument(
        "--out-root",
        type=Path,
        default=Path("evaluation/results"),
        help="Root for per-run output (default: evaluation/results).",
    )
    p.add_argument("--seed", type=int, default=42, help="Random seed for CV.")
    return p.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    results_dir = run(args.cohort, args.out_root, random_state=args.seed)
    print(f"\nresults: {results_dir}")
    return results_dir


if __name__ == "__main__":
    main()
