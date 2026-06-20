# Model specification — Heart failure identification (standardized elastic-net logistic regression)

Best hyperparameters: {'C': 0.1, 'l1_ratio': 0.8}. Intercept (log-odds): -4.447. Coefficients are on standardized numeric features and 0/1 binary features; odds ratio = exp(coefficient). `missingindicator_*` columns flag imputed values.

| Feature (standardized) | Coefficient (log-odds) | Odds ratio |
|---|---|---|
| med_aht | +1.220 | 3.386 |
| cm_ihd | +1.093 | 2.983 |
| cm_afib | +1.042 | 2.834 |
| cm_ckd | +0.840 | 2.317 |
| lab_cl | -0.446 | 0.640 |
| med_ap | +0.364 | 1.439 |
| age | +0.359 | 1.433 |
| missingindicator_lab_creat | +0.314 | 1.369 |
| lab_bun | +0.308 | 1.361 |
| cm_dm | +0.302 | 1.353 |
| lab_na | +0.300 | 1.350 |
| med_ac | +0.224 | 1.251 |
| vit_bmi | +0.213 | 1.237 |
| sex_male | -0.212 | 0.809 |
| missingindicator_lab_hco3 | -0.201 | 0.818 |
| cm_smoke | +0.169 | 1.184 |
| lab_creat | -0.163 | 0.850 |
| cm_pvd | +0.153 | 1.165 |
| missingindicator_lab_inr | -0.149 | 0.862 |
| cm_htn | +0.147 | 1.159 |
| missingindicator_lab_bun | -0.144 | 0.866 |
| med_ad | -0.138 | 0.871 |
| lab_hgb | -0.131 | 0.877 |
| missingindicator_lab_plt | +0.118 | 1.125 |
| lab_inr | +0.115 | 1.122 |
| vit_sbp | -0.110 | 0.896 |
| missingindicator_lab_cl | +0.095 | 1.100 |
| missingindicator_lab_na | -0.084 | 0.920 |
| missingindicator_lab_k | -0.077 | 0.926 |
| lab_hco3 | +0.060 | 1.062 |
| lab_plt | -0.051 | 0.950 |
| missingindicator_vit_bmi | +0.047 | 1.048 |
| lab_k | +0.033 | 1.034 |
| missingindicator_lab_hba1c | -0.031 | 0.970 |
| med_statin | +0.028 | 1.029 |
| missingindicator_vit_sbp | -0.024 | 0.976 |
| missingindicator_vit_dbp | -0.024 | 0.976 |
| missingindicator_lab_wbc | -0.018 | 0.982 |
| missingindicator_lab_hgb | +0.014 | 1.014 |
| missingindicator_lab_glucose | -0.013 | 0.987 |
| vit_dbp | -0.013 | 0.988 |
| cm_hld | -0.008 | 0.992 |
| lab_wbc | -0.003 | 0.997 |
| lab_hba1c | -0.001 | 0.999 |
| lab_glucose | +0.001 | 1.001 |