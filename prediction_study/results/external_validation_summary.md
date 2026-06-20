# Multi-condition internal vs external validation (i2b2-ML phenotype models)

Identification models trained on MIMIC-IV (one row per admission, all-comers, natural prevalence,
elastic-net logistic regression, no SMOTE) and applied **frozen** to eICU-CRD (200+ US hospitals).
Each phenotype's own ICD-derived self-comorbidity is excluded to avoid label leakage; diagnostic
labs (creatinine, glucose) are kept.

| Phenotype | n (MIMIC / eICU) | Internal ROC AUC | External ROC AUC | External calib. (frozen → recalibrated) |
|---|---|---|---|---|
| Heart failure | 546k / 201k | 0.907 (0.906–0.909) | 0.758 (0.754–0.761) | 0.56 → 0.98 |
| Chronic kidney disease | 546k / 201k | 0.935 | 0.840 (0.838–0.843) | 0.38 → 0.99 |
| Diabetes | 546k / 201k | 0.933 | 0.761 (0.758–0.764) | 0.38 → 1.01 |

Internal discrimination (0.91–0.94) rivals a published 200-feature DNN HF abstract (0.93) using
30 features + logistic regression. External transport degrades honestly (cross-health-system
shift) but remains strong (0.76–0.84); calibration drifts on transport and is restored by
intercept-slope recalibration in every condition — a consistent, generalizable transportability story.

*(Diabetes = any diabetes (E08–E13/250) for clean MIMIC↔eICU label harmonization.)*