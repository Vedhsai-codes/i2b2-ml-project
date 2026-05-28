#!/usr/bin/env python
# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Pretty-print a summary of an evaluation results directory.

Useful when you've just finished a run and want a single-screen view of
what happened without grepping through 7 files.

Usage::

    python evaluation/quick_inspect.py evaluation/results/<timestamp>/
    # or omit arg to inspect the most recent run
    python evaluation/quick_inspect.py
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path


def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m" if sys.stdout.isatty() else s


def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m" if sys.stdout.isatty() else s


def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m" if sys.stdout.isatty() else s


def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m" if sys.stdout.isatty() else s


def _latest_results_dir() -> Path | None:
    root = Path(__file__).parent / "results"
    if not root.exists():
        return None
    dirs = sorted(p for p in root.iterdir() if p.is_dir())
    return dirs[-1] if dirs else None


def _pct(num, den, places=1):
    if not den:
        return "–"
    return f"{100 * num / den:.{places}f}%"


def inspect(results_dir: Path) -> None:
    if not results_dir.exists():
        sys.exit(f"error: {results_dir} does not exist")

    print()
    print(_bold(f"  Evaluation results: {results_dir.name}"))
    print(_bold(f"  {'═' * (24 + len(results_dir.name))}"))
    print()

    # ───────── reproducibility receipt ─────────
    rc_path = results_dir / "run_config.json"
    if rc_path.exists():
        rc = json.loads(rc_path.read_text())
        commit = (rc.get("git_commit") or "")[:12] or "(none)"
        dirty = " [DIRTY]" if rc.get("git_dirty") else ""
        provider = rc.get("config", {}).get("provider", {})
        print(_bold("  Reproducibility receipt"))
        print(f"    git:        {commit}{dirty}")
        print(f"    cohort:     {rc.get('cohort_path')}")
        print(f"    rows:       {rc.get('cohort_row_count')}")
        print(f"    provider:   {provider.get('name')} / {provider.get('model')}")
        print(f"    python:     {(rc.get('python') or '').split()[0]}")
        print(f"    timestamp:  {rc.get('timestamp_utc')}")
        print()

    # ───────── headline metrics ─────────
    m_path = results_dir / "metrics_summary.json"
    if m_path.exists():
        m = json.loads(m_path.read_text())
        print(_bold("  Headline metrics"))
        n_total = m.get("n_total", 0)
        n_processed = m.get("n_processed", 0)
        n_failed = m.get("n_failed", 0)
        completion_status = (
            _green(f"{n_processed}/{n_total}")
            if n_failed == 0
            else _yellow(f"{n_processed}/{n_total} ({n_failed} failed)")
        )
        print(f"    completion:    {completion_status}")
        if n_processed > 0:
            print(f"    cohen_kappa:   {m.get('cohen_kappa', 'n/a')}")
            print(f"    accuracy:      {m.get('accuracy', 'n/a')}")
            print(f"    sensitivity:   {m.get('sensitivity', 'n/a')}")
            print(f"    specificity:   {m.get('specificity', 'n/a')}")
            print(f"    PPV:           {m.get('ppv', 'n/a')}")
            print(f"    NPV:           {m.get('npv', 'n/a')}")
            print(f"    AUROC (conf):  {m.get('auroc_confidence', 'n/a')}")
        print(f"    runtime:       {m.get('total_runtime_s')}s")
        print(f"    cost:          ${m.get('total_cost_usd')}")
        print(f"    audit rows:    {m.get('audit_rows_written')}")
        print()

        if n_processed > 0:
            tp, fp = m.get("true_positive", 0), m.get("false_positive", 0)
            fn, tn = m.get("false_negative", 0), m.get("true_negative", 0)
            print(_bold("  Confusion matrix"))
            print(f"                pred_neg  pred_pos")
            print(f"    actual_neg  {tn:>8}  {fp:>8}")
            print(f"    actual_pos  {fn:>8}  {tp:>8}")
            print()

    # ───────── audit-table outcomes ─────────
    audit_path = results_dir / "audit.sqlite"
    if audit_path.exists():
        conn = sqlite3.connect(str(audit_path))
        cur = conn.cursor()
        cur.execute(
            "SELECT guardrail_outcome, COUNT(*) AS c FROM llm_audit "
            "GROUP BY guardrail_outcome ORDER BY c DESC"
        )
        rows = cur.fetchall()
        if rows:
            print(_bold("  Audit-row outcomes"))
            for outcome, n in rows:
                color = _green if outcome == "passed" else _red if outcome in ("exhausted",) else _yellow
                print(f"    {outcome:<20} {color(str(n)):>10}")
            print()
        conn.close()

    # ───────── error analysis — show up to 5 worst ─────────
    err_path = results_dir / "error_analysis.csv"
    if err_path.exists():
        with open(err_path) as f:
            errs = list(csv.DictReader(f))
        if errs:
            print(_bold(f"  Error analysis — {len(errs)} mismatched/failed rows (showing up to 5)"))
            for e in errs[:5]:
                status = e.get("status", "?")
                pred = e.get("llm_label", "-") or "-"
                gold = e.get("hf_gold", "?")
                conf = e.get("llm_confidence", "-") or "-"
                evidence = (e.get("llm_evidence") or "").replace("\n", " ")
                excerpt = (e.get("note_excerpt") or "").replace("\n", " ")
                tag = _red(status) if status == "failed" else _yellow(f"pred={pred} gold={gold}")
                print(f"    patient {e.get('subject_id'):>8} [{tag}] conf={conf}")
                print(f"      note: {excerpt[:120]}{'…' if len(excerpt) > 120 else ''}")
                if evidence:
                    print(f"      evidence: {evidence[:120]}{'…' if len(evidence) > 120 else ''}")
            if len(errs) > 5:
                print(f"    ...and {len(errs) - 5} more (see error_analysis.csv)")
            print()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "results_dir",
        nargs="?",
        type=Path,
        help="Path to a results dir. Defaults to the most recent under evaluation/results/.",
    )
    args = p.parse_args()
    results_dir = args.results_dir or _latest_results_dir()
    if results_dir is None:
        sys.exit("error: no results dir provided and none exist under evaluation/results/")
    inspect(Path(results_dir).resolve())


if __name__ == "__main__":
    main()
