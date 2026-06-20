# Model specification — Chronic kidney disease identification (standardized elastic-net logistic regression)

Best hyperparameters: {'C': 0.1, 'l1_ratio': 0.8}. Intercept (log-odds): -4.119. Coefficients are on standardized numeric features and 0/1 binary features; odds ratio = exp(coefficient). `missingindicator_*` columns flag imputed values.

| Feature (standardized) | Coefficient (log-odds) | Odds ratio |
|---|---|---|
| lab_creat | +2.146 | 8.548 |
| cm_htn | +1.182 | 3.260 |
| cm_dm | +0.680 | 1.973 |
| age | +0.486 | 1.626 |
| cm_pvd | +0.316 | 1.371 |
| med_aht | +0.292 | 1.340 |
| cm_ihd | +0.290 | 1.336 |
| cm_afib | +0.222 | 1.248 |
| lab_hgb | -0.209 | 0.812 |
| lab_bun | +0.205 | 1.227 |
| med_ad | -0.194 | 0.824 |
| med_ac | +0.187 | 1.206 |
| sex_male | +0.166 | 1.180 |
| missingindicator_lab_creat | +0.143 | 1.153 |
| cm_hld | +0.136 | 1.146 |
| med_statin | +0.116 | 1.123 |
| missingindicator_vit_bmi | -0.116 | 0.891 |
| lab_cl | +0.109 | 1.115 |
| missingindicator_lab_bun | -0.104 | 0.901 |
| med_ap | +0.102 | 1.107 |
| lab_wbc | -0.067 | 0.935 |
| lab_hco3 | +0.054 | 1.056 |
| vit_sbp | +0.054 | 1.056 |
| missingindicator_lab_glucose | -0.052 | 0.949 |
| lab_plt | -0.051 | 0.951 |
| missingindicator_vit_sbp | -0.046 | 0.955 |
| missingindicator_vit_dbp | -0.046 | 0.955 |
| vit_dbp | -0.045 | 0.956 |
| lab_k | +0.042 | 1.042 |
| lab_hba1c | +0.035 | 1.035 |
| missingindicator_lab_wbc | +0.033 | 1.034 |
| missingindicator_lab_hco3 | -0.027 | 0.974 |
| vit_bmi | +0.024 | 1.024 |
| lab_glucose | -0.022 | 0.978 |
| missingindicator_lab_na | -0.020 | 0.981 |
| missingindicator_lab_plt | +0.019 | 1.019 |
| missingindicator_lab_hba1c | -0.018 | 0.982 |
| lab_na | +0.010 | 1.010 |
| cm_smoke | -0.007 | 0.993 |
| lab_inr | -0.004 | 0.996 |
| missingindicator_lab_inr | -0.000 | 1.000 |
| missingindicator_lab_hgb | +0.000 | 1.000 |
| missingindicator_lab_k | +0.000 | 1.000 |
| missingindicator_lab_cl | +0.000 | 1.000 |