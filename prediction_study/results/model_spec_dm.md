# Model specification — Diabetes identification (standardized elastic-net logistic regression)

Best hyperparameters: {'C': 0.1, 'l1_ratio': 0.2}. Intercept (log-odds): -3.747. Coefficients are on standardized numeric features and 0/1 binary features; odds ratio = exp(coefficient). `missingindicator_*` columns flag imputed values.

| Feature (standardized) | Coefficient (log-odds) | Odds ratio |
|---|---|---|
| med_ad | +3.686 | 39.892 |
| cm_htn | +1.089 | 2.973 |
| lab_hba1c | +0.858 | 2.358 |
| cm_hld | +0.738 | 2.093 |
| cm_ckd | +0.726 | 2.067 |
| lab_glucose | +0.504 | 1.655 |
| med_ac | -0.345 | 0.708 |
| med_aht | -0.334 | 0.716 |
| cm_ihd | +0.291 | 1.338 |
| missingindicator_lab_inr | +0.277 | 1.320 |
| cm_afib | -0.270 | 0.763 |
| missingindicator_lab_hgb | +0.254 | 1.289 |
| vit_bmi | +0.211 | 1.235 |
| missingindicator_lab_hba1c | +0.209 | 1.233 |
| lab_cl | -0.204 | 0.815 |
| lab_wbc | -0.200 | 0.819 |
| cm_pvd | +0.184 | 1.202 |
| missingindicator_lab_wbc | -0.178 | 0.837 |
| lab_hgb | -0.174 | 0.841 |
| missingindicator_lab_plt | +0.132 | 1.141 |
| lab_na | +0.127 | 1.136 |
| vit_dbp | -0.119 | 0.888 |
| vit_sbp | +0.085 | 1.089 |
| med_statin | +0.084 | 1.088 |
| missingindicator_lab_creat | +0.069 | 1.072 |
| missingindicator_vit_bmi | -0.055 | 0.947 |
| med_ap | +0.055 | 1.056 |
| missingindicator_lab_k | +0.051 | 1.053 |
| sex_male | +0.040 | 1.040 |
| age | +0.038 | 1.039 |
| missingindicator_lab_hco3 | -0.034 | 0.967 |
| lab_inr | +0.031 | 1.031 |
| lab_plt | +0.027 | 1.027 |
| lab_hco3 | +0.023 | 1.023 |
| missingindicator_lab_glucose | -0.021 | 0.979 |
| missingindicator_lab_na | -0.015 | 0.985 |
| lab_bun | +0.013 | 1.013 |
| lab_k | +0.012 | 1.012 |
| cm_smoke | +0.010 | 1.010 |
| lab_creat | -0.009 | 0.991 |
| missingindicator_lab_cl | +0.008 | 1.008 |
| missingindicator_vit_sbp | -0.007 | 0.993 |
| missingindicator_vit_dbp | -0.007 | 0.993 |
| missingindicator_lab_bun | +0.000 | 1.000 |