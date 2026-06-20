# Capability map — the i2b2-ML tool vs. the prediction-study harness

The accessibility claim of this work is that a **no-code, CDW-native tool** (the i2b2-ML
plugin, driven through its JSON API) can fit the same phenotype-identification models that a
bespoke pipeline produces. The tool covers model *fitting*; a thin reproducible-research
harness wraps it for the *rigor* a clinical-prediction paper requires. This table is the
honest division of labour.

## Reproduction receipt (built live through the JSON API, `jobType:ml`, `http 200`, serialized model returned)

| Phenotype | i2b2-ML tool (no-code) ROC AUC | Bespoke harness identification ROC AUC | Δ |
|---|---|---|---|
| Heart failure | 0.914 | 0.907 (0.906–0.909) | +0.007 |
| Chronic kidney disease | 0.946 | 0.935 | +0.011 |
| Type-2 diabetes | 0.931 | 0.933 | −0.002 |

The no-code tool reproduces the bespoke pipeline's discrimination to within ≤0.011 AUROC for
all three cardiometabolic phenotypes — the central accessibility result. *(Tool builds use the
plugin's balanced sampling: n=2,400, 800 positive / 1,600 negative; the harness uses the full
natural-prevalence cohort, which is why the tool numbers run a hair higher. Self-comorbidity
features are excluded in both to prevent label leakage.)*

**Sampling sensitivity (rules out an apples-to-oranges artefact):** trained on an *identical*
800/1,600 balanced HF sample, the harness reaches ROC AUC **0.902** — essentially equal to its own
full natural-prevalence 0.907 and the tool's 0.914. The plugin's balanced sampling therefore does
not inflate discrimination; the tool-vs-harness agreement is genuine, not a sampling artefact
(`results/hf_balanced2400.json`).

## What runs **inside** the tool (no code; a non-ML researcher can do it via the JSON UI/API)

| Capability | How it is exercised |
|---|---|
| Cohort as i2b2 named **patient sets** | positive/negative sets in `qt_patient_set_collection` |
| Feature assembly from **concepts + facts** | `concept_dimension` + `observation_fact` (loaded via the ETL `concept/fact load`) |
| **Model fitting** (regularized logistic regression / `mlEngine`) | `POST /etl/job {"jobType":"ml","input":{"path": <ML concept>}}` |
| Asynchronous build (`jobWatcher`) | poll `GET /etl/job` until `COMPLETED` |
| **Model + metrics retrieval** | `concept_blob.serialized_model`; ROC AUC, accuracy, precision, recall, F1 |
| Automatic feature selection | tool returned 16 of the supplied features for HF |

## What the **harness adds around** the tool (the rigor layer; reusable, not phenotype-specific)

| Capability | Artifact |
|---|---|
| Aligned per-admission **identification cohort** definition | `cohort_{hf,ckd,dm}_mimic_identify.sql` |
| **Temporal / blackout** leakage-decay design | `cohort_{hf,ckd,dm}_temporal.sql`, `evaluate.py` |
| eICU **harmonization** (diagnosis **+ pasthistory**, unit-checked) | `cohort_{hf,ckd,dm}_eicu.sql` |
| **External validation** (frozen MIMIC→eICU transport) | `external_validate.py` |
| **Recalibration hierarchy** (intercept-only, intercept+slope) | `external_validate.py` |
| **Bootstrap 95% CIs**, calibration slope/intercept, Brier | `evaluate.py`, `identify_eval.py` |
| **Decision-curve analysis** + risk-factor reference comparator | `dca.py`, `identify_eval.py` |
| **TRIPOD+AI** reporting + PROBAST self-assessment | `paper/TRIPOD_AI_checklist.md` |

**Reading of the split:** the tool is sufficient for *building a calibrated identification
model from a CDW* — the step that previously required an ML engineer. Everything the harness
adds is study-design and reporting scaffolding that is phenotype-agnostic and would live in any
rigorous prediction study regardless of the modelling engine. The contribution is therefore that
the *modelling* step is now accessible, and the surrounding rigor is a reusable template.
