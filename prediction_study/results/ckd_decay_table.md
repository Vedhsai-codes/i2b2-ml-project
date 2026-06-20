# Chronic kidney disease leakage / lead-time decay (natural prevalence, MIMIC-IV)

Features come from the most recent hospital visit at least *blackout* days before the first CKD diagnosis (blackout 0 = the CKD admission itself = concurrent).

| Blackout (days) | N | Prevalence | ROC AUC (95% CI) | AUPRC | Calib. slope | Calib. intercept |
|---|---|---|---|---|---|---|
| 0 | 89,809 | 11.1% | 0.903 (0.898–0.908) | 0.556 | 1.03 | 0.06 |
| 30 | 76,775 | 12.1% | 0.845 (0.838–0.852) | 0.432 | 0.99 | -0.03 |
| 90 | 68,611 | 12.5% | 0.840 (0.832–0.846) | 0.428 | 1.00 | 0.01 |
| 180 | 62,460 | 12.8% | 0.838 (0.830–0.845) | 0.424 | 0.99 | -0.02 |

*Concurrent → 180-day blackout AUROC drop: 0.066 (7% of the concurrent AUROC) — the portion attributable to outcome-proximal (leaky) features. For a chronic phenotype, label=1 is newly-documented chronic kidney disease; the defining lab is kept.*