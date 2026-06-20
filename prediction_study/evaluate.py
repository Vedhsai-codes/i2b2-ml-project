"""Rigorous evaluation harness for a temporal phenotype cohort (one CSV = one design point).

Trains an elastic-net logistic regression (the i2b2-ML model family; saga solver, inner-CV
tuned) on a natural-prevalence cohort, with median imputation + missing-indicators, and
reports discrimination, calibration, and clinical-operating-point metrics with bootstrap
95% CIs on a held-out test set. No SMOTE (it harms calibration); class balance is handled by
the elastic-net + reported at the natural base rate.

Usage:
    python prediction_study/evaluate.py --csv prediction_study/data/hf_b0.csv --tag hf_b0
"""

from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, brier_score_loss,
                             roc_auc_score, roc_curve)
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
SEED = 42
NON_FEATURES = {"subject_id", "label", "anchor_date", "feature_date", "days_before_anchor"}


def _calibration_slope_intercept(y, p):
    eps = 1e-6
    lp = np.log(np.clip(p, eps, 1 - eps) / (1 - np.clip(p, eps, 1 - eps))).reshape(-1, 1)
    lr = LogisticRegression(penalty=None, solver="lbfgs", max_iter=1000).fit(lp, y)
    return float(lr.coef_[0][0]), float(lr.intercept_[0])


def _metrics_at_threshold(y, p, thr):
    pred = (p >= thr).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum()); fp = int(((pred == 1) & (y == 0)).sum())
    tn = int(((pred == 0) & (y == 0)).sum()); fn = int(((pred == 0) & (y == 1)).sum())
    sens = tp / (tp + fn) if tp + fn else float("nan")
    spec = tn / (tn + fp) if tn + fp else float("nan")
    ppv = tp / (tp + fp) if tp + fp else float("nan")
    npv = tn / (tn + fn) if tn + fn else float("nan")
    return {"threshold": round(thr, 4), "sensitivity": round(sens, 3),
            "specificity": round(spec, 3), "ppv": round(ppv, 3), "npv": round(npv, 3)}


def _bootstrap_ci(y, p, fn, n=1000):
    rng = np.random.default_rng(SEED)
    vals = []
    idx = np.arange(len(y))
    for _ in range(n):
        b = rng.choice(idx, size=len(idx), replace=True)
        if y[b].sum() == 0 or y[b].sum() == len(b):
            continue
        vals.append(fn(y[b], p[b]))
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return round(float(lo), 4), round(float(hi), 4)


def evaluate(csv: Path, tag: str) -> dict:
    df = pd.read_csv(csv)
    y = df["label"].astype(int).values
    feats = [c for c in df.columns if c not in NON_FEATURES]
    X = df[feats]
    binary = [c for c in feats if c.startswith(("cm_", "med_")) or c == "sex_male"]
    numeric = [c for c in feats if c not in binary]

    pre = ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median", add_indicator=True)),
                          ("sc", StandardScaler())]), numeric),
        ("bin", "passthrough", binary),
    ])
    base = LogisticRegression(penalty="elasticnet", solver="saga", max_iter=2000)
    grid = GridSearchCV(base, {"C": [0.1, 1.0], "l1_ratio": [0.2, 0.5, 0.8]},
                        scoring="roc_auc", cv=4, n_jobs=-1)
    pipe = Pipeline([("pre", pre), ("clf", grid)])

    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, stratify=y, random_state=SEED)
    pipe.fit(Xtr, ytr)
    p = pipe.predict_proba(Xte)[:, 1]
    yte = np.asarray(yte)

    auroc = roc_auc_score(yte, p)
    auprc = average_precision_score(yte, p)
    base_rate = float(yte.mean())
    slope, intercept = _calibration_slope_intercept(yte, p)
    # operating point: threshold at the cohort prevalence (a simple, prevalence-aware choice)
    thr = float(np.quantile(p, 1 - base_rate))
    out = {
        "tag": tag, "n_total": len(df), "n_test": len(yte),
        "prevalence": round(base_rate, 4),
        "median_days_before_anchor": float(df["days_before_anchor"].median()),
        "auroc": round(float(auroc), 4),
        "auroc_ci95": _bootstrap_ci(yte, p, roc_auc_score),
        "auprc": round(float(auprc), 4),
        "auprc_ci95": _bootstrap_ci(yte, p, average_precision_score),
        "auprc_lift_over_baserate": round(float(auprc / base_rate), 2),
        "brier": round(float(brier_score_loss(yte, p)), 4),
        "calibration_slope": round(slope, 3),
        "calibration_intercept": round(intercept, 3),
        "operating_point": _metrics_at_threshold(yte, p, thr),
        "n_features": len(feats),
        "best_params": grid.best_params_,
    }
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, type=Path)
    ap.add_argument("--tag", required=True)
    args = ap.parse_args(argv)
    res = evaluate(args.csv, args.tag)
    outdir = Path(__file__).resolve().parent / "results"
    outdir.mkdir(exist_ok=True)
    (outdir / f"{args.tag}.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
