"""External validation: train the HF model on MIMIC-IV, apply (frozen) to eICU-CRD.

Reports transport discrimination + calibration drift, then the recalibration hierarchy
(intercept-only and intercept+slope logistic recalibration, fit on half of eICU and
evaluated on the other half). This is the transportability evidence.

Usage:
    python prediction_study/external_validate.py \
        --train prediction_study/data/hf_b0.csv --external prediction_study/data/hf_eicu.csv
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
FEATURES = (["age", "sex_male", "cm_htn", "cm_dm", "cm_afib", "cm_ihd", "cm_hld", "cm_ckd",
             "cm_pvd", "cm_smoke", "lab_glucose", "lab_hba1c", "lab_creat", "lab_inr", "lab_hgb",
             "lab_plt", "lab_wbc", "lab_na", "lab_k", "lab_hco3", "lab_bun", "lab_cl",
             "vit_sbp", "vit_dbp", "vit_bmi", "med_aht", "med_statin", "med_ac", "med_ap", "med_ad"])


def _logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _calib(y, p):
    lr = LogisticRegression(C=np.inf, solver="lbfgs", max_iter=1000).fit(_logit(p).reshape(-1, 1), y)
    return round(float(lr.coef_[0][0]), 3), round(float(lr.intercept_[0]), 3), round(float(brier_score_loss(y, p)), 4)


def _boot_auc(y, p, n=1000):
    rng = np.random.default_rng(SEED); idx = np.arange(len(y)); v = []
    for _ in range(n):
        b = rng.choice(idx, len(idx), replace=True)
        if 0 < y[b].sum() < len(b):
            v.append(roc_auc_score(y[b], p[b]))
    return [round(float(x), 4) for x in np.percentile(v, [2.5, 97.5])]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", required=True, type=Path)
    ap.add_argument("--external", required=True, type=Path)
    args = ap.parse_args(argv)

    tr = pd.read_csv(args.train); ex = pd.read_csv(args.external)
    feats = [f for f in FEATURES if f in tr.columns and f in ex.columns]
    binary = [c for c in feats if c.startswith(("cm_", "med_")) or c == "sex_male"]
    numeric = [c for c in feats if c not in binary]

    pre = ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median", add_indicator=True)),
                          ("sc", StandardScaler())]), numeric),
        ("bin", "passthrough", binary)])
    grid = GridSearchCV(LogisticRegression(penalty="elasticnet", solver="saga", max_iter=2000),
                        {"C": [0.1, 1.0], "l1_ratio": [0.2, 0.5, 0.8]}, scoring="roc_auc", cv=4, n_jobs=-1)
    pipe = Pipeline([("pre", pre), ("clf", grid)])
    pipe.fit(tr[feats], tr["label"].astype(int))

    yx = ex["label"].astype(int).values
    px = pipe.predict_proba(ex[feats])[:, 1]

    # frozen transport
    cs, ci, br = _calib(yx, px)
    out = {
        "train": args.train.name, "external": args.external.name,
        "n_train": len(tr), "n_external": len(ex), "external_prevalence": round(float(yx.mean()), 4),
        "frozen": {"auroc": round(float(roc_auc_score(yx, px)), 4), "auroc_ci95": _boot_auc(yx, px),
                   "auprc": round(float(average_precision_score(yx, px)), 4),
                   "calibration_slope": cs, "calibration_intercept": ci, "brier": br},
    }
    # recalibration: fit on half of eICU, evaluate on the other half
    iA, iB = train_test_split(np.arange(len(yx)), test_size=0.5, stratify=yx, random_state=SEED)
    # intercept-only: logistic with logit(p) as offset -> fit intercept only
    from scipy.optimize import minimize_scalar
    def nll(a):
        q = 1 / (1 + np.exp(-(_logit(px[iA]) + a)))
        q = np.clip(q, 1e-9, 1 - 1e-9)
        return -np.mean(yx[iA] * np.log(q) + (1 - yx[iA]) * np.log(1 - q))
    a_hat = minimize_scalar(nll).x
    p_io = 1 / (1 + np.exp(-(_logit(px[iB]) + a_hat)))
    cs_io, ci_io, br_io = _calib(yx[iB], p_io)
    # intercept + slope (Platt)
    platt = LogisticRegression(C=np.inf, solver="lbfgs", max_iter=1000).fit(_logit(px[iA]).reshape(-1, 1), yx[iA])
    p_is = platt.predict_proba(_logit(px[iB]).reshape(-1, 1))[:, 1]
    cs_is, ci_is, br_is = _calib(yx[iB], p_is)
    out["recalibration"] = {
        "intercept_only": {"calibration_slope": cs_io, "calibration_intercept": ci_io, "brier": br_io},
        "intercept_slope": {"calibration_slope": cs_is, "calibration_intercept": ci_is, "brier": br_is},
        "note": "AUROC is unchanged by recalibration; only calibration improves.",
    }
    RESULTS.mkdir(exist_ok=True)
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    from sklearn.calibration import calibration_curve
    fig, ax = plt.subplots(figsize=(5, 5))
    for p_, lab_, col in [(px[iB], "Frozen MIMIC model", "#cc4b37"),
                          (p_is, "+ recalibration", "#185FA5")]:
        ft, mp = calibration_curve(yx[iB], p_, n_bins=10, strategy="quantile")
        ax.plot(mp, ft, "o-", color=col, label=lab_, lw=2, ms=4)
    ax.plot([0, 0.5], [0, 0.5], ls=":", color="gray", label="Perfect")
    ax.set_xlabel("Predicted probability"); ax.set_ylabel("Observed HF frequency")
    ax.set_title("MIMIC-IV → eICU calibration (HF)")
    ax.legend(frameon=False, fontsize=9); ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(RESULTS / "hf_external_calibration.png", dpi=150)
    (RESULTS / "hf_external_eicu.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
