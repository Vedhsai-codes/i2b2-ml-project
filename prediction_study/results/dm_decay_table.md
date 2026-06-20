# Diabetes leakage / lead-time decay (natural prevalence, MIMIC-IV)

Features come from the most recent hospital visit at least *blackout* days before the first diabetes diagnosis (blackout 0 = the diabetes admission itself = concurrent).

| Blackout (days) | N | Prevalence | ROC AUC (95% CI) | AUPRC | Calib. slope | Calib. intercept |
|---|---|---|---|---|---|---|
| 0 | 79,152 | 7.8% | 0.856 (0.846–0.866) | 0.501 | 1.02 | 0.02 |
| 30 | 67,265 | 8.4% | 0.732 (0.721–0.745) | 0.234 | 1.05 | 0.12 |
| 90 | 60,083 | 8.7% | 0.730 (0.716–0.743) | 0.234 | 1.03 | 0.06 |
| 180 | 54,679 | 8.9% | 0.718 (0.703–0.731) | 0.230 | 1.00 | -0.01 |

*Concurrent → 180-day blackout AUROC drop: 0.139 (16% of the concurrent AUROC) — the portion attributable to outcome-proximal (leaky) features. For a chronic phenotype, label=1 is newly-documented diabetes; the defining lab is kept.*