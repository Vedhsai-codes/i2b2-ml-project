"""Transform a MIMIC phenotype cohort (wide CSV) into i2b2 load files.

Given the one-row-per-patient cohort CSV produced by ``sql/cohort_<phenotype>.sql``
and the feature/label mapping in ``pipeline/config/phenotypes.yaml``, emit the three
files the i2b2-ML build pipeline consumes:

* ``<phenotype>_concepts.csv``    — header ``type,path,code`` (etl concept load)
* ``<phenotype>_facts.csv``       — header ``mrn,code,start_date,value`` (etl fact load)
* ``<phenotype>_membership.csv``  — header ``subject_id,label`` (patient-set creation)

Design notes (see pipeline/PLAN_phenotype_ml_pipeline.md):
* Every emitted fact is dated at the patient's ``index_date`` (v1 cross-sectional
  snapshot) so that, with ``time_buffer=0``, the i2b2-ML engine keeps every feature.
* Positives (label==1) additionally get a label assertion fact — the engine derives
  the temporal cutoff from the first label fact, so this is mandatory.
* Integer/binary features are emitted for every patient (always present); float
  labs/vitals are emitted only where measured (NaN cells skipped).

Usage:
    python pipeline/build_cohort.py stroke --cohort ~/mimic_data/cohort_stroke.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "pipeline" / "config" / "phenotypes.yaml"

VALID_CONCEPT_TYPES = {"integer", "float", "posinteger", "posfloat", "assertion", "string", "largestring"}
INT_TYPES = {"integer", "posinteger"}


def load_config(path: Path = CONFIG_PATH) -> dict:
    """Load and return the phenotypes config."""
    with path.open() as fh:
        return yaml.safe_load(fh)


def _validate_code(code: str) -> None:
    """Raise if a concept code violates the i2b2 loader contract (<=50, no separators)."""
    if len(code) > 50:
        raise ValueError(f"concept code '{code}' exceeds 50 chars")
    for sep in ("/", "\\", ","):
        if sep in code:
            raise ValueError(f"concept code '{code}' contains illegal separator '{sep}'")


def _fmt_value(value, ctype: str) -> str:
    """Format a feature value for the fact CSV based on its concept type."""
    if ctype in INT_TYPES:
        return str(int(round(float(value))))
    # float: keep a clean numeric string, strip trailing .0 noise
    f = float(value)
    return str(int(f)) if f.is_integer() else repr(f)


def build(
    cohort_csv: Path,
    phenotype: str,
    out_dir: Path,
    config: dict | None = None,
) -> dict:
    """Generate the three i2b2 load files for ``phenotype``.

    Args:
        cohort_csv: path to the wide one-row-per-patient cohort CSV.
        phenotype: phenotype key present in phenotypes.yaml.
        out_dir: directory to write the output CSVs into (created if needed).
        config: pre-loaded config (loaded from disk if None).

    Returns:
        Summary dict with counts.
    """
    config = config or load_config()
    if phenotype not in config["phenotypes"]:
        raise KeyError(f"Unknown phenotype '{phenotype}'. Known: {sorted(config['phenotypes'])}")
    ph = config["phenotypes"][phenotype]
    features = config["features"]
    # Per-phenotype feature exclusion: drop self-referential features that encode the
    # outcome. The comorbidity flag is derived from the SAME ICD codes that define the
    # label (e.g. cm_chf <- I50 == the heart-failure label), so leaving it in produces
    # perfect leakage (AUROC 1.0). Configured per phenotype in phenotypes.yaml.
    exclude = set(ph.get("exclude_features", []) or [])
    if exclude:
        features = [f for f in features if f["name"] not in exclude]
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(cohort_csv)
    required = {"subject_id", "index_date", "label"}
    missing_required = required - set(df.columns)
    if missing_required:
        raise ValueError(f"cohort CSV missing required columns: {sorted(missing_required)}")

    feature_names = [f["name"] for f in features]
    missing_features = [n for n in feature_names if n not in df.columns]
    if missing_features:
        raise ValueError(
            f"cohort CSV missing feature columns declared in config: {missing_features}"
        )

    # ---- concepts.csv ----
    concept_rows = []
    for f in features:
        _validate_code(f["code"])
        if f["type"] not in VALID_CONCEPT_TYPES:
            raise ValueError(f"feature '{f['name']}' has invalid type '{f['type']}'")
        concept_rows.append({"type": f["type"], "path": f["path"], "code": f["code"]})
    _validate_code(ph["label_code"])
    concept_rows.append(
        {"type": "assertion", "path": ph["label_path"], "code": ph["label_code"]}
    )
    concepts = pd.DataFrame(concept_rows, columns=["type", "path", "code"])
    concepts_path = out_dir / f"{phenotype}_concepts.csv"
    concepts.to_csv(concepts_path, index=False)

    # ---- facts.csv ----
    fact_rows: list[dict] = []
    feat_by_name = {f["name"]: f for f in features}
    for _, row in df.iterrows():
        mrn = int(row["subject_id"])
        start_date = str(row["index_date"])[:10]  # YYYY-MM-DD
        for name in feature_names:
            value = row[name]
            if pd.isna(value):
                continue  # unmeasured lab/vital -> no fact (engine fills 0)
            ctype = feat_by_name[name]["type"]
            fact_rows.append(
                {
                    "mrn": mrn,
                    "code": feat_by_name[name]["code"],
                    "start_date": start_date,
                    "value": _fmt_value(value, ctype),
                }
            )
        if int(row["label"]) == 1:
            # label assertion fact (empty value) -> marks the case + cutoff date
            fact_rows.append(
                {"mrn": mrn, "code": ph["label_code"], "start_date": start_date, "value": ""}
            )
    facts = pd.DataFrame(fact_rows, columns=["mrn", "code", "start_date", "value"])
    facts_path = out_dir / f"{phenotype}_facts.csv"
    facts.to_csv(facts_path, index=False)

    # ---- membership.csv ----
    membership = df[["subject_id", "label"]].copy()
    membership["subject_id"] = membership["subject_id"].astype(int)
    membership["label"] = membership["label"].astype(int)
    membership_path = out_dir / f"{phenotype}_membership.csv"
    membership.to_csv(membership_path, index=False)

    n_pos = int((membership["label"] == 1).sum())
    n_neg = int((membership["label"] == 0).sum())
    summary = {
        "phenotype": phenotype,
        "n_patients": len(membership),
        "n_positive": n_pos,
        "n_negative": n_neg,
        "n_concepts": len(concepts),
        "n_facts": len(facts),
        "n_label_facts": int((facts["code"] == ph["label_code"]).sum()),
        "concepts_csv": str(concepts_path),
        "facts_csv": str(facts_path),
        "membership_csv": str(membership_path),
    }
    # sanity invariants the i2b2-ML engine relies on
    assert summary["n_label_facts"] == n_pos, "every positive must have exactly one label fact"
    # every negative must have >=1 feature fact: the engine derives a negative's temporal
    # cutoff from its LAST feature fact, so a featureless negative is silently dropped.
    feature_codes = {f["code"] for f in features}
    feat_mrns = set(facts.loc[facts["code"].isin(feature_codes), "mrn"])
    neg_mrns = set(membership.loc[membership["label"] == 0, "subject_id"])
    featureless_neg = neg_mrns - feat_mrns
    assert not featureless_neg, (
        f"{len(featureless_neg)} negative patient(s) have no feature fact and would be "
        f"dropped by the engine: e.g. {sorted(featureless_neg)[:5]}"
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phenotype", help="Phenotype key from phenotypes.yaml")
    parser.add_argument("--cohort", required=True, type=Path, help="Wide cohort CSV path")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "pipeline" / "out",
        help="Output directory for the generated CSVs",
    )
    args = parser.parse_args(argv)

    summary = build(args.cohort, args.phenotype, args.out_dir)
    print("Generated i2b2 load files:")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
