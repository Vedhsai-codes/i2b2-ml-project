# i2b2-ML phenotype build results (through the JSON API)

| Phenotype | n (cases/controls) | Features | ROC AUC | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|
| stroke | 2400 (800/1600) | 16 | 0.891 | 0.811 | 0.686 | 0.792 | 0.736 |
| heart_failure | 2400 (800/1600) | 16 | 0.914 | 0.842 | 0.734 | 0.824 | 0.776 |
| ischemic_heart_disease | 2400 (800/1600) | 16 | 0.893 | 0.807 | 0.659 | 0.872 | 0.751 |

*Every model retrieved through `GET /etl/concepts`; built through `POST /etl/job` (`jobType:ml`). Metrics are the engine's own held-out test scores.*