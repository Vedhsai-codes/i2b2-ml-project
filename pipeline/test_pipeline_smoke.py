"""Cheap LOCAL verification of the cohort -> i2b2 CSV transform.

No DB, no network, no BigQuery. Builds a tiny synthetic wide cohort, runs
``build_cohort.build``, and asserts the generated concept/fact/membership CSVs
satisfy the i2b2 loader contract and the i2b2-ML engine's invariants.

Run:  python -m pytest pipeline/test_pipeline_smoke.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pipeline import build_cohort, render_cohort_sql  # noqa: E402

VALID_FACT_TYPES_FOR_VALUE = {"integer", "float"}


@pytest.fixture
def config():
    return build_cohort.load_config()


@pytest.fixture
def synthetic_cohort(tmp_path, config):
    """Write a 6-patient synthetic stroke cohort (wide) and return its path."""
    feature_names = [f["name"] for f in config["features"]]
    rows = []
    for i in range(6):
        label = 1 if i < 2 else 0  # 2 positives, 4 negatives
        row = {"subject_id": 90000 + i, "index_date": "2150-06-01", "label": label}
        for name in feature_names:
            if name.startswith(("cm_", "med_", "sex_")):
                row[name] = i % 2            # binary
            elif name == "age":
                row[name] = 60 + i
            elif name.startswith(("lab_", "vit_")):
                # leave some labs missing to exercise NaN-skipping
                row[name] = None if (i == 3 and name == "lab_ldl") else round(10.0 + i, 1)
            else:
                row[name] = 0
        rows.append(row)
    df = pd.DataFrame(rows)
    path = tmp_path / "cohort_stroke.csv"
    df.to_csv(path, index=False)
    return path


def test_render_stroke_sql_has_no_placeholders(config):
    sql = render_cohort_sql.render("stroke", config)
    assert "@@" not in sql
    assert "I63%" in sql and "I64%" in sql            # label codes injected
    assert "physionet-data.mimiciv_3_1_hosp" in sql


def test_build_emits_three_files(tmp_path, synthetic_cohort, config):
    summary = build_cohort.build(synthetic_cohort, "stroke", tmp_path, config)
    for key in ("concepts_csv", "facts_csv", "membership_csv"):
        assert Path(summary[key]).exists()
    assert summary["n_patients"] == 6
    assert summary["n_positive"] == 2
    assert summary["n_negative"] == 4


def test_concepts_csv_contract(tmp_path, synthetic_cohort, config):
    build_cohort.build(synthetic_cohort, "stroke", tmp_path, config)
    concepts = pd.read_csv(tmp_path / "stroke_concepts.csv")
    assert list(concepts.columns) == ["type", "path", "code"]
    # every concept type is loader-legal
    assert set(concepts["type"]) <= build_cohort.VALID_CONCEPT_TYPES
    # codes <=50 chars, no separators
    for code in concepts["code"]:
        assert len(code) <= 50 and not any(s in code for s in ("/", "\\", ","))
    # the label concept exists and is an assertion
    label_row = concepts[concepts["code"] == "STROKE"]
    assert len(label_row) == 1 and label_row.iloc[0]["type"] == "assertion"
    # paths are forward-slash, leading slash
    assert all(p.startswith("/") for p in concepts["path"])


def test_facts_csv_contract_and_engine_invariants(tmp_path, synthetic_cohort, config):
    summary = build_cohort.build(synthetic_cohort, "stroke", tmp_path, config)
    facts = pd.read_csv(tmp_path / "stroke_facts.csv", keep_default_na=False)
    assert list(facts.columns) == ["mrn", "code", "start_date", "value"]

    # INVARIANT 1: every positive has exactly one label fact (engine cutoff source)
    assert summary["n_label_facts"] == summary["n_positive"]
    label_facts = facts[facts["code"] == "STROKE"]
    assert (label_facts["value"] == "").all()         # assertion -> empty value
    assert set(label_facts["mrn"]) == {90000, 90001}  # the 2 positives

    # INVARIANT 2: every patient (incl. negatives) has >=1 feature fact
    feat_codes = {f["code"] for f in config["features"]}
    feat_facts = facts[facts["code"].isin(feat_codes)]
    assert set(feat_facts["mrn"]) == set(range(90000, 90006))

    # dates are YYYY-MM-DD
    assert (facts["start_date"].str.match(r"^\d{4}-\d{2}-\d{2}$")).all()

    # NaN labs were skipped (patient 90003 has no lab_ldl fact)
    ldl_facts = facts[facts["code"] == "LAB_LDL"]
    assert 90003 not in set(ldl_facts["mrn"])


def test_membership_csv_contract(tmp_path, synthetic_cohort, config):
    build_cohort.build(synthetic_cohort, "stroke", tmp_path, config)
    membership = pd.read_csv(tmp_path / "stroke_membership.csv")
    assert list(membership.columns) == ["subject_id", "label"]
    assert set(membership["label"]) <= {0, 1}
    assert len(membership) == 6


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
