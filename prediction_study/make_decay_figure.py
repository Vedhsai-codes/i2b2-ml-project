"""Assemble the leakage / lead-time decay curve from per-blackout eval results.

Reads prediction_study/results/<prefix>_b{0,30,90,180}.json and writes:
  - results/<prefix>_decay_table.md   (AUROC/AUPRC/N/calibration by blackout)
  - results/<prefix>_decay.png        (AUROC with 95% CI vs. days before onset)

Usage:
    python prediction_study/make_decay_figure.py                       # HF (default)
    python prediction_study/make_decay_figure.py --prefix ckd \
        --label "chronic kidney disease" --short CKD
    python prediction_study/make_decay_figure.py --prefix dm \
        --label "diabetes" --short diabetes
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS = Path(__file__).resolve().parent / "results"
BLACKOUTS = [0, 30, 90, 180]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="hf", help="eval-tag prefix (hf/ckd/dm)")
    ap.add_argument("--label", default="heart failure", help="disease name for the title/prose")
    ap.add_argument("--short", default="HF", help="short label for the diagnosis anchor")
    args = ap.parse_args(argv)
    prefix, label, short = args.prefix, args.label, args.short

    rows = []
    for b in BLACKOUTS:
        f = RESULTS / f"{prefix}_b{b}.json"
        if not f.exists():
            continue
        rows.append((b, json.loads(f.read_text())))
    if not rows:
        raise SystemExit(f"no {prefix}_b*.json results found in {RESULTS}")

    # table
    md = [f"# {label.capitalize()} leakage / lead-time decay (natural prevalence, MIMIC-IV)", "",
          f"Features come from the most recent hospital visit at least *blackout* days before "
          f"the first {short} diagnosis (blackout 0 = the {short} admission itself = concurrent).", "",
          "| Blackout (days) | N | Prevalence | ROC AUC (95% CI) | AUPRC | Calib. slope | Calib. intercept |",
          "|---|---|---|---|---|---|---|"]
    for b, r in rows:
        ci = r["auroc_ci95"]
        md.append(f"| {b} | {r['n_total']:,} | {r['prevalence']:.1%} | "
                  f"{r['auroc']:.3f} ({ci[0]:.3f}–{ci[1]:.3f}) | {r['auprc']:.3f} | "
                  f"{r['calibration_slope']:.2f} | {r['calibration_intercept']:.2f} |")
    if len(rows) >= 2:
        drop = rows[0][1]["auroc"] - rows[-1][1]["auroc"]
        chronic = (f" For a chronic phenotype, label=1 is newly-documented {label}; the defining "
                   f"lab is kept.") if prefix in ("ckd", "dm") else ""
        md.append("")
        md.append(f"*Concurrent → {rows[-1][0]}-day blackout AUROC drop: "
                  f"{drop:.3f} ({drop / rows[0][1]['auroc']:.0%} of the concurrent AUROC) — "
                  f"the portion attributable to outcome-proximal (leaky) features.{chronic}*")
    (RESULTS / f"{prefix}_decay_table.md").write_text("\n".join(md))

    # figure
    xs = [b for b, _ in rows]
    aurocs = [r["auroc"] for _, r in rows]
    los = [r["auroc_ci95"][0] for _, r in rows]
    his = [r["auroc_ci95"][1] for _, r in rows]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(xs, aurocs, "o-", color="#185FA5", lw=2, label="ROC AUC")
    ax.fill_between(xs, los, his, color="#185FA5", alpha=0.15, label="95% CI")
    ax.axhline(0.5, ls=":", color="gray", lw=1)
    for x, a in zip(xs, aurocs):
        ax.annotate(f"{a:.3f}", (x, a), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=9)
    ax.set_xlabel(f"Feature blackout window before {short} diagnosis (days)")
    ax.set_ylabel("ROC AUC (held-out test)")
    ax.set_title(f"{label.capitalize()} detection: AUROC vs. feature recency (MIMIC-IV)")
    ax.set_ylim(0.5, 1.0)
    ax.set_xticks(xs)
    ax.legend(frameon=False, loc="upper right")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(RESULTS / f"{prefix}_decay.png", dpi=150)
    print("\n".join(md))
    print(f"\nWrote {RESULTS / f'{prefix}_decay_table.md'} and {RESULTS / f'{prefix}_decay.png'}")


if __name__ == "__main__":
    main()
