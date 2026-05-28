#!/usr/bin/env python
# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Generate Table 1 (cohort demographics) from the BigQuery-pulled CSV.

Reads the CSV produced by ``sql/demographics.sql`` (one row per
admission), computes a paper-ready Table 1 stratified by ``hf_gold``,
and writes:

    paper/tables/table1_demographics.csv  (tidy long-form for further analysis)
    paper/tables/table1_demographics.md   (Markdown, copy-paste into manuscript)

For continuous variables (age, length of stay), reports median (IQR).
For categorical, reports n (%). Two-group comparison: Mann-Whitney U
for continuous, chi-square (or Fisher exact when expected count < 5)
for categorical.

The 'unit' of analysis is per-admission (one row = one discharge note);
the cohort has 1000 admissions from 452 distinct patients. This matches
the analysis units used by the eval harness + baseline LogReg.

Usage::

    python evaluation/demographics_table.py \
        --csv ~/mimic_data/cohort_demographics.csv \
        --out-dir paper/tables
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy import stats


def _fmt_median_iqr(series: pd.Series) -> str:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) == 0:
        return "—"
    med, q1, q3 = s.median(), s.quantile(0.25), s.quantile(0.75)
    return f"{med:.1f} ({q1:.1f}–{q3:.1f})"


def _fmt_n_pct(numer: int, denom: int) -> str:
    if denom == 0:
        return "—"
    return f"{numer} ({100 * numer / denom:.1f}%)"


def _p_mannwhitney(a: pd.Series, b: pd.Series) -> float:
    a = pd.to_numeric(a, errors="coerce").dropna()
    b = pd.to_numeric(b, errors="coerce").dropna()
    if len(a) == 0 or len(b) == 0:
        return float("nan")
    try:
        return float(stats.mannwhitneyu(a, b, alternative="two-sided").pvalue)
    except Exception:
        return float("nan")


def _p_categorical(table: np.ndarray) -> Tuple[float, str]:
    """Returns (p, test_used)."""
    try:
        chi2, p, dof, exp = stats.chi2_contingency(table, correction=False)
        # Fisher when expected count < 5 in any cell, but only for 2x2
        if exp.min() < 5 and table.shape == (2, 2):
            _, p_fisher = stats.fisher_exact(table)
            return float(p_fisher), "Fisher"
        return float(p), "chi2"
    except Exception:
        return float("nan"), "—"


def _fmt_p(p: float) -> str:
    if p is None or np.isnan(p):
        return "—"
    if p < 0.001:
        return "<0.001"
    return f"{p:.3f}"


