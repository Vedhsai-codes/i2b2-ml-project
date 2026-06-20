"""Aggregate i2b2-ML build results across phenotypes — retrieved THROUGH the API.

For each configured phenotype this:
  1. GETs the ML concept blob from the running stack (`GET /etl/concepts`), i.e. the
     model the tool produced — not a re-computed metric.
  2. Extracts the engine's reported metrics + retained features.
  3. Counts cases/controls from the membership CSV produced by build_cohort.py.
  4. Writes a per-phenotype receipt JSON (paper/results/<ph>_build_receipt.json) and a
     combined results table (paper/tables/results_by_phenotype.{md,csv}).

Usage (host, stack on 5005):
    python pipeline/aggregate_results.py            # all configured phenotypes
    python pipeline/aggregate_results.py stroke heart_failure
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "pipeline" / "config" / "phenotypes.yaml"
OUT_DIR = REPO_ROOT / "pipeline" / "out"
RESULTS_DIR = REPO_ROOT / "paper" / "results"
TABLES_DIR = REPO_ROOT / "paper" / "tables"

BASE_URL = "http://localhost:5005"
AUTH_USER = r"demo\demo"
AUTH_PASS = "Etl@2021"
PROJECT = "Demo"

METRIC_KEYS = ("roc_auc", "accuracy", "precision", "recall", "f1", "build_time_sec")


def load_config() -> dict:
    with CONFIG_PATH.open() as fh:
        return yaml.safe_load(fh)


def _session():
    import requests
    from requests.auth import HTTPBasicAuth

    s = requests.Session()
    s.auth = HTTPBasicAuth(AUTH_USER, AUTH_PASS)
    s.headers.update({"X-Project-Name": PROJECT, "accept": "application/json"})
    return s


def _coerce_blob(raw) -> dict | None:
    """The blob is stored as a Python-repr string; round-trip it to a dict."""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return None
    for candidate in (raw, raw.replace("'", '"')):
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def retrieve_metrics(session, phenotype: str, config: dict) -> dict:
    ph = config["phenotypes"][phenotype]
    resp = session.get(
        f"{BASE_URL}/etl/concepts", params={"hpath": ph["ml_concept_path"]}, timeout=60
    )
    out: dict = {"phenotype": phenotype, "ml_concept_path": ph["ml_concept_path"],
                 "http_status": resp.status_code}
    try:
        rows = json.loads(resp.text)
        row = rows[0] if isinstance(rows, list) and rows else rows
        blob = _coerce_blob(row.get("concept_blob")) if isinstance(row, dict) else None
        if blob:
            out["has_serialized_model"] = "serialized_model" in blob
            for k in METRIC_KEYS:
                if k in blob:
                    out[k] = blob[k]
            out["n_features_selected"] = len(blob.get("feature_column_codes", []) or [])
            out["feature_column_codes"] = blob.get("feature_column_codes", [])
    except (json.JSONDecodeError, KeyError, TypeError, IndexError) as exc:
        out["parse_error"] = str(exc)
    return out


def count_membership(phenotype: str) -> dict:
    path = OUT_DIR / f"{phenotype}_membership.csv"
    if not path.exists():
        return {}
    pos = neg = 0
    with path.open(newline="") as fh:
        for r in csv.DictReader(fh):
            if int(r["label"]) == 1:
                pos += 1
            else:
                neg += 1
    return {"n_positive": pos, "n_negative": neg, "n_patients": pos + neg}


def main(argv: list[str] | None = None) -> int:
    config = load_config()
    phenotypes = (argv or sys.argv[1:]) or list(config["phenotypes"].keys())
    session = _session()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for ph in phenotypes:
        rec = retrieve_metrics(session, ph, config)
        rec.update(count_membership(ph))
        rec["label_icd10"] = config["phenotypes"][ph]["label_icd"]["icd10"]
        (RESULTS_DIR / f"{ph}_build_receipt.json").write_text(json.dumps(rec, indent=2))
        rows.append(rec)
        auc = rec.get("roc_auc")
        print(f"  {ph:24s} AUROC={auc if auc is None else round(auc, 3)} "
              f"model={rec.get('has_serialized_model')} feats={rec.get('n_features_selected')}")

    # combined table
    cols = ["phenotype", "n_patients", "n_positive", "n_negative", "n_features_selected",
            "roc_auc", "accuracy", "precision", "recall", "f1", "build_time_sec"]
    csv_path = TABLES_DIR / "results_by_phenotype.csv"
    with csv_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    def fmt(v, nd=3):
        return "—" if v is None else (round(v, nd) if isinstance(v, float) else v)

    md = ["# i2b2-ML phenotype build results (through the JSON API)", "",
          "| Phenotype | n (cases/controls) | Features | ROC AUC | Accuracy | Precision | Recall | F1 |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(
            f"| {r['phenotype']} | {r.get('n_patients','—')} "
            f"({r.get('n_positive','—')}/{r.get('n_negative','—')}) | "
            f"{r.get('n_features_selected','—')} | {fmt(r.get('roc_auc'))} | "
            f"{fmt(r.get('accuracy'))} | {fmt(r.get('precision'))} | "
            f"{fmt(r.get('recall'))} | {fmt(r.get('f1'))} |"
        )
    md.append("")
    md.append("*Every model retrieved through `GET /etl/concepts`; built through "
              "`POST /etl/job` (`jobType:ml`). Metrics are the engine's own held-out test scores.*")
    (TABLES_DIR / "results_by_phenotype.md").write_text("\n".join(md))
    print(f"\nWrote {csv_path} and {TABLES_DIR / 'results_by_phenotype.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
