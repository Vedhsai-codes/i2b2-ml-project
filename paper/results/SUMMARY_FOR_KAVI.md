# i2b2-ML phenotype models on MIMIC-IV — 11 phenotypes built through the tool

I used the i2b2-ML module, driven entirely through its JSON API (`jobType:ml`), to build
phenotype models for eleven conditions on MIMIC-IV — including the ones you asked for
(ASCVD, dyslipidemia, hypertension, CKD, type 2 diabetes, OSA, prediabetes, asthma) on top
of stroke, heart failure, and ischemic heart disease. Each job ran through the jobWatcher /
engine to `COMPLETED`, with the trained model retrieved from `concept_blob` — nothing was
trained outside the tool.

Per your note, this is wrapped as one script: **`./pipeline/run_all_phenotypes.sh`** builds
every phenotype end-to-end (renders the cohort SQL, pulls from BigQuery, loads into i2b2,
builds through the API, writes the results table). The phenotype list comes from one config
file (`pipeline/config/phenotypes.yaml`), so adding a phenotype is a single config entry —
no code change.

| Phenotype | Cases / Controls | ROC AUC | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| Ischemic stroke | 800 / 1,600 | 0.891 | 0.811 | 0.686 | 0.792 | 0.736 |
| Ischemic heart disease | 800 / 1,600 | 0.893 | 0.807 | 0.659 | 0.872 | 0.751 |
| Atherosclerotic CVD (ASCVD) | 800 / 1,600 | 0.910 | 0.834 | 0.719 | 0.827 | 0.769 |
| Heart failure | 800 / 1,600 | 0.914 | 0.842 | 0.734 | 0.824 | 0.776 |
| Hypertension | 800 / 1,600 | 0.899 | 0.832 | 0.693 | 0.892 | 0.780 |
| Dyslipidemia | 800 / 1,600 | 0.895 | 0.824 | 0.686 | 0.869 | 0.767 |
| Type 2 diabetes | 800 / 1,600 | 0.931 | 0.875 | 0.809 | 0.815 | 0.812 |
| Prediabetes | 800 / 1,600 | 0.797 | 0.760 | 0.629 | 0.666 | 0.647 |
| Chronic kidney disease | 800 / 1,600 | 0.946 | 0.896 | 0.841 | 0.849 | 0.845 |
| Obstructive sleep apnea | 800 / 1,600 | 0.767 | 0.656 | 0.490 | 0.809 | 0.610 |
| Asthma | 800 / 1,600 | 0.658 | 0.558 | 0.413 | 0.776 | 0.539 |
| **Mean (11)** | | **0.864** | 0.791 | 0.669 | 0.817 | 0.730 |

Elastic-net logistic regression with SMOTE, built and scored by the engine on a held-out 50%
test split. Silver-standard ICD labels; a shared set of 32 structured features (demographics,
comorbidities, labs, vitals, medications). Metrics are the engine's own test-set scores.

A couple of honest notes:
- The spread is driven by how well the shared (cardiometabolic) feature set fits each
  condition — highest where the diagnostic labs are in the set (CKD/creatinine 0.95,
  T2D/HbA1c 0.93), lowest for the respiratory phenotypes the cardiovascular features barely
  describe (OSA 0.77, asthma 0.66). Tailoring features per phenotype is a config change.
- The comorbidity flag that equals a phenotype's own outcome (e.g. the HF flag for HF) is
  derived from the same ICD codes as the label and gives a misleading AUROC of 1.0; I
  exclude it per phenotype. Diagnostic labs that aren't ICD-derived are kept (they're the
  clinical basis and don't perfectly reproduce the label).

Formatted results table: `paper/tables/results_table.docx`. Full draft write-up:
`paper/MANUSCRIPT.md` (+ `.docx`). Happy to adjust any of the ICD phenotype definitions —
they're all in the config with comments.
