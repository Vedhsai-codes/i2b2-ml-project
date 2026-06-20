# Model audit summary (TRIPOD+AI items 8, 14, AI-3)

## Events-per-variable (EPV)

| Phenotype | Train N | Train events | Candidate predictors | EPV |
|---|---|---|---|---|
| Heart failure | 382,219 | 56,428 | 45 | 1,254 |
| Chronic kidney disease | 382,219 | 58,002 | 44 | 1,318 |
| Diabetes | 382,219 | 93,415 | 44 | 2,123 |

## Subgroup equity (largest AUROC gap across sex and age bands)

| Phenotype | Overall AUROC | Female | Male | Age <65 | Age ≥65 | Gap |
|---|---|---|---|---|---|---|
| Heart failure | 0.907 | 0.915 | 0.898 | 0.928 | 0.848 | 0.079 |
| Chronic kidney disease | 0.935 | 0.939 | 0.928 | 0.956 | 0.888 | 0.068 |
| Diabetes | 0.933 | 0.935 | 0.930 | 0.944 | 0.910 | 0.034 |

Per-phenotype detail: `model_spec_<ph>.md` (coefficients), `fairness_<ph>.md` (subgroups).