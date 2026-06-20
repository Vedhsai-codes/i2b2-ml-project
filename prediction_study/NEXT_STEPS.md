# Prediction study — handoff to continue (read this first in a new window)

**Branch:** `feature/phenotype-ml-pipeline` · last commit `a10211e` (all pushed).
**Read also:** `prediction_study/results/FINDINGS.md`, `results/external_validation_summary.md`.

This is the rigorous *prediction / external-validation* paper (distinct from the tool-validation
paper in `paper/MANUSCRIPT.md`). Goal venue: npj Digital Medicine / EHJ–Digital Health / JACC:Adv.

## STATUS — what's DONE (don't redo)

3-condition external validation complete. ROC AUC internal / external (eICU, 200+ hospitals):
- Heart failure 0.907 / 0.758, CKD 0.935 / 0.840, diabetes 0.933 / 0.761.
- Internal calibration ~perfect (slope ~1.0); external calibration drifts, **restored by
  intercept-slope recalibration in every condition** (0.98–1.01).
- HF leakage-decay ablation (concurrent 0.88 → pre-onset 0.81, fixed-cohort confirmed) + DCA done.
- Figures in `results/`: `hf_decay.png`, `hf_dca.png`, `hf_external_calibration.png`,
  `external_validation_summary.png`.

## FILES (prediction_study/)
- `cohort_hf_temporal.sql` — incident-HF, blackout-windowed (placeholder `BLACKOUT_PLACEHOLDER`) → the ablation.
- `cohort_{hf,ckd,dm}_mimic_identify.sql` — **aligned** per-admission, all-comers identification cohorts (train).
- `cohort_{hf,ckd,dm}_eicu.sql` — eICU harmonized (diagnosis **+ pasthistory** comorbidities; same 30 features).
- `evaluate.py` — internal eval (AUROC/AUPRC/calibration/bootstrap CI; `--restrict-csv` for fixed cohort; saves `<tag>_preds.npz`).
- `external_validate.py` — train A → test B frozen + recalibration hierarchy (`--drop <self-comorbidity>`, `--tag`).
- `dca.py`, `make_decay_figure.py`. `data/` is gitignored (re-pull with `bq query < cohort_*.sql > data/x.csv`).

## THE 4 REMAINING ITEMS (the user wants all done)

### 1. Ablation + DCA for CKD + diabetes
- `sed` `cohort_hf_temporal.sql` → `cohort_{ckd,dm}_temporal.sql` (label: HF `I50%`/`428%` → CKD `N18%`/`585%`;
  DM `E08%..E13%`/`250%`). Pull at blackout 0/30/90/180; `evaluate.py` each; `make_decay_figure.py` (generalize tag).
  CAVEAT: CKD/DM are chronic — "first code ≠ onset"; frame as *newly-documented* + note the defining lab
  (creatinine/glucose) is the diagnostic basis. Drop the self-comorbidity (`cm_ckd`/`cm_dm`).
- DCA: `evaluate.py` already saves `<tag>_preds.npz`; generalize `dca.py` to take tags → net benefit for CKD/DM.

### 2. Wire through the i2b2-ML tool (the accessibility claim — ties to Kavi's framing)
- Stack is up (colima vz; `i2b2-pg/etl/ml`; PM session token `Etl@2021`; auth `demo\demo`/`Etl@2021`, `X-Project-Name: Demo`).
- Load the aligned HF identification cohort through `pipeline/load_and_build.sh` (jobType:ml) and show the
  tool's LogReg AUROC ≈ the Python harness's 0.907 → "the no-code tool reproduces the bespoke pipeline."
- Add a capability map table (in-tool: model fit/JSON API; around-tool: cohorting, eICU harmonization, eval).

### 3. TRIPOD+AI writeup + manuscript  ← the big one; the reason for a fresh window
- New file `paper/PREDICTION_MANUSCRIPT.md`. Lead with internal 0.91–0.94 + external validation.
- Sections: abstract; intro (accessible CDW-native modeling + external validity); methods (aligned cohorts,
  30 features, temporal design, MIMIC→eICU, recalibration hierarchy, TRIPOD+AI); results (3-condition table +
  ablation + DCA + calibration figs); discussion (transportability; labs transport better than codes; the
  leakage-decay finding); limitations (ICU-only, silver ICD labels, chronic-onset ambiguity, single external set);
  conclusion. Add `paper/TRIPOD_AI_checklist.md` (item-by-item) + a PROBAST self-assessment table.
- Generate a polished `.docx` via `pandoc paper/PREDICTION_MANUSCRIPT.md -o paper/PREDICTION_MANUSCRIPT.docx`.

### 4. Polish
- Strict type-2 diabetes (MIMIC `E11` only; current is any-diabetes for clean harmonization — note in limitations).
- Established-risk-score DCA comparator: KFRE (CKD), PCP-HF/PREVENT (HF) — implement the published equation, compare net benefit.

## KEY LEARNINGS (don't re-derive)
- Lab/vital **units already match** MIMIC↔eICU (verified) — no conversion.
- eICU comorbidities: **must combine `diagnosis` + `pasthistory`** (diagnosis alone under-codes 4–5×: HTN 12%→48%).
- **Cohort alignment is critical**: train and test must share the SAME encounter/label definition (per-admission,
  all-comers) — this single fix moved HF transport 0.717→0.758 and CKD/DM to 0.84/0.76.
- Lead with **internal** (high, the JACC-comparable number); **external** is the rigor (honest drop, expected).
- Model: elastic-net LogReg, **no SMOTE** (it wrecks calibration). `evaluate.py`'s 1000× bootstrap is slow on
  546k rows — use a lighter inline pass for quick internal AUROCs (see git history of this session).
- Reproduce any number: `bq query --use_legacy_sql=false --format=csv --max_rows=2000000 < cohort_X.sql > data/X.csv`
  then `python prediction_study/evaluate.py` / `external_validate.py`.

## CONTEXT FOR THE NEW WINDOW
gcloud authed (project i2b2-mimic-eval-…), eICU + MIMIC-IV both queryable on BigQuery, venv has sklearn/scipy/
matplotlib + python-docx + pandoc. Stack reachable at `http://localhost:5005`. See HANDOFF.md for infra (colima vz, skopeo).
