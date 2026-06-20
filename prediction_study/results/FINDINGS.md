# HF vertical slice — first rigorous results (MIMIC-IV, natural prevalence)

**Cohort:** incident heart failure (first I50 admission, with prior history) vs. never-HF
patients (≥2 admissions). One row per patient. N=90,435, 11,509 HF cases, **12.7% prevalence**
(natural — no case:control forcing, no 800 cap). Model: elastic-net logistic regression
(saga, inner-CV tuned), median imputation + missing indicators, **no SMOTE**. 30% held-out
test set. Bootstrap 95% CIs.

## Result 1 — rigorous identification (concurrent features)

Using the index (HF) admission's features: **AUROC 0.884 (95% CI 0.879–0.889)**, AUPRC 0.505
(≈4× the base rate), **calibration slope 0.99 / intercept −0.02 (near-perfect calibration)**,
Brier 0.081. This is the legitimate high number, now defensible (natural prevalence, calibrated,
tight CIs) — unlike the earlier 0.914 (forced 1:2 + SMOTE, uncalibrated).

## Result 2 — leakage / lead-time decay (the methodological centerpiece)

Sliding the feature cutoff to a hospital visit ≥N days before the HF diagnosis:

| Blackout (days) | N | ROC AUC (95% CI) | AUPRC | Calib. slope / intercept |
|---|---|---|---|---|
| 0 (concurrent) | 90,435 | 0.884 (0.879–0.889) | 0.505 | 0.99 / −0.02 |
| 30 | 77,409 | 0.814 (0.806–0.821) | 0.374 | 1.02 / 0.01 |
| 90 | 69,278 | 0.811 (0.803–0.818) | 0.380 | 1.03 / 0.05 |
| 180 | 63,098 | 0.808 (0.800–0.816) | 0.379 | 1.01 / 0.00 |

**Two findings:**
1. The concurrent→pre-onset drop is **0.076 AUROC (~9%)** — the inflation attributable to the
   acute-admission (outcome-proximal) features. Quantifying this is itself a publishable result.
2. The drop is **concentrated in the index admission and then plateaus** (30→180 days barely
   moves). Genuine pre-onset early detection is a **stable, well-calibrated AUROC ≈ 0.81** — still
   a strong, defensible number, and honest.

Both the high identification number and the honest early-detection number come out of the same
pipeline; the ablation connects them. Calibration is excellent at every time point.

## Result 3 — fixed-cohort ablation (composition confound removed)

The same 63,098 patients (those with a visit ≥180 d before onset), evaluated at every cutoff:
AUROC 0.883 (concurrent) → 0.811 (≥30 d) → 0.810 (≥90 d) → 0.808 (≥180 d), calibration slope
~1.0 throughout. Nearly identical to the full-cohort decay, so the drop is **pure feature
timing**, not cohort composition. The ~0.07 inflation is the acute-admission (leaky) signal;
genuine pre-onset detection is a stable, well-calibrated **0.81**.

## Result 4 — decision-curve analysis (clinical utility)

Net benefit on the test set, vs. treat-all / treat-none:

| Threshold | Treat-all | Concurrent model | Pre-onset model |
|---|---|---|---|
| 0.10 | 0.047 | 0.098 | 0.084 |
| 0.20 | −0.072 | 0.071 | 0.045 |
| 0.30 | −0.226 | 0.049 | 0.023 |

Both models add net benefit across the clinically relevant range; crucially the **pre-onset
model keeps positive net benefit** — clinical utility survives removal of the leaky features.

## External validation — ready now

eICU-CRD (200+ US hospitals) is **already queryable on BigQuery** under the existing PhysioNet
credentials (no DUA wait). Next: transport the MIMIC-trained concurrent identification model to
an eICU HF cohort and report calibration drift + recalibration (the main tier-mover).
