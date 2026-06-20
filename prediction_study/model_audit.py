"""TRIPOD+AI gap-closers for the identification models (HF / CKD / diabetes).

For each phenotype it refits the exact model from identify_eval.py (same split, seed 42)
and emits three reviewer-expected artifacts:
  * model specification  — standardized elastic-net coefficients + odds ratios  [TRIPOD item 14]
  * events-per-variable  — EPV with the events/candidate-predictor count         [TRIPOD item 8]
  * subgroup performance — AUROC + calibration + prevalence by sex and age band  [TRIPOD+AI AI-3]

Writes results/model_spec_<ph>.md, results/fairness_<ph>.md, results/epv.json, and a combined
results/model_audit_summary.md.

Usage: python prediction_study/model_audit.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

SEED = 42
RESULTS = Path(__file__).resolve().parent / "results"
DATA = Path(__file__).resolve().parent / "data"
FEATURES = ["age", "sex_male", "cm_htn", "cm_dm", "cm_afib", "cm_ihd", "cm_hld", "cm_ckd",
            "cm_pvd", "cm_smoke", "lab_glucose", "lab_hba1c", "lab_creat", "lab_inr", "lab_hgb",
            "lab_plt", "lab_wbc", "lab_na", "lab_k", "lab_hco3", "lab_bun", "lab_cl",
            "vit_sbp", "vit_dbp", "vit_bmi", "med_aht", "med_statin", "med_ac", "med_ap", "med_ad"]

PHENOTYPES = [
    ("hf", "Heart failure", "data/hf_mimic_identify.csv", []),
    ("ckd", "Chronic kidney disease", "data/ckd_mimic.csv", ["cm_ckd"]),
    ("dm", "Diabetes", "data/dm_mimic.csv", ["cm_dm"]),
]


def _calib_slope(y, p):
    eps = 1e-6
    lp = np.log(np.clip(p, eps, 1 - eps) / (1 - np.clip(p, eps, 1 - eps))).reshape(-1, 1)
    return float(LogisticRegression(penalty=None, solver="lbfgs", max_iter=1000).fit(lp, y).coef_[0][0])


def _boot_auc(y, p, n=300):
    rng = np.random.default_rng(SEED); idx = np.arange(len(y)); v = []
    for _ in range(n):
        b = rng.choice(idx, len(idx), replace=True)
        if 0 < y[b].sum() < len(b):
            v.append(roc_auc_score(y[b], p[b]))
    return [round(float(x), 3) for x in np.percentile(v, [2.5, 97.5])] if v else [float("nan")] * 2


def fit_phenotype(key, label, csv, drop):
    df = pd.read_csv(DATA.parent / csv)
    feats = [f for f in FEATURES if f in df.columns and f not in drop]
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

    # ---- coefficients (TRIPOD item 14) ----
    names = list(pipe.named_steps["pre"].get_feature_names_out())
    coefs = pipe.named_steps["clf"].best_estimator_.coef_[0]
    intercept = float(pipe.named_steps["clf"].best_estimator_.intercept_[0])
    rows = sorted(zip(names, coefs), key=lambda t: -abs(t[1]))
    spec = [f"# Model specification — {label} identification (standardized elastic-net logistic regression)",
            "",
            f"Best hyperparameters: {pipe.named_steps['clf'].best_params_}. Intercept (log-odds): "
            f"{intercept:.3f}. Coefficients are on standardized numeric features and 0/1 binary features;"
            f" odds ratio = exp(coefficient). `missingindicator_*` columns flag imputed values.",
            "",
            "| Feature (standardized) | Coefficient (log-odds) | Odds ratio |",
            "|---|---|---|"]
    nonzero = 0
    for nm, c in rows:
        if abs(c) > 1e-8:
            nonzero += 1
        nm_clean = nm.replace("num__", "").replace("bin__", "")
        spec.append(f"| {nm_clean} | {c:+.3f} | {np.exp(c):.3f} |")
    (RESULTS / f"model_spec_{key}.md").write_text("\n".join(spec))

    # ---- EPV (TRIPOD item 8) ----
    n_pos_tr = int(ytr.sum())
    n_params = len(coefs)
    epv = {"phenotype": key, "n_train": int(len(ytr)), "n_train_events": n_pos_tr,
           "n_candidate_params": int(n_params), "n_nonzero_coefs": int(nonzero),
           "epv_candidate": round(n_pos_tr / n_params, 1),
           "epv_nonzero": round(n_pos_tr / max(nonzero, 1), 1)}

    # ---- subgroup fairness (TRIPOD+AI AI-3) ----
    Xte = Xte.reset_index(drop=True)
    groups = {
        "Overall": np.ones(len(yte), bool),
        "Female": (Xte["sex_male"].values == 0),
        "Male": (Xte["sex_male"].values == 1),
        "Age <65": (Xte["age"].values < 65),
        "Age ≥65": (Xte["age"].values >= 65),
    }
    fr = [f"# Subgroup performance — {label} identification (held-out test, by sex and age)",
          "",
          "| Subgroup | N | Prevalence | ROC AUC (95% CI) | Calibration slope |",
          "|---|---|---|---|---|"]
    fair_rows = {}
    for gname, mask in groups.items():
        yy, pp = yte[mask], p[mask]
        if yy.sum() < 10 or (yy == 0).sum() < 10:
            fr.append(f"| {gname} | {int(mask.sum())} | — | (too few events) | — |")
            continue
        auc = roc_auc_score(yy, pp); ci = _boot_auc(yy, pp); slope = _calib_slope(yy, pp)
        fr.append(f"| {gname} | {int(mask.sum()):,} | {yy.mean():.1%} | {auc:.3f} ({ci[0]:.3f}–{ci[1]:.3f}) | {slope:.2f} |")
        fair_rows[gname] = {"n": int(mask.sum()), "prevalence": round(float(yy.mean()), 4),
                            "auroc": round(float(auc), 4), "auroc_ci95": ci, "calib_slope": round(slope, 3)}
    # equity gap = max-min subgroup AUROC across sex and age (excluding Overall)
    subs = {k: v["auroc"] for k, v in fair_rows.items() if k != "Overall"}
    gap = round(max(subs.values()) - min(subs.values()), 3) if subs else None
    fr.append("")
    fr.append(f"*Largest between-subgroup AUROC gap (sex/age): {gap}.*")
    (RESULTS / f"fairness_{key}.md").write_text("\n".join(fr))

    return {"key": key, "label": label, "overall_auroc": round(float(roc_auc_score(yte, p)), 4),
            "epv": epv, "fairness": fair_rows, "fairness_gap": gap}


def main():
    RESULTS.mkdir(exist_ok=True)
    out = [fit_phenotype(*ph) for ph in PHENOTYPES]
    (RESULTS / "epv.json").write_text(json.dumps([o["epv"] for o in out], indent=2))
    summ = ["# Model audit summary (TRIPOD+AI items 8, 14, AI-3)", "",
            "## Events-per-variable (EPV)", "",
            "| Phenotype | Train N | Train events | Candidate predictors | EPV |",
            "|---|---|---|---|---|"]
    for o in out:
        e = o["epv"]
        summ.append(f"| {o['label']} | {e['n_train']:,} | {e['n_train_events']:,} | {e['n_candidate_params']} | {e['epv_candidate']:,.0f} |")
    summ += ["", "## Subgroup equity (largest AUROC gap across sex and age bands)", "",
             "| Phenotype | Overall AUROC | Female | Male | Age <65 | Age ≥65 | Gap |",
             "|---|---|---|---|---|---|---|"]
    for o in out:
        f = o["fairness"]
        g = lambda k: f"{f[k]['auroc']:.3f}" if k in f else "—"
        summ.append(f"| {o['label']} | {o['overall_auroc']:.3f} | {g('Female')} | {g('Male')} | "
                    f"{g('Age <65')} | {g('Age ≥65')} | {o['fairness_gap']} |")
    summ += ["", "Per-phenotype detail: `model_spec_<ph>.md` (coefficients), `fairness_<ph>.md` (subgroups)."]
    (RESULTS / "model_audit_summary.md").write_text("\n".join(summ))
    print("\n".join(summ))


if __name__ == "__main__":
    main()
