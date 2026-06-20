"""Table 1 — cohort characteristics by case/control for a phenotype.

Reads the wide cohort CSV (sql/cohort_<ph>.sql output) and the feature definitions in
phenotypes.yaml, and writes a Table-1-style markdown + CSV summary (demographics,
comorbidity prevalence, lab/vital means) stratified by case vs control.

Usage:
    python pipeline/cohort_table1.py stroke
    python pipeline/cohort_table1.py stroke --cohort ~/mimic_data/cohort_stroke.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "pipeline" / "config" / "phenotypes.yaml"
TABLES_DIR = REPO_ROOT / "paper" / "tables"

PRETTY = {
    "age": "Age, years", "sex_male": "Male sex",
    "cm_htn": "Hypertension", "cm_dm": "Diabetes", "cm_afib": "Atrial fibrillation",
    "cm_ihd": "Ischemic heart disease", "cm_chf": "Heart failure",
    "cm_hld": "Hyperlipidemia", "cm_ckd": "Chronic kidney disease",
    "cm_pvd": "Peripheral vascular disease", "cm_smoke": "Smoking",
    "cm_carotid": "Carotid stenosis",
    "lab_glucose": "Glucose", "lab_hba1c": "HbA1c", "lab_ldl": "LDL", "lab_hdl": "HDL",
    "lab_chol": "Total cholesterol", "lab_trig": "Triglycerides", "lab_creat": "Creatinine",
    "lab_inr": "INR", "lab_hgb": "Hemoglobin", "lab_plt": "Platelets", "lab_wbc": "WBC",
    "lab_na": "Sodium",
    "vit_sbp": "Systolic BP", "vit_dbp": "Diastolic BP", "vit_bmi": "BMI",
    "med_aht": "Antihypertensive", "med_statin": "Statin", "med_ac": "Anticoagulant",
    "med_ap": "Antiplatelet", "med_ad": "Antidiabetic",
}


def summarize(df: pd.DataFrame, col: str, binary: bool) -> str:
    s = df[col].dropna()
    if len(s) == 0:
        return "—"
    if binary:
        return f"{int(s.sum())} ({100*s.mean():.1f}%)"
    return f"{s.mean():.1f} ± {s.std():.1f}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("phenotype")
    ap.add_argument("--cohort", type=Path, default=None)
    args = ap.parse_args(argv)

    config = yaml.safe_load(CONFIG_PATH.open())
    features = config["features"]
    cohort = args.cohort or Path.home() / "mimic_data" / f"cohort_{args.phenotype}.csv"
    df = pd.read_csv(cohort)

    cases = df[df["label"] == 1]
    controls = df[df["label"] == 0]
    rows = [("N", str(len(df)), str(len(cases)), str(len(controls)))]
    for f in features:
        name = f["name"]
        if name not in df.columns:
            continue
        # Binary = values are only {0,1} (comorbidity/med/sex flags). Declared type
        # doesn't separate these from continuous integers like age, so use the values.
        binary = set(pd.unique(df[name].dropna())) <= {0, 1}
        rows.append((
            PRETTY.get(name, name),
            summarize(df, name, binary),
            summarize(cases, name, binary),
            summarize(controls, name, binary),
        ))

    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    label = args.phenotype.replace("_", " ")
    md = [f"# Table 1 — {label} cohort characteristics (MIMIC-IV)", "",
          "Binary features: n (%). Continuous: mean ± SD. Continuous stats over measured "
          "values only (unmeasured labs/vitals are absent rather than imputed).", "",
          "| Characteristic | Overall | Cases | Controls |",
          "|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |")
    out_md = TABLES_DIR / f"table1_{args.phenotype}.md"
    out_md.write_text("\n".join(md))
    pd.DataFrame(rows, columns=["characteristic", "overall", "cases", "controls"]).to_csv(
        TABLES_DIR / f"table1_{args.phenotype}.csv", index=False)
    print(f"Wrote {out_md}")
    print("\n".join(md[4:]))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