def build_table1(df: pd.DataFrame) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    hf_pos = df[df["hf_gold"] == 1]
    hf_neg = df[df["hf_gold"] == 0]
    n_pos, n_neg = len(hf_pos), len(hf_neg)

    def header(label):
        rows.append({"Variable": label, "HF+ (n=" + str(n_pos) + ")": "", "HF– (n=" + str(n_neg) + ")": "", "p": ""})

    def row(label, pos_val, neg_val, p):
        rows.append({
            "Variable": label,
            "HF+ (n=" + str(n_pos) + ")": pos_val,
            "HF– (n=" + str(n_neg) + ")": neg_val,
            "p": p,
        })

    # ── Demographics ──
    header("Demographics")
    p_age = _p_mannwhitney(hf_pos["age"], hf_neg["age"])
    row("Age, years, median (IQR)", _fmt_median_iqr(hf_pos["age"]), _fmt_median_iqr(hf_neg["age"]), _fmt_p(p_age))

    # Sex
    pos_f = (hf_pos["gender"] == "F").sum()
    neg_f = (hf_neg["gender"] == "F").sum()
    p_sex, _ = _p_categorical(np.array([[pos_f, n_pos - pos_f], [neg_f, n_neg - neg_f]]))
    row("Female, n (%)", _fmt_n_pct(pos_f, n_pos), _fmt_n_pct(neg_f, n_neg), _fmt_p(p_sex))

    # Race (top categories + Other)
    header("Race / ethnicity")
    race_top = ["WHITE", "BLACK/AFRICAN AMERICAN", "HISPANIC/LATINO", "ASIAN"]
    for race_val in race_top:
        pos = hf_pos["race"].str.startswith(race_val, na=False).sum()
        neg = hf_neg["race"].str.startswith(race_val, na=False).sum()
        p, _ = _p_categorical(np.array([[pos, n_pos - pos], [neg, n_neg - neg]]))
        label = race_val.title().replace("African American", "African American")
        row(label, _fmt_n_pct(pos, n_pos), _fmt_n_pct(neg, n_neg), _fmt_p(p))
    # Other
    pos_other = n_pos - sum(hf_pos["race"].str.startswith(r, na=False).sum() for r in race_top)
    neg_other = n_neg - sum(hf_neg["race"].str.startswith(r, na=False).sum() for r in race_top)
    p, _ = _p_categorical(np.array([[pos_other, n_pos - pos_other], [neg_other, n_neg - neg_other]]))
    row("Other / unknown", _fmt_n_pct(pos_other, n_pos), _fmt_n_pct(neg_other, n_neg), _fmt_p(p))

    # ── Admission characteristics ──
    header("Admission characteristics")
    p_los = _p_mannwhitney(hf_pos["los_days"], hf_neg["los_days"])
    row("Length of stay, days, median (IQR)", _fmt_median_iqr(hf_pos["los_days"]), _fmt_median_iqr(hf_neg["los_days"]), _fmt_p(p_los))

    pos_icu = (hf_pos["had_icu_stay"] == 1).sum()
    neg_icu = (hf_neg["had_icu_stay"] == 1).sum()
    p, _ = _p_categorical(np.array([[pos_icu, n_pos - pos_icu], [neg_icu, n_neg - neg_icu]]))
    row("ICU stay during admission", _fmt_n_pct(pos_icu, n_pos), _fmt_n_pct(neg_icu, n_neg), _fmt_p(p))

    pos_die = (hf_pos["died_inhospital"] == 1).sum()
    neg_die = (hf_neg["died_inhospital"] == 1).sum()
    p, _ = _p_categorical(np.array([[pos_die, n_pos - pos_die], [neg_die, n_neg - neg_die]]))
    row("Died during admission", _fmt_n_pct(pos_die, n_pos), _fmt_n_pct(neg_die, n_neg), _fmt_p(p))

    # ── Insurance / admission type ──
    header("Insurance / admission type")
    for ins_val in ["Medicare", "Medicaid", "Private", "Other"]:
        pos = (hf_pos["insurance"] == ins_val).sum()
        neg = (hf_neg["insurance"] == ins_val).sum()
        p, _ = _p_categorical(np.array([[pos, n_pos - pos], [neg, n_neg - neg]]))
        row(ins_val, _fmt_n_pct(pos, n_pos), _fmt_n_pct(neg, n_neg), _fmt_p(p))

    pos_em = (hf_pos["admission_type"].str.contains("EMER", case=False, na=False)).sum()
    neg_em = (hf_neg["admission_type"].str.contains("EMER", case=False, na=False)).sum()
    p, _ = _p_categorical(np.array([[pos_em, n_pos - pos_em], [neg_em, n_neg - neg_em]]))
    row("Emergency admission", _fmt_n_pct(pos_em, n_pos), _fmt_n_pct(neg_em, n_neg), _fmt_p(p))

    # ── Comorbidities (ICD-10 based, this admission) ──
    header("Comorbidities (this admission)")
    comorbidities = [
        ("Diabetes mellitus (any)", "dm_any"),
        ("Hypertension", "htn"),
        ("Chronic kidney disease", "ckd"),
        ("COPD", "copd"),
        ("Atrial fibrillation", "afib"),
        ("Ischemic heart disease", "ihd"),
        ("Stroke", "stroke"),
    ]
    for label, col in comorbidities:
        pos = (hf_pos[col] == 1).sum()
        neg = (hf_neg[col] == 1).sum()
        p, _ = _p_categorical(np.array([[pos, n_pos - pos], [neg, n_neg - neg]]))
        row(label, _fmt_n_pct(pos, n_pos), _fmt_n_pct(neg, n_neg), _fmt_p(p))

    return rows


def write_outputs(rows: List[Dict[str, str]], out_dir: Path) -> Tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)

    csv_path = out_dir / "table1_demographics.csv"
    df.to_csv(csv_path, index=False)

    # Markdown table — headers from df.columns
    md_lines: List[str] = []
    md_lines.append("# Table 1. Cohort demographics and clinical characteristics")
    md_lines.append("")
    md_lines.append("Stratified by HF gold-standard (ICD-10 I50.*). Continuous: median (IQR). Categorical: n (%).")
    md_lines.append("Two-group comparisons: Mann–Whitney U (continuous), chi-square or Fisher exact (categorical).")
    md_lines.append("")
    md_lines.append("| " + " | ".join(df.columns) + " |")
    md_lines.append("|" + "|".join(["---"] * len(df.columns)) + "|")
    for _, r in df.iterrows():
        cells = [r[c] for c in df.columns]
        # bold section headers
        if cells[1] == "" and cells[2] == "" and cells[3] == "":
            cells = [f"**{cells[0]}**"] + cells[1:]
        md_lines.append("| " + " | ".join(cells) + " |")

    md_path = out_dir / "table1_demographics.md"
    md_path.write_text("\n".join(md_lines) + "\n")
    return csv_path, md_path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--csv",
        type=Path,
        required=True,
        help="Path to the demographics CSV from sql/demographics.sql",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("paper/tables"),
        help="Output directory (default: paper/tables)",
    )
    args = p.parse_args()

    df = pd.read_csv(args.csv)
    rows = build_table1(df)
    csv_path, md_path = write_outputs(rows, args.out_dir)
    print(f"wrote {csv_path}")
    print(f"wrote {md_path}")
    print()
    # Echo the Markdown to stdout so you can see it immediately
    print(md_path.read_text())


if __name__ == "__main__":
    main()
