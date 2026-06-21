"""Faithful implementation of the AHA PREVENT (2024) base 10-year HEART FAILURE risk equation
(Khan SS et al., Circulation 2024;149:430-449), as an external reference comparator.

Sex-specific base model: age, SBP (knot 110), antihypertensive use, diabetes, current smoking,
BMI (knot 30), CKD-EPI-2021 eGFR (knot 60), and the published interactions. No lipid terms.
Coefficients verified by reproducing the paper's worked examples (F 0.081 / M 0.106).

Applied here to the pre-onset incident-HF cohort (features >=180 d before onset) — the design that
matches PREVENT's incident-prediction intent — as a published-equation reference for the CDW
harness. NB: PREVENT's 10-year ambulatory horizon and derivation population differ from this ICU
identification task, so it is a reference scale, not a competitor; we report discrimination.

Usage: python prediction_study/prevent_hf.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

SEED = 42
RESULTS = Path(__file__).resolve().parent / "results"
DATA = Path(__file__).resolve().parent / "data"

# base 10-yr HF coefficients (preventr sysdata base_10yr; verified vs paper examples)
F = dict(age=0.8998235, sbp_lt=-0.4559771, sbp_ge=0.3576505, dm=1.038346, smoke=0.583916,
         bmi_lt=-0.0072294, bmi_ge=0.2997706, egfr_lt=0.7451638, egfr_ge=0.0557087, bptx=0.3534442,
         bptx_sbp=-0.0981511, age_sbp=-0.0946663, age_dm=-0.3581041, age_smoke=-0.1159453,
         age_bmi=-0.0038780, age_egfr=-0.1884289, intercept=-4.310409)
M = dict(age=0.8972642, sbp_lt=-0.6811466, sbp_ge=0.3634461, dm=0.923776, smoke=0.5023736,
         bmi_lt=-0.0485841, bmi_ge=0.3726929, egfr_lt=0.6926917, egfr_ge=0.0251827, bptx=0.2980922,
         bptx_sbp=-0.0497731, age_sbp=-0.1289201, age_dm=-0.3040924, age_smoke=-0.1401688,
         age_bmi=0.0068126, age_egfr=-0.1797778, intercept=-3.946391)


def ckd_epi_2021(scr, age, sex_male):
    scr = np.asarray(scr, float)
    valid = np.isfinite(scr) & (scr > 0)
    scr_safe = np.where(valid, scr, 1.0)
    female = np.asarray(sex_male) == 0
    kappa = np.where(female, 0.7, 0.9); alpha = np.where(female, -0.241, -0.302)
    r = scr_safe / kappa
    e = (142.0 * np.minimum(r, 1.0) ** alpha * np.maximum(r, 1.0) ** (-1.200)
         * 0.9938 ** np.asarray(age, float) * np.where(female, 1.012, 1.0))
    return np.where(valid, e, np.nan)


def prevent_hf_risk(age, sbp, dm, smoke, bmi, egfr, bptx, sex_male):
    """Vectorized base 10-yr HF risk. Inputs are arrays; returns probability in [0,1]."""
    age = np.asarray(age, float); sbp = np.asarray(sbp, float); bmi = np.asarray(bmi, float)
    egfr = np.asarray(egfr, float); dm = np.asarray(dm, float); smoke = np.asarray(smoke, float)
    bptx = np.asarray(bptx, float); sex_male = np.asarray(sex_male)
    a = (age - 55) / 10
    sbp_lt = (np.minimum(sbp, 110) - 110) / 20
    sbp_ge = (np.maximum(sbp, 110) - 130) / 20
    bmi_lt = (np.minimum(bmi, 30) - 25) / 5
    bmi_ge = (np.maximum(bmi, 30) - 30) / 5
    egfr_lt = (np.minimum(egfr, 60) - 60) / -15
    egfr_ge = (np.maximum(egfr, 60) - 90) / -15
    out = np.empty(len(age), float)
    for c, mask in ((F, sex_male == 0), (M, sex_male == 1)):
        m = np.asarray(mask)
        lp = (c["intercept"] + c["age"] * a + c["sbp_lt"] * sbp_lt + c["sbp_ge"] * sbp_ge
              + c["dm"] * dm + c["smoke"] * smoke + c["bmi_lt"] * bmi_lt + c["bmi_ge"] * bmi_ge
              + c["egfr_lt"] * egfr_lt + c["egfr_ge"] * egfr_ge + c["bptx"] * bptx
              + c["bptx_sbp"] * bptx * sbp_ge + c["age_sbp"] * a * sbp_ge + c["age_dm"] * a * dm
              + c["age_smoke"] * a * smoke + c["age_bmi"] * a * bmi_ge + c["age_egfr"] * a * egfr_lt)
        out[m] = (1 / (1 + np.exp(-lp)))[m]
    return out


def _selftest():
    # paper worked example: age 50, SBP 160, on antihypertensive, diabetic, non-smoker, eGFR 90, BMI 35
    f = prevent_hf_risk([50], [160], [1], [0], [35], [90], [1], [0])[0]
    m = prevent_hf_risk([50], [160], [1], [0], [35], [90], [1], [1])[0]
    assert abs(f - 0.081) < 0.001, f"female example {f:.4f} != 0.081"
    assert abs(m - 0.106) < 0.001, f"male example {m:.4f} != 0.106"
    return f, m


def main():
    f, m = _selftest()
    print(f"self-test OK: female={f:.4f} (paper 0.081), male={m:.4f} (paper 0.106)")
    df = pd.read_csv(DATA / "hf_b180.csv")  # pre-onset incident HF (>=180 d before onset)
    y = df["label"].astype(int).values
    egfr = ckd_epi_2021(df["lab_creat"], df["age"], df["sex_male"])
    # PREVENT needs every input; impute missing continuous inputs with cohort medians (report coverage)
    cov = {c: round(float(df[c].notna().mean()), 3) for c in ["vit_sbp", "vit_bmi", "lab_creat"]}
    sbp = df["vit_sbp"].fillna(df["vit_sbp"].median()).values
    bmi = df["vit_bmi"].fillna(df["vit_bmi"].median()).values
    egfr = np.where(np.isfinite(egfr), egfr, np.nanmedian(egfr))
    risk = prevent_hf_risk(df["age"].values, sbp, df["cm_dm"].values, df["cm_smoke"].values,
                           bmi, egfr, df["med_aht"].values, df["sex_male"].values)
    # evaluate on the SAME 30% test split the harness used (seed 42) for a fair comparison
    idx = np.arange(len(y))
    _, te = train_test_split(idx, test_size=0.3, stratify=y, random_state=SEED)
    auc_full = roc_auc_score(y, risk)
    auc_test = roc_auc_score(y[te], risk[te])
    out = {"model": "PREVENT base 10-yr HF (published equation, faithfully implemented)",
           "cohort": "hf_b180 (pre-onset incident HF, >=180 d before onset)",
           "selftest_female": round(f, 4), "selftest_male": round(m, 4),
           "input_coverage": cov, "n": int(len(y)), "n_test": int(len(te)),
           "auroc_full": round(float(auc_full), 4), "auroc_test_split": round(float(auc_test), 4),
           "harness_preonset_auroc": 0.808, "predicted_10yr_risk_median": round(float(np.median(risk)), 4),
           "note": "PREVENT predicts 10-yr incident HF in ambulatory adults; applied here as a published "
                   "external reference on the pre-onset incident cohort. Discrimination is comparable; the "
                   "absolute risk scale is not calibrated to this ICU cohort's horizon (expected)."}
    (RESULTS / "prevent_hf.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
