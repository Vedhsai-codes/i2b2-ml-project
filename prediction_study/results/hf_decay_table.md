# HF leakage / lead-time decay (natural prevalence, MIMIC-IV)

Features come from the most recent hospital visit at least *blackout* days before the first HF diagnosis (blackout 0 = the HF admission itself = concurrent).

| Blackout (days) | N | Prevalence | ROC AUC (95% CI) | AUPRC | Calib. slope | Calib. intercept |
|---|---|---|---|---|---|---|
| 0 | 90,435 | 12.7% | 0.884 (0.879–0.889) | 0.505 | 0.99 | -0.02 |
| 30 | 77,409 | 13.8% | 0.814 (0.806–0.821) | 0.374 | 1.02 | 0.01 |
| 90 | 69,278 | 14.0% | 0.811 (0.803–0.818) | 0.380 | 1.03 | 0.05 |
| 180 | 63,098 | 14.2% | 0.808 (0.800–0.816) | 0.379 | 1.01 | 0.00 |

*Concurrent → 180-day blackout AUROC drop: 0.076 (9% of the concurrent AUROC) — the portion attributable to outcome-proximal (leaky) features.*