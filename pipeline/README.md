# Phenotype ML pipeline — build models THROUGH the i2b2-ML API on MIMIC

This is the **aligned grant deliverable**: a repeatable pipeline that builds a
phenotype model **through the i2b2-ML JSON API** (`jobType: "ml"`) on a MIMIC
cohort — not a standalone sklearn script. The same pipeline runs stroke, heart
failure, IHD, and Kavi's emailed list by swapping config. That repeatability is
the paper's claim: *"a non-ML researcher can drive the i2b2-ML tool to build
phenotype models on MIMIC."*

> Contrast with `evaluation/` (the LLM eval harness) and `evaluation/baseline_logreg.py`
> (standalone sklearn). Those prove a *model* works. This proves the *tool* works.

## How it maps to the tool (verified against the code)

```
sql/cohort_<ph>.sql ─bq─▶ wide cohort CSV
        │ build_cohort.py
        ▼
 <ph>_concepts.csv ─ etl concept load ─▶ concept_dimension + i2b2 ontology
 <ph>_facts.csv    ─ etl fact load    ─▶ observation_fact   (--mrn-are-patient-numbers)
 <ph>_membership   ─ create_patient_sets.py ─▶ qt_patient_set_collection  (<ph>_pos / <ph>_neg)
        │ run_ml_build.py
        ▼
 POST /etl/concepts (register ML concept + blob)
 POST /etl/job  {"input":{"path":"/ML/Diagnosis/Stroke"},"jobType":"ml"}
        ▼ jobWatcher ▶ mlEngine ▶ apply_build_model (elastic-net LogisticRegression)
 concept_dimension.concept_blob.serialized_model   ◀── retrieved via GET /etl/concepts
```

Reference implementation already in repo: `tests/ML/test_ml_mimic_hf.py` +
`tests/ML/test_helper.py:create_patient_set` (a working MIMIC-HF build through
this exact path). This pipeline generalises and operationalises it.

## Files

| File | Role |
|---|---|
| `config/phenotypes.yaml` | **Single source of truth** — shared feature set + per-phenotype label ICD codes, cohort caps, ML blob. |
| `../sql/cohort_template.sql` | BigQuery template (one row per patient: label + features). |
| `render_cohort_sql.py` | template + config → runnable `sql/cohort_<ph>.sql`. |
| `build_cohort.py` | wide cohort CSV → `<ph>_concepts.csv`, `<ph>_facts.csv`, `<ph>_membership.csv`. |
| `create_patient_sets.py` | membership → named `qt_*` patient sets (run **in container**). |
| `run_ml_build.py` | register concept → POST `jobType:ml` → poll → retrieve model (API driver). |
| `load_and_build.sh` | end-to-end runbook tying it all together. |
| `test_pipeline_smoke.py` | cheap LOCAL contract test (no DB/network). |
| `PLAN_phenotype_ml_pipeline.md` | the plan + frozen contract. |

## Quickstart (stroke)

```bash
# 0. cheap checks — no infra needed
python pipeline/render_cohort_sql.py --all
python -m pytest pipeline/test_pipeline_smoke.py -q
bq query --use_legacy_sql=false --dry_run < sql/cohort_stroke.sql   # validates vs MIMIC

# 1. pull the cohort (PhysioNet DUA required; ~6.8 GB scan, free-tier OK)
bq query --use_legacy_sql=false --format=csv --max_rows=100000 \
    < sql/cohort_stroke.sql > ~/mimic_data/cohort_stroke.csv

# 2. generate i2b2 load files
python pipeline/build_cohort.py stroke --cohort ~/mimic_data/cohort_stroke.csv

# 3. end-to-end (stack must be up + jobWatcher running)
./pipeline/load_and_build.sh stroke ~/mimic_data/cohort_stroke.csv
```

Add a phenotype: add a `phenotypes:` entry to `config/phenotypes.yaml`, then rerun
from step 0 with the new name. Add a feature: add it to `config/phenotypes.yaml`
`features:` **and** add the column to `sql/cohort_template.sql`.

Configured today: **stroke, heart_failure, ischemic_heart_disease**. Kavi's emailed
list slots in as additional `phenotypes:` entries (and any new risk factors as
`features:` entries) when it arrives — no code change, just config.

