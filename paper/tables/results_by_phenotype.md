# i2b2-ML phenotype build results (through the JSON API)

| Phenotype | n (cases/controls) | Features | ROC AUC | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|
| stroke | 2400 (800/1600) | 16 | 0.891 | 0.811 | 0.686 | 0.792 | 0.736 |
| heart_failure | 2400 (800/1600) | 16 | 0.914 | 0.842 | 0.734 | 0.824 | 0.776 |
| ischemic_heart_disease | 2400 (800/1600) | 16 | 0.893 | 0.807 | 0.659 | 0.872 | 0.751 |
| ascvd | 2400 (800/1600) | 15 | 0.91 | 0.834 | 0.719 | 0.827 | 0.769 |
| dyslipidemia | 2400 (800/1600) | 16 | 0.895 | 0.824 | 0.686 | 0.869 | 0.767 |
| hypertension | 2400 (800/1600) | 16 | 0.899 | 0.832 | 0.693 | 0.892 | 0.78 |
| chronic_kidney_disease | 2400 (800/1600) | 16 | 0.946 | 0.896 | 0.841 | 0.849 | 0.845 |
| type2_diabetes | 2400 (800/1600) | 16 | 0.931 | 0.875 | 0.809 | 0.815 | 0.812 |
| obstructive_sleep_apnea | 2400 (800/1600) | 16 | 0.767 | 0.656 | 0.49 | 0.809 | 0.61 |
| prediabetes | 2400 (800/1600) | 16 | 0.797 | 0.76 | 0.629 | 0.666 | 0.647 |
| asthma | 2400 (800/1600) | 16 | 0.658 | 0.558 | 0.413 | 0.776 | 0.539 |

*Every model retrieved through `GET /etl/concepts`; built through `POST /etl/job` (`jobType:ml`). Metrics are the engine's own held-out test scores.*