#!/usr/bin/env python
# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Render the CONSORT-style cohort-flow figure for the paper.

Reads the counts CSV produced by ``sql/cohort_flow.sql`` (run via
``bq query --use_legacy_sql=false --format=csv < sql/cohort_flow.sql``)
and renders a journal-quality flow diagram. Saves PDF + PNG to
``paper/figures/cohort_flow.{pdf,png}`` (paper/figures/ is created if
needed).

Usage::

    python evaluation/cohort_flow_figure.py --counts /tmp/cohort_flow.csv
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict


def _load_counts(p: Path) -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = {}
    with open(p) as f:
        for row in csv.DictReader(f):
            out[row["step"]] = {
                "n": int(row["n"]),
                "n_patients": int(row["n_patients"]),
            }
    return out


def render(counts_csv: Path, out_dir: Path) -> Path:
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    counts = _load_counts(counts_csv)

    def n(step):
        return counts.get(step, {}).get("n", 0)

    def n_pat(step):
        return counts.get(step, {}).get("n_patients", 0)

    boxes = [
        # (label_lines, dropped_text_or_None)
        (
            [
                "MIMIC-IV v3.1 patients",
                f"N = {n('step1_all_patients'):,}",
            ],
            None,
        ),
        (
            [
                "Adults (anchor_age ≥ 18)",
                f"N = {n_pat('step2_adults_18plus'):,} patients",
            ],
            (
                f"Excluded: {n_pat('step1_all_patients') - n_pat('step2_adults_18plus'):,} "
                f"non-adults (MIMIC-IV is adult-only; no exclusions)"
            ),
        ),
        (
            [
                "With at least one discharge note",
                f"{n('step3_with_discharge_note'):,} notes from {n_pat('step3_with_discharge_note'):,} patients",
            ],
            (
                f"Excluded: {n_pat('step2_adults_18plus') - n_pat('step3_with_discharge_note'):,} "
                f"patients without discharge notes"
            ),
        ),
        (
            [
                "Note length 500–50,000 chars",
                f"{n('step4_note_length_500_to_50000'):,} notes from {n_pat('step4_note_length_500_to_50000'):,} patients",
            ],
            (
                f"Excluded: {n('step3_with_discharge_note') - n('step4_note_length_500_to_50000'):,} "
                f"notes (blank / stub / extreme length)"
            ),
        ),
        (
            [
                "Final analysis cohort",
                f"{n('step6_final_cohort_LIMIT_1000'):,} admissions",
                f"from {n_pat('step6_final_cohort_LIMIT_1000'):,} unique patients",
            ],
            "LIMIT 1000 (ORDER BY subject_id)",
        ),
        (
            [
                f"HF positive (any ICD-10 I50.*):  {n('step7_final_HF_positive'):,} admissions",
                f"HF negative:                   {n('step7_final_HF_negative'):,} admissions",
            ],
            None,
        ),
    ]

    fig, ax = plt.subplots(figsize=(8.0, 11.0))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 12 * len(boxes))
    ax.axis("off")

    box_w = 6.0
    box_h = 1.6
    cx = 5.0
    spacing = 12  # y-axis units per row

    for i, (lines, dropped) in enumerate(boxes):
        # Box vertical position
        y_top = (len(boxes) - i) * spacing - 2
        y_center = y_top - box_h / 2

        # Main box
        box = FancyBboxPatch(
            (cx - box_w / 2, y_top - box_h),
            box_w,
            box_h,
            boxstyle="round,pad=0.18,rounding_size=0.4",
            facecolor="#f8f8f8",
            edgecolor="#222222",
            linewidth=1.4,
        )
        ax.add_patch(box)

        # Label inside box
        label = "\n".join(lines)
        ax.text(
            cx,
            y_center,
            label,
            ha="center",
            va="center",
            fontsize=11,
            family="serif",
        )

        # Excluded note to the right
        if dropped:
            ax.text(
                cx + box_w / 2 + 0.3,
                y_center,
                dropped,
                ha="left",
                va="center",
                fontsize=9,
                style="italic",
                color="#555555",
                wrap=True,
            )

        # Arrow down to next box
        if i < len(boxes) - 1:
            y_next_top = (len(boxes) - (i + 1)) * spacing - 2
            ax.annotate(
                "",
                xy=(cx, y_next_top),
                xytext=(cx, y_top - box_h - 0.05),
                arrowprops=dict(arrowstyle="->", lw=1.4, color="#222222"),
            )

    ax.set_title(
        "Cohort selection for the i2b2-ML LLM extension demonstration\n"
        "(MIMIC-IV v3.1, sql/cohort_v1.sql)",
        fontsize=12,
        family="serif",
        pad=12,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / "cohort_flow.pdf"
    png_path = out_dir / "cohort_flow.png"
    fig.tight_layout()
    fig.savefig(pdf_path, format="pdf", bbox_inches="tight")
    fig.savefig(png_path, format="png", bbox_inches="tight", dpi=200)
    plt.close(fig)
    return pdf_path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--counts", type=Path, required=True,
                   help="CSV produced by sql/cohort_flow.sql")
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("paper/figures"),
        help="Output directory (default: paper/figures)",
    )
    args = p.parse_args()
    pdf = render(args.counts, args.out_dir)
    print(f"wrote {pdf}")
    print(f"wrote {pdf.with_suffix('.png')}")


if __name__ == "__main__":
    main()
