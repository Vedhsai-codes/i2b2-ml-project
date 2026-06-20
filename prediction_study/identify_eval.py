"""Internal holdout evaluation for an *identification* cohort (one row per admission,
all-comers, natural prevalence) — the design used for the headline internal AUROCs and
for the MIMIC->eICU external validation. evaluate.py is for the temporal cohorts (it
needs days_before_anchor); this is its identification-cohort counterpart.

Two modes on the SAME train/test split (SEED=42, 30% holdout, stratified):
  * full      — all 30 CDW features minus --drop (the self-comorbidity).
  * reference — only --keep features, optionally with a CKD-EPI-2021 eGFR derived from
                serum creatinine (the established-risk-factor baseline for DCA).

Saves results/<tag>.json and results/<tag>_preds.npz (y, p on the held-out test set).

Usage:
    python prediction_study/identify_eval.py --csv data/dm_mimic.csv --drop cm_dm --tag dm_id_full
    python prediction_study/identify_eval.py --csv data/ckd_mimic.csv --drop cm_ckd \
        --keep age,sex_male,cm_htn,cm_dm,vit_sbp --egfr --tag ckd_id_ref
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

SEED = 42
RESULTS = Path(__file__).resolve().parent / "results"
FEATURES = ["age", "sex_male", "cm_htn", "cm_dm", "cm_afib", "cm_ihd", "cm_hld", "cm_ckd",
            "cm_pvd", "cm_smoke", "lab_glucose", "lab_hba1c", "lab_creat", "lab_inr", "lab_hgb",
            "lab_plt", "lab_wbc", "lab_na", "lab_k", "lab_hco3", "lab_bun", "lab_cl",
            "vit_sbp", "vit_dbp", "vit_bmi", "med_aht", "med_statin", "med_ac", "med_ap", "med_ad"]


def ckd_epi_2021(scr, age, sex_male):
    """Race-free CKD-EPI 2021 eGFR (mL/min/1.73m^2) from serum creatinine (mg/dL).

    Non-positive or missing creatinine -> NaN (so the median imputer handles it; a 0
    creatinine would otherwise give 0**(negative alpha) = inf and break the fit).
    """
    scr = np.asarray(scr, dtype=float)
    valid = np.isfinite(scr) & (scr > 0)
    scr_safe = np.where(valid, scr, 1.0)  # placeholder; masked back to NaN below
    female = (np.asarray(sex_male) == 0)
    kappa = np.where(female, 0.7, 0.9)
    alpha = np.where(female, -0.241, -0.302)
    ratio = scr_safe / kappa
    egfr = (142.0 * np.minimum(ratio, 1.0) ** alpha * np.maximum(ratio, 1.0) ** (-1.200)
            * 0.9938 ** np.asarray(age, dtype=float) * np.where(female, 1.012, 1.0))
    return np.where(valid, egfr, np.nan)


def _calib(y, p):
    eps = 1e-6
    lp = np.log(np.clip(p, eps, 1 - eps) / (1 - np.clip(p, eps, 1 - eps))).reshape(-1, 1)
    lr = LogisticRegression(penalty=None, solver="lbfgs", max_iter=1000).fit(lp, y)
    return round(float(lr.coef_[0][0]), 3), round(float(lr.intercept_[0]), 3)


def _boot_auc(y, p, n=1000):
    rng = np.random.default_rng(SEED); idx = np.arange(len(y)); v = []
    for _ in range(n):
        b = rng.choice(idx, len(idx), replace=True)
        if 0 < y[b].sum() < len(b):
            v.append(roc_auc_score(y[b], p[b]))
    return [round(float(x), 4) for x in np.percentile(v, [2.5, 97.5])]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, type=Path)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--drop", default="", help="comma-separated features to exclude (self-comorbidity)")
    ap.add_argument("--keep", default="", help="restrict to this comma-separated feature subset (reference model)")
    ap.add_argument("--egfr", action="store_true", help="add a CKD-EPI-2021 eGFR feature from lab_creat")
    ap.add_argument("--max-pos", type=int, default=0,
                    help="if >0, subsample to this many positives + (neg-per-pos x) negatives "
                         "(mirrors the i2b2-ML plugin's balanced sampling, e.g. 800 with --neg-per-pos 2)")
    ap.add_argument("--neg-per-pos", type=float, default=2.0)
    args = ap.parse_args(argv)

    df = pd.read_csv(args.csv)
    if args.max_pos > 0:
        rng = np.random.default_rng(SEED)
        pos_idx = df.index[df["label"] == 1].to_numpy()
        neg_idx = df.index[df["label"] == 0].to_numpy()
        n_pos = min(args.max_pos, len(pos_idx))
        n_neg = min(int(round(n_pos * args.neg_per_pos)), len(neg_idx))
        keep = np.concatenate([rng.choice(pos_idx, n_pos, replace=False),
                               rng.choice(neg_idx, n_neg, replace=False)])
        df = df.loc[keep].reset_index(drop=True)
    if args.egfr and {"lab_creat", "age", "sex_male"}.issubset(df.columns):
        df["egfr"] = ckd_epi_2021(df["lab_creat"], df["age"], df["sex_male"])

    drop = {f for f in args.drop.split(",") if f}
    if args.keep:
        keep = args.keep.split(",")
        if args.egfr and "egfr" in df.columns and "egfr" not in keep:
            keep.append("egfr")  # --egfr means include the derived eGFR in the reference set
        feats = [f for f in keep if f in df.columns and f not in drop]
    else:
        pool = FEATURES + (["egfr"] if args.egfr else [])
        feats = [f for f in pool if f in df.columns and f not in drop]

    y = df["label"].astype(int).values
    binary = [c for c in feats if c.startswith(("cm_", "med_")) or c == "sex_male"]
    numeric = [c for c in feats if c not in binary]
    pre = ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median", add_indicator=True)),
                          ("sc", StandardScaler())]), numeric),
        ("bin", "passthrough", binary)])
    grid = GridSearchCV(LogisticRegression(penalty="elasticnet", solver="saga", max_iter=2000),
                        {"C": [0.1, 1.0], "l1_ratio": [0.2, 0.5, 0.8]}, scoring="roc_auc", cv=4, n_jobs=-1)
    pipe = Pipeline([("pre", pre), ("clf", grid)])

    Xtr, Xte, ytr, yte = train_test_split(df[feats], y, test_size=0.3, stratify=y, random_state=SEED)
    pipe.fit(Xtr, ytr)
    p = pipe.predict_proba(Xte)[:, 1]
    yte = np.asarray(yte)

    RESULTS.mkdir(exist_ok=True)
    np.savez(RESULTS / f"{args.tag}_preds.npz", y=yte, p=p)
    cs, ci = _calib(yte, p)
    out = {
        "tag": args.tag, "csv": args.csv.name, "mode": "reference" if args.keep else "full",
        "n_total": len(df), "n_test": len(yte), "prevalence": round(float(yte.mean()), 4),
        "n_features": len(feats), "features": feats,
        "auroc": round(float(roc_auc_score(yte, p)), 4), "auroc_ci95": _boot_auc(yte, p),
        "auprc": round(float(average_precision_score(yte, p)), 4),
        "brier": round(float(brier_score_loss(yte, p)), 4),
        "calibration_slope": cs, "calibration_intercept": ci,
    }
    (RESULTS / f"{args.tag}.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
