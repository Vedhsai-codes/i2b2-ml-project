# PLAN — Phenotype ML pipeline (build models THROUGH the i2b2 ML API)

**Phase:** Aligned grant deliverable (tool-validation paper). NOT the LLM follow-up.
**Date:** 2026-06-18
**Owner:** Vedhsai · Lab: MGH / Dr. Kavishwar Wagholikar

## Task
Build a **repeatable** pipeline that turns a MIMIC phenotype into a model built
**through the i2b2 ML JSON API** (`jobType: "ml"`), not a standalone sklearn script.
First phenotype: **stroke** (silver standard ICD-10 `I63%`/`I64%`). Same pipeline
must run HF, IHD, and Kavi's emailed list by swapping config — that repeatability
IS the paper's claim.

## What "through the tool" means (verified against the code, not assumed)
The live `jobType: "ml"` path is:
`POST /etl/job` → `job` row PENDING → jobWatcher → `mlEngine.run` →
`i2b2_cdi.ML.apply_build_model_ml.apply_build_model` → `build_model_ML_helper.get_dataframes`.

`get_dataframes` reads cohort membership from **i2b2 patient sets**
(`qt_patient_set_collection`, resolved by NAME via
`i2b2_cdi/utils/patient_set.py:get_patient_set_instance_id`, which matches
`qt_query_result_instance.description = 'Patient Set for "<name>"'`). It trains an
elastic-net LogisticRegression (RobustScaler → SMOTE → SelectFromModel → GridSearchCV)
and writes the base64-pickled model into `concept_dimension.concept_blob`.

Reference implementation already in repo: `tests/ML/test_ml_mimic_hf.py` +
`tests/ML/test_helper.py:create_patient_set` (a working MIMIC-HF build through this
exact path). Stroke mirrors it.

## Contract (frozen — every artifact must agree on these)
- **Concept CSV** (`*_concepts.csv`): header `type,path,code`. Types:
  `integer|float|assertion`. Paths forward-slash, leading slash; loader stores as
  `\MIMIC\...\` backslash coded paths.
- **Fact CSV** (`*_facts.csv`): header `mrn,code,start_date,value`. Load with
  `--mrn-are-patient-numbers` so `patient_num == subject_id`. Assertion facts have
  empty value.
- **Blob `data_paths`/`label_paths`** are forward-slash human paths
  (`/MIMIC/features`, `/MIMIC/phenotype/stroke`); `format_data_paths` turns them
  into `\\MIMIC\\features%` LIKE patterns. Data and label subtrees are disjoint.
- **Temporal model (v1):** every feature fact AND the label fact are dated at the
  patient's **index admission date**. `time_buffer=0` → cutoff = index date → all
  features included. (Real per-fact timestamps collapsed to index date for v1; a
  temporal/leakage-aware variant is future work and is documented as a caveat.)
- **Positives MUST have a label fact** (engine derives the cutoff from the first
  label fact); **negatives MUST have ≥1 feature fact** (cutoff = last feature fact).
- Auth: HTTPBasicAuth `demo\demo` / `Etl@2021`, header `X-Project-Name: Demo`.
  etl Flask on container 5000 (host 5005 via docker-compose.override.yml on Mac).

## Pipeline stages (files)
1. `sql/cohort_template.sql` (+ rendered `sql/cohort_stroke.sql`) — BigQuery, one
   row per patient: label + structured features (demographics, comorbidities, labs,
   OMR vitals, meds). Index admission = earliest case admission (positives) /
   earliest admission (controls). Controls exclude ALL cerebrovascular codes (I60–I69).
2. `pipeline/config/phenotypes.yaml` — single source of truth: shared `features:`
   (wide-CSV column → i2b2 path/code/type) + `phenotypes:` (label ICD predicate,
   negative-exclusion, cohort caps, ML blob).
3. `pipeline/render_cohort_sql.py` — template + config → runnable per-phenotype SQL.
4. `pipeline/build_cohort.py` — wide cohort CSV + config → `<ph>_concepts.csv`,
   `<ph>_facts.csv`, `<ph>_membership.csv`. Validates against the loader contract.
5. `pipeline/create_patient_sets.py` — membership CSV → named positive/negative
   patient sets in `qt_*` (adapts `create_patient_set` to an explicit patient_num list).
6. `pipeline/run_ml_build.py` — API driver: register ML concept (`POST /etl/concepts`),
   POST build job (`POST /etl/job` `jobType:ml`), poll, retrieve model from concept_blob.
7. `pipeline/load_and_build.sh` — end-to-end runbook (concept load → fact load →
   patient sets → register concept → build job → retrieve).
8. `pipeline/test_pipeline_smoke.py` — cheap LOCAL verification (synthetic wide CSV →
   asserts generated CSVs satisfy the loader contract). No DB, no network.

## Cheapest-first tests (ResearchOS rule 9 — Mac is cockpit, not compute)
- `bq query --dry_run` on rendered SQL (validates against real MIMIC schema, $0).
- `pytest pipeline/test_pipeline_smoke.py` (CSV contract, $0, no infra).
- Small cohort default (`max_positives: 800`, `neg_per_pos: 2`) so the first real
  end-to-end build is fast/cheap before scaling.

## Success criteria
- `cohort_stroke.sql` dry-runs clean against `physionet-data.mimiciv_3_1_*`.
- `build_cohort.py` on the real stroke cohort CSV emits concept/fact/membership CSVs
  that pass the smoke contract checks.
- Runbook documents the exact POSTs; a build job reaches `COMPLETED` and
  `concept_blob.serialized_model` is retrievable. (Final end-to-end run is gated on
  a live stack — Docker was wedged; runbook is ready to execute when infra is up.)

## Blocked / pending
- Kavi's emailed risk-factor list (the authoritative feature set). Default feature
  set is clinically grounded and config-driven so swapping is a YAML edit.
- Live i2b2 stack (Docker Desktop wedged per HANDOFF) for the final COMPLETED receipt.
