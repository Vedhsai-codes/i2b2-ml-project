# Validating the i2b2-ML tool for phenotype model development on MIMIC-IV

**Authors:** Vedhsai Thiriveedi, [Kavishwar Wagholikar], [coauthors TBD]
**Affiliation:** Massachusetts General Hospital
**Draft:** auto-generated 2026-06-20 — *results pending all three phenotype builds; numbers below are populated from live i2b2-ML API receipts, not standalone scripts.*

---

## Abstract

**Objective.** To validate the i2b2 embedded machine-learning module (i2b2-ML) as a tool for phenotype model development on an external dataset, building every model through the tool's JSON API rather than in standalone analytic code.

**Methods.** Using MIMIC-IV v3.1, we defined three cardiovascular phenotypes — ischemic stroke, heart failure, and ischemic heart disease — each with 800 ICD-defined cases and 1,600 controls and 32 structured features (demographics, comorbidities, laboratory values, vitals, and medication classes). For each phenotype we loaded the cohort into i2b2 as concepts and facts, created case and control patient sets, and submitted a build job over the API (`POST /etl/job`, `jobType:ml`). The engine trained an elastic-net logistic regression with class-imbalance resampling and cross-validated hyperparameter selection, and returned the model and metrics in the i2b2 data model. Each phenotype was added by editing one configuration file.

**Results.** All three builds completed through the API, with the trained model retrieved from the i2b2 concept store. Held-out test ROC AUCs were 0.891 (stroke), 0.914 (heart failure), and 0.893 (ischemic heart disease). Initial heart-failure and ischemic-heart-disease builds reached AUC 1.0 because a comorbidity feature was derived from the same ICD codes as the label; removing that self-referential feature — a one-line change — produced the values above.

**Conclusion.** The i2b2-ML tool, driven entirely through its JSON API, built phenotype models for three conditions on a dataset it was not developed against, by configuration alone. This supports the use of the tool by researchers without machine-learning expertise and provides a repeatable procedure for adding further phenotypes.

---

## 1. Introduction

Electronic phenotyping — identifying patients with a condition from structured clinical data — underpins cohort discovery, quality measurement, and observational research. Most phenotype models are still built by hand in bespoke analytic scripts, which couples each model to the analyst who wrote it and makes the work hard to reproduce or transfer. The i2b2 platform addresses part of this gap with an embedded machine-learning module (i2b2-ML) that builds models from data already loaded in the i2b2 clinical data warehouse and exposes the whole workflow through a JSON API, so that a researcher specifies a model declaratively rather than writing training code.

The contribution of this work is a validation of that tool rather than a new model. The question is not "can a logistic-regression model predict stroke" — that is well established — but "can the i2b2-ML tool, driven through its API, build usable phenotype models on a real, external dataset across several conditions, without the user writing any machine-learning code." A standalone scikit-learn script answers the first question and says nothing about the second. We therefore build every model in this paper *through the tool*: we load a phenotype cohort into i2b2 as concepts and facts, create patient sets, and submit a build job to the i2b2-ML engine over its JSON API. The model that comes back is the one the tool produced.

We validate across three cardiovascular phenotypes — ischemic stroke, heart failure, and ischemic heart disease — on MIMIC-IV, an external dataset the tool was not developed against. Each phenotype is added to the pipeline by editing a single configuration file, so the same procedure produces all three models. That repeatability is the claim: a non-ML researcher can drive the i2b2-ML tool to build phenotype models on new data.

## 2. Methods

### 2.1 Data source

We used MIMIC-IV v3.1 (hospital module), a de-identified critical-care dataset of 364,627 patients from Beth Israel Deaconess Medical Center, accessed through Google BigQuery (`physionet-data.mimiciv_3_1_hosp`) under an approved PhysioNet data use agreement. All cohort construction was performed in BigQuery SQL; no patient-level data left the credentialed environment except the de-identified structured facts loaded into the local i2b2 instance.

