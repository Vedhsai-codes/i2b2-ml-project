#!/usr/bin/env python
# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Side-by-side comparison of two (or more) eval results dirs.

Usage::

    python evaluation/compare_runs.py \
        evaluation/results/baseline_20260528T133857Z \
        evaluation/results/20260528T023141Z

Or compare baseline vs the latest LLM run automatically::

    python evaluation/compare_runs.py --auto

Produces a markdown-style comparison table on stdout (also valid
plain-text for terminal viewing) showing each provider, headline metric,
and the confusion-matrix counts. The intended use is for the paper's
results table.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional


def _load(d: Path) -> dict:
    m = json.loads((d / "metrics_summary.json").read_text())
    c = json.loads((d / "run_config.json").read_text())
    provider = c.get("config", {}).get("provider", {})
    label = f"{provider.get('name', '?')}/{provider.get('model', '?')}"
    return {
        "label": label,
        "dir": d.name,
        "git": (c.get("git_commit") or "")[:8],
        "n_total": m.get("n_total"),
        "n_processed": m.get("n_processed"),
        "n_failed": m.get("n_failed"),
        "kappa": m.get("cohen_kappa"),
        "accuracy": m.get("accuracy"),
        "sensitivity": m.get("sensitivity"),
        "specificity": m.get("specificity"),
        "ppv": m.get("ppv"),
        "npv": m.get("npv"),
        "auroc": m.get("auroc_confidence"),
        "runtime_s": m.get("total_runtime_s"),
        "cost_usd": m.get("total_cost_usd"),
        "tp": m.get("true_positive"),
        "fp": m.get("false_positive"),
        "tn": m.get("true_negative"),
        "fn": m.get("false_negative"),
    }


def _latest_runs() -> List[Path]:
    root = Path(__file__).parent / "results"
    if not root.exists():
        return []
    dirs = sorted(p for p in root.iterdir() if p.is_dir())
    # Heuristic: most recent baseline_* + most recent non-baseline
    baselines = [d for d in dirs if d.name.startswith("baseline_")]
    others = [d for d in dirs if not d.name.startswith("baseline_")]
    picks: List[Path] = []
    if baselines:
        picks.append(baselines[-1])
    if others:
        picks.append(others[-1])
    return picks


def _fmt(v, places=4):
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:.{places}f}"
    return str(v)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("results_dirs", nargs="*", type=Path)
    p.add_argument("--auto", action="store_true",
                   help="Compare the latest baseline_* against the latest LLM run.")
    args = p.parse_args()

    dirs = args.results_dirs or (_latest_runs() if args.auto else [])
    if len(dirs) < 1:
        sys.exit("error: pass at least one results dir (or use --auto)")

    runs = [_load(Path(d).resolve()) for d in dirs]

    # Column widths: pick widest label, but cap at 38
    label_w = max(min(38, len(r["label"])) for r in runs)
    label_w = max(label_w, len("provider/model"))

    def row(cols):
        return "  " + " | ".join(c.ljust(w) for c, w in cols)

    metric_w = 13

    # Header
    headers = ["provider/model"] + [f"run{i+1}" for i in range(len(runs))]
    # Actually let's use the run dir name as the column header (more useful)
    headers = ["metric".ljust(metric_w)] + [r["dir"][-16:] for r in runs]

    print()
    print("  comparison of runs:")
    for r in runs:
        print(f"    [{r['dir']}]  provider={r['label']}  git={r['git']}  n_total={r['n_total']}")
    print()

    def emit(metric_name, key, places=4, suffix=""):
        cells = [_fmt(r.get(key), places) + suffix for r in runs]
        print(f"    {metric_name.ljust(metric_w)} : " + " | ".join(c.rjust(13) for c in cells))

    print(f"    {'metric'.ljust(metric_w)} : " + " | ".join(h.rjust(13) for h in [r['dir'][-16:] for r in runs]))
    print(f"    {'-' * metric_w} : " + " | ".join("-" * 13 for _ in runs))
    emit("n_processed", "n_processed", places=0)
    emit("n_failed",    "n_failed",    places=0)
    emit("cohen_kappa", "kappa")
    emit("accuracy",    "accuracy")
    emit("sensitivity", "sensitivity")
    emit("specificity", "specificity")
    emit("PPV",         "ppv")
    emit("NPV",         "npv")
    emit("AUROC",       "auroc")
    emit("runtime_s",   "runtime_s", places=3)
    emit("cost_usd",    "cost_usd",  places=4)
    print()
    print("    confusion matrices:")
    for r in runs:
        print(f"    [{r['dir'][-16:]}]:  TP={r['tp']}  FP={r['fp']}  TN={r['tn']}  FN={r['fn']}")
    print()


if __name__ == "__main__":
    main()