### Where each step runs
`load_and_build.sh` steps 0/1/6 run on the **Mac cockpit** (SQL render, CSV gen, the
HTTP API driver). Steps 2–5 run **in-container** via `docker exec` — the loaders and
`create_patient_sets.py` need the `i2b2_cdi` module and a live CRC DB connection, which
the host doesn't have. `run_ml_build.py` (step 6) is a pure HTTP client, so it runs on
the host against the published port. The script preflights that Docker + both containers
are up and aborts with a clear message if not.

### Troubleshooting a build
- Job stuck `PENDING`: the jobWatcher daemon isn't running. Start it:
  `docker exec i2b2-ml bash -lc "source /usr/src/app/.venv/bin/activate && python -m i2b2_cdi.job.jobWatcher &"`
- Job `ERROR`: inspect `job.output` and the container logs
  (`docker logs i2b2-ml --tail 200`). Common cause = patient sets not found
  (names must be `<phenotype>_pos`/`<phenotype>_neg`; verify `create_patient_sets.py`
  printed result_instance_ids in step 5).
- Empty feature matrix: confirm the loaded `concept_path`s sit under `/MIMIC/features`
  so the blob `data_paths` LIKE-match them.
- Reproducibility: builds are deterministic because the blob carries a fixed
  `random_seed` (0.42). Change it in `config/phenotypes.yaml` to perturb.

## Default feature set (provisional — pending Kavi's emailed risk factors)

Clinically grounded stroke risk factors available structured in MIMIC-IV hosp:
demographics (age, sex); comorbidities (HTN, DM, AFib, IHD, CHF, hyperlipidemia,
CKD, PVD, smoking, carotid stenosis); labs (glucose, HbA1c, LDL, HDL, total
cholesterol, triglycerides, creatinine, INR, hemoglobin, platelets, WBC, sodium);
OMR vitals (SBP, DBP, BMI); meds (antihypertensive, statin, anticoagulant,
antiplatelet, antidiabetic). When Kavi's list arrives, edit the YAML + SQL feature
blocks — the rest of the pipeline is unchanged.

## Design decisions & caveats (be honest in the paper)

- **Silver standard.** Cases = ICD-10 `I63%`/`I64%` (ischemic stroke) — Kavi's
  assigned homework. Controls exclude **all** cerebrovascular codes (I60–I69, G45/46)
  so they are clean negatives. Per-phenotype label/exclusion ICD sets live in the YAML.
- **Analysis unit = patient.** Index admission = earliest case admission (positives) /
  earliest admission (controls). One row per `subject_id`.
- **Temporal model (v1): cross-sectional snapshot.** Every feature fact AND the
  label fact are dated at the patient's index-admission date, with `time_buffer=0`,
  so the i2b2-ML engine retains every feature. Real per-fact timestamps are collapsed
  to the index date. A temporal/leakage-aware variant (features strictly before the
  event) is future work.
- **Leakage caveat.** Comorbidities/labs/meds drawn from the index admission can leak
  outcome-concurrent information for an acute stroke admission. Acceptable for a
  *tool-validation* demonstration; documented, not hidden. The temporal variant above
  addresses it for any clinical-prediction follow-up.
- **patient_num = subject_id** (load with `--mrn-are-patient-numbers`). MIMIC 8-digit
  subject_ids don't collide with the small demo patient_nums.
- **Lab label strings** in the SQL are the common MIMIC-IV `d_labitems.label` values;
  confirm on first run (`SELECT DISTINCT label,fluid FROM d_labitems WHERE label LIKE ...`).
- **Class imbalance** is handled inside the engine (SMOTE + class_weight); the cohort
  caps (`max_positives`, `neg_per_pos`) keep the first end-to-end run small/cheap.

## Verification status (2026-06-18)

| Check | Result |
|---|---|
| `pytest pipeline/test_pipeline_smoke.py` | ✅ 5 passed (CSV contract + engine invariants) |
| `render_cohort_sql.py --all` | ✅ stroke / heart_failure / ischemic_heart_disease render |
| `bq query --dry_run < sql/cohort_stroke.sql` | ✅ validated vs `physionet-data.mimiciv_3_1_hosp` (6.76 GB/run) |
| Live end-to-end (`COMPLETED` + model retrieved) | ⏳ gated on a live stack (Docker was wedged; runbook ready) |