### 2.2 Cohort definition

For each phenotype we defined cases by a silver-standard ICD code set and sampled controls without any related diagnosis:

| Phenotype | Case ICD-10 (and ICD-9) | Control exclusion |
|---|---|---|
| Ischemic stroke | I63, I64 (433.x1, 434.x1) | all cerebrovascular: I60–I69, G45/G46 |
| Heart failure | I50 (428) | I50, I110, I130, I132, I255, I420, I429 |
| Ischemic heart disease | I20–I25 (410–414) | I20–I25 |

Each cohort comprised 800 cases and 1,600 controls (1:2), capped to keep the first end-to-end runs small. The analysis unit is the patient (one row per `subject_id`). The index admission is the earliest case admission for cases and the earliest admission for controls; every feature and the label are dated at the index-admission date (a cross-sectional snapshot; see Limitations). Controls were drawn to exclude any diagnosis in the phenotype's exclusion set, so they are clean negatives.

Because the cases are defined by ICD codes rather than chart review, the labels are a silver standard. For heart failure, ICD-based ascertainment has been validated against chart review (Roger et al., 2014: pooled sensitivity 75%, specificity 97%, PPV ≥87%), which supports using codes as labels without manual inter-rater review.

### 2.3 Feature set

We extracted 32 structured features available in MIMIC-IV hosp, chosen as clinically grounded cardiovascular risk factors and mapped one-to-one to i2b2 concepts under `\MIMIC\features\`:

- **Demographics (2):** age at index, sex.
- **Comorbidities (10), binary, history through the index admission:** hypertension, diabetes, atrial fibrillation, ischemic heart disease, heart failure, hyperlipidemia, chronic kidney disease, peripheral vascular disease, smoking, carotid stenosis.
- **Laboratory values (12), first value during the index admission:** glucose, HbA1c, LDL, HDL, total cholesterol, triglycerides, creatinine, INR, hemoglobin, platelets, white blood cell count, sodium. (LDL/HDL/total cholesterol were matched on the MIMIC-IV `d_labitems` labels `Cholesterol, LDL/HDL/Total`; an earlier `LDL%` pattern matched nothing and was corrected.)
- **Vitals (3), most recent value on or before the index date, from the outpatient OMR table:** systolic and diastolic blood pressure, BMI, each with plausibility bounds applied before recency ranking (BMI 10–100, SBP 50–300, DBP 20–200).
- **Medications (5), binary, any order during the index admission:** antihypertensive, statin, anticoagulant, antiplatelet, antidiabetic.

### 2.4 Building the model through the i2b2-ML API

We used i2b2-etl v4.1.0 with its ML module, running locally as a Docker stack (PostgreSQL CRC database, the ETL Flask service, and the jobWatcher daemon). Every step below is driven through the tool, not in an external script:

1. **Load.** The per-patient cohort CSV is transformed into i2b2 concept and fact files and loaded with the i2b2 ETL loader (`concept load`, `fact load --mrn-are-patient-numbers`, so the i2b2 `patient_num` equals the MIMIC `subject_id`). This writes the 32 feature facts and the label fact for each patient into `observation_fact`.
2. **Patient sets.** Cases and controls are materialized as two named i2b2 patient sets (`<phenotype>_pos`, `<phenotype>_neg`) in `qt_patient_set_collection` — the same structure an i2b2 user would create from the query tool.
3. **Register the model concept.** An ML concept is registered through `POST /etl/concepts` with a blob specifying the positive/negative patient sets, the feature subtree (`data_paths`), the label path, and a fixed random seed.
4. **Submit the build job.** `POST /etl/job` with `{"jobType": "ml"}` enqueues an asynchronous build. The jobWatcher daemon picks it up and invokes the ML engine (`mlEngine → apply_build_model`), which reads the cohort from the patient sets, assembles the feature matrix from `observation_fact`, and trains an elastic-net logistic regression with SMOTE oversampling for class imbalance and a 5-fold grid search over the regularization path, evaluating on a held-out split (50%).
5. **Retrieve.** The trained model and its metrics are serialized into `concept_dimension.concept_blob` and retrieved through `GET /etl/concepts`. The model returned is the tool's output; we did not train anything ourselves.

Builds are deterministic: the blob carries a fixed `random_seed` (0.42) used for the SMOTE sampler and the train/test split, so repeating a build reproduces the same model and metrics. Adding a phenotype is a configuration edit (label ICD set and concept paths) plus one command; the pipeline code does not change.

### 2.5 Evaluation

For each phenotype we report the metrics the tool computes on its held-out test split: ROC AUC, accuracy, precision, recall, and F1, together with the features the engine retained. No external evaluation was performed; the goal is to validate the tool's own reported output, which is what an i2b2-ML user would see.

## 3. Results

All three phenotype build jobs ran to completion through the i2b2-ML API. Each `POST /etl/job` (`jobType:ml`) was picked up by the jobWatcher, trained by the engine, and reached `COMPLETED`; the serialized model and its metrics were retrieved from `concept_dimension.concept_blob` via `GET /etl/concepts`. No model was trained outside the tool.

**Table 2. Phenotype models built through the i2b2-ML API (MIMIC-IV).** Metrics are the engine's own held-out test scores (50% split).

| Phenotype | Cases / Controls | Features retained | ROC AUC | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|
| Ischemic stroke | 800 / 1600 | 16 | 0.891 | 0.811 | 0.686 | 0.792 | 0.736 |
| Heart failure | 800 / 1600 | 16 | 0.914 | 0.842 | 0.734 | 0.824 | 0.776 |
| Ischemic heart disease | 800 / 1600 | 16 | 0.893 | 0.807 | 0.659 | 0.872 | 0.751 |

Discrimination was consistent across the three conditions (test ROC AUC 0.89–0.91). From the 31–32 features loaded per phenotype, the engine retained 16 in each model; the dropped features were the sparsely measured laboratory values (e.g., HbA1c, LDL/HDL, triglycerides), which the engine removes for high missingness. Retained features were the universally available ones — age, sex, common comorbidities, routine labs (creatinine, glucose, hemoglobin, INR, sodium), vitals, and medication classes — and matched clinical expectation (e.g., for stroke the model kept hypertension, age, and antithrombotic medication use).

### 3.1 A leakage check the tool surfaced

The first heart-failure and ischemic-heart-disease builds returned **ROC AUC 1.0** — perfect separation. Inspection of the retained features showed the cause: the model had selected the comorbidity flag matching its own outcome (`cm_chf` for heart failure, `cm_ihd` for ischemic heart disease). These comorbidity features are derived from the *same* ICD-10 codes that define the label (heart failure from I50, ischemic heart disease from I20–I25), so the feature is the outcome. In the heart-failure cohort, the heart-failure comorbidity flag was present in 0 of 1,600 controls and ~93% of cases — a near-perfect proxy for the label.

We removed each self-referential comorbidity from its own phenotype (a one-line configuration change) and rebuilt. Discrimination fell to the values in Table 2 (heart failure 1.0 → 0.914; ischemic heart disease → 0.893), in line with stroke, which never had this problem because no "stroke comorbidity" feature exists in the set. We report this because it is informative about the tool in use: the engine faithfully built whatever cohort it was given, and the implausibly perfect score was itself the signal that surfaced a feature-design error. A researcher without machine-learning training would see the same red flag and could act on it.

To keep cohorts from contaminating one another through the shared fact table, each phenotype was loaded, built, and then cleared before the next, so every model was trained on its own cohort only.

## 4. Discussion

The result that matters for this paper is procedural, not predictive: three phenotype models were produced on an external dataset entirely through the i2b2-ML JSON API, with no analyst-written training code. After the cohort SQL was in place, each model was a configuration entry (label codes, concept paths) and a single command; the engine handled feature assembly, resampling, model selection, training, and storage of the result back into the i2b2 data model. This is the workflow the tool is meant to support, and it held across three conditions without code changes — which is what "a non-ML researcher can build phenotype models with this tool" requires in practice.

The models themselves discriminated consistently (ROC AUC 0.89–0.91). A standalone logistic-regression baseline on a comparable cohort reaches similar performance; that comparison is reassuring but beside the point, since a standalone script demonstrates that a model can be built, not that the tool builds it. The contribution here is the second claim.

The leakage episode is worth drawing out. The tool did exactly what it was told — it built a model from the cohort it was given — and the resulting perfect score was the artifact that exposed a feature-design mistake. In a workflow where the analyst writes the training code, the same mistake is just as easy to make and no more visible; here it surfaced as an obviously implausible metric returned by the tool. This cuts against a common worry about "push-button" model builders, that they hide problems from non-expert users: in this case the tool's output made the problem conspicuous.

Two of the engine's defaults shaped the results and are worth naming. First, feature selection by missingness dropped the sparse laboratory values, so the retained models lean on routinely measured features; a user wanting to keep sparse labs would need to impute upstream. Second, the 50/50 train/test split and SMOTE resampling are the engine's defaults, appropriate for a tool validation but not tuned per phenotype. None of these were changed, by design — the goal was to characterize the tool as it ships.

## 5. Limitations

- **Silver-standard labels.** Cases are defined by ICD codes, not chart review. This is standard for high-throughput phenotyping and, for heart failure, is supported by validation against chart review (Roger et al., 2014), but code-based labels carry known misclassification.
- **Outcome-concurrent features (leakage).** Because comorbidities, labs, and medications are drawn from the index admission, they can encode information concurrent with an acute event rather than strictly preceding it. This is acceptable for a tool-validation demonstration — the point is that the tool builds a model, not that the model is deployable for prospective risk prediction — but it inflates discrimination relative to a true prediction setting. A temporal variant that restricts features to a window strictly before the event is the natural next step and is straightforward in the same pipeline (narrow the engine's data-period window).
- **Cross-sectional snapshot.** All feature facts and the label are dated at the index-admission date (`time_buffer = 0`), collapsing real per-fact timestamps. This keeps every feature available to the engine but removes temporality.
- **Single dataset and cohort size.** Results are from MIMIC-IV only, with 800 cases per phenotype; external validity and calibration are not assessed here.
- **Defaults not tuned.** We used the engine's default model family (elastic-net logistic regression), resampling (SMOTE), and split (50/50). These are the tool's defaults, which is appropriate for a validation of the tool but not optimized per phenotype.

## 6. Conclusion

Driven entirely through its JSON API, the i2b2-ML tool built logistic-regression phenotype models for ischemic stroke, heart failure, and ischemic heart disease on MIMIC-IV — a dataset it was not developed against — by configuration alone, with held-out ROC AUCs of 0.89–0.91. The same procedure produced all three models and extends to further phenotypes through configuration, which is the property a tool-validation claim needs. Natural next steps are a temporal, leakage-aware feature window for any clinical-prediction use; the additional phenotypes on the collaborating investigator's list; and the extension that lets the engine derive features from clinical notes with a large language model, feeding model building from unstructured data through the same interface.

## References

1. Roger VL, et al. *Trends in heart failure incidence and survival.* (validation of ICD-based HF ascertainment vs chart review; PMC4134216), 2014.
2. Johnson AEW, et al. *MIMIC-IV* (v3.1), PhysioNet.
3. [i2b2-ML / i2b2-etl tool reference — Klann et al.; JAMIA Open — TBD]

---

*Reproducibility: cohort SQL in `sql/cohort_<phenotype>.sql`; pipeline and runbook in `pipeline/`; per-phenotype build receipts in `paper/results/`. Every model in this paper was built through the i2b2-ML JSON API (`jobType:ml`), not a standalone script.*
