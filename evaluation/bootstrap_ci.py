#!/usr/bin/env python
# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""95% bootstrap confidence intervals for any eval results dir.

Reads ``raw_predictions.csv`` from a results dir, resamples with
replacement N times (default 1000), recomputes every per-run metric on
each resample, and writes ``metrics_with_ci.json`` next to the existing
``metrics_summary.json``. Also prints a stdout table for quick viewing.

Works on any results dir: ``baseline_*`` and the LLM provider runs.
``quick_inspect.py`` will show CIs automatically when this file is
present.

Usage::

    python evaluation/bootstrap_ci.py evaluation/results/baseline_20260528T133857Z/
    # or default to the most recent results dir
    python evaluation/bootstrap_ci.py --auto

    # custom N and seed
    python evaluation/bootstrap_ci.py results_dir --n-bootstrap 2000 --seed 7
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

import numpy as np
import pandas as pd


def _latest_results_dir() -> Optional[Path]:
    root = Path(__file__).parent / "results"
    if not root.exists():
        return None
    dirs = sorted(p for p in root.iterdir() if p.is_dir())
    return dirs[-1] if dirs else None


def _metric_point(y_true: np.ndarray, y_pred: np.ndarray,
                  y_prob: Optional[np.ndarray]) -> Dict[str, float]:
    from sklearn.metrics import cohen_kappa_score, confusion_matrix, roc_auc_score

    out: Dict[str, float] = {}
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()
    n = tp + tn + fp + fn
    out["accuracy"] = (tp + tn) / max(n, 1)
    out["sensitivity"] = tp / max(tp + fn, 1)
    out["specificity"] = tn / max(tn + fp, 1)
    out["ppv"] = tp / max(tp + fp, 1) if (tp + fp) else float("nan")
    out["npv"] = tn / max(tn + fn, 1) if (tn + fn) else float("nan")
    try:
        out["cohen_kappa"] = float(cohen_kappa_score(y_true, y_pred))
    except Exception:
        out["cohen_kappa"] = float("nan")
    if y_prob is not None and len(set(y_true.tolist())) > 1:
        try:
            out["auroc_confidence"] = float(roc_auc_score(y_true, y_prob))
        except Exception:
            out["auroc_confidence"] = float("nan")
    else:
        out["auroc_confidence"] = float("nan")
    return out


def _safe_float(x):
    try:
        f = float(x)
        if np.isnan(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def bootstrap(
    results_dir: Path,
    n_bootstrap: int = 1000,
    seed: int = 42,
) -> Dict[str, dict]:
    """Run the resampling and write metrics_with_ci.json."""
    rp = pd.read_csv(results_dir / "raw_predictions.csv")
    # Restrict to successfully predicted rows (skip status='failed')
    if "status" in rp.columns:
        rp = rp[rp["status"] == "ok"]
    if len(rp) == 0:
        sys.exit("error: no successfully-predicted rows in raw_predictions.csv")

    y_true = rp["hf_gold"].astype(int).to_numpy()
    y_pred_raw = rp["llm_label"]
    # Coerce to int; rows where label is missing get dropped from this analysis
    mask = y_pred_raw.notna()
    y_true = y_true[mask.values]
    y_pred = y_pred_raw[mask].astype(int).to_numpy()
    y_prob_col = rp["llm_confidence"][mask]
    try:
        y_prob = y_prob_col.astype(float).to_numpy()
    except Exception:
        y_prob = None
    n = len(y_true)
    if n == 0:
        sys.exit("error: no labeled rows after filtering")

    # Point estimate
    point = _metric_point(y_true, y_pred, y_prob)

    rng = np.random.default_rng(seed)
    metric_names = list(point.keys())
    samples: Dict[str, list] = {m: [] for m in metric_names}
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        yt = y_true[idx]
        yp = y_pred[idx]
        yprob = y_prob[idx] if y_prob is not None else None
        m = _metric_point(yt, yp, yprob)
        for k in metric_names:
            v = m[k]
            if not np.isnan(v):
                samples[k].append(v)

    result: Dict[str, dict] = {
        "n_bootstrap": int(n_bootstrap),
        "seed": int(seed),
        "n_evaluated": int(n),
        "metrics": {},
    }
    for k, arr in samples.items():
        if not arr:
            continue
        a = np.asarray(arr, dtype=float)
        ci_lo, ci_hi = np.percentile(a, [2.5, 97.5])
        result["metrics"][k] = {
            "point": _safe_float(point[k]),
            "ci95_lo": _safe_float(ci_lo),
            "ci95_hi": _safe_float(ci_hi),
            "mean": _safe_float(a.mean()),
            "std": _safe_float(a.std(ddof=1)),
        }

    out_path = results_dir / "metrics_with_ci.json"
    out_path.write_text(json.dumps(result, indent=2))
    return result


def _print_table(result: Dict[str, dict], results_dir: Path) -> None:
    print()
    print(f"  Bootstrap 95% CI — {results_dir.name}")
    print(f"  n_evaluated={result['n_evaluated']}, n_bootstrap={result['n_bootstrap']}, seed={result['seed']}")
    print()
    print(f"    {'metric':<18} {'point':>8}  {'95% CI':>22}")
    print(f"    {'-'*18} {'-'*8}  {'-'*22}")
    for k, v in result["metrics"].items():
        point = v.get("point")
        lo, hi = v.get("ci95_lo"), v.get("ci95_hi")
        if point is None:
            continue
        ci_str = f"({lo:.3f}, {hi:.3f})" if lo is not None and hi is not None else "(–)"
        print(f"    {k:<18} {point:>8.4f}  {ci_str:>22}")
    print()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("results_dir", nargs="?", type=Path)
    p.add_argument("--auto", action="store_true",
                   help="Use the most recent results dir if no path given.")
    p.add_argument("--n-bootstrap", type=int, default=1000)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    rd = args.results_dir or (_latest_results_dir() if args.auto else None)
    if rd is None:
        sys.exit("error: pass a results dir or --auto")
    rd = Path(rd).resolve()
    result = bootstrap(rd, n_bootstrap=args.n_bootstrap, seed=args.seed)
    _print_table(result, rd)
    print(f"  wrote {rd / 'metrics_with_ci.json'}")


if __name__ == "__main__":
    main()
