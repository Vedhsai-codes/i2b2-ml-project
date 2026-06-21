# STATE.md

**Updated:** 2026-06-20 (11-phenotype expansion — Dr. Wagholikar's requested additions)
**Branch:** `feature/phenotype-ml-pipeline`

## Where we are

The aligned grant deliverable is **done end-to-end for 11 phenotypes**, all built **through
the i2b2-ML JSON API** on MIMIC-IV (each `COMPLETED`, model retrieved from `concept_blob`).
Manuscript + a publication-quality results table are drafted.

| Phenotype | ROC AUC | | Phenotype | ROC AUC |
|---|---|---|---|---|
| Chronic kidney disease | 0.946 | | Hypertension | 0.899 |
| Type 2 diabetes | 0.931 | | Dyslipidemia | 0.895 |
| Heart failure | 0.914 | | Ischemic heart disease | 0.893 |
| ASCVD | 0.910 | | Prediabetes | 0.797 |
| Ischemic stroke | 0.891 | | Obstructive sleep apnea | 0.767 |
|  |  | | Asthma | 0.658 |

Mean ROC AUC 0.864. The spread is honest: cardiometabolic phenotypes whose diagnostic
labs are in the shared feature set rank highest; respiratory phenotypes (the cardiovascular
feature set fits them poorly) rank lowest. No leakage (self-comorbidity features excluded).

Artifacts: `paper/MANUSCRIPT.md` (+ `.docx`), `paper/tables/results_by_phenotype.md`,
`paper/tables/results_table.docx` (also `~/Downloads/results table.docx`),
`paper/tables/table1_<ph>.md`, `paper/results/<ph>_build_receipt.json`.

## Reproduce (one command)

`./pipeline/run_all_phenotypes.sh` — derives the phenotype list from
`pipeline/config/phenotypes.yaml`, renders SQL, pulls each cohort from BigQuery if missing,
loads + builds each model through the API in isolation, and writes the results table.
Prereqs: running i2b2 stack (HANDOFF.md "Infra notes"), gcloud + PhysioNet DUA, the venv.
**To add a phenotype: add a `phenotypes:` entry and re-run the script — nothing else.**

## Prediction study (rigorous external-validation paper) — 2026-06-20: COMPLETE (4 items + 4 hardening items)

The second, more rigorous paper (`prediction_study/`, MIMIC-IV→eICU external validation) is
complete through its 4-item plan **and** the adversarial pre-submission hardening pass. Internal
0.907/0.935/0.933 (HF/CKD/DM), external eICU 0.758/0.840/0.761, calibration restored by
intercept+slope recalibration everywhere.
- **Ablation+DCA** for CKD (0.903→0.838) and diabetes (0.856→0.718) added alongside HF.
- **Tool reproduction**: i2b2-ML JSON API HF 0.914 / CKD 0.946 / T2D 0.931 (≤0.011 of harness);
  capability map in `prediction_study/results/tool_capability_map.md`.
- **Manuscript**: `paper/PREDICTION_MANUSCRIPT.md` (+`.docx`) + `paper/TRIPOD_AI_checklist.md`.
- **Polish**: strict-T2D internal 0.919 (vs any 0.933); guideline-variable reference DCA with
  CKD-EPI-2021 eGFR. See `prediction_study/NEXT_STEPS.md` (top) for the full receipt.

### Hardening pass (final) — TRIPOD+AI gaps closed + comparators
- **EPV** (item 8): HF 1,254 / CKD 1,318 / DM 2,123, far above ≥10–20 (`results/epv.json`).
- **Coefficient/spec supplement** (item 14): `results/model_spec_{hf,ckd,dm}.md`.
- **Fairness/subgroup** (AI-3, §3.9): AUROC by sex/age; surfaced a real age gap (HF 0.928 <65 vs
  0.848 ≥65; same pattern CKD/DM). `results/fairness_{hf,ckd,dm}.md`, `results/model_audit_summary.md`.
- **PREVENT-HF** published-equation comparator (§3.7): faithfully implemented (self-test exact, F
  0.081 / M 0.106), ROC AUC 0.778 vs CDW 0.808 on the matched pre-onset cohort (`results/prevent_hf.json`).
- **Necessity assessment** (`prediction_study/NECESSITY_ASSESSMENT.md`): KFRE cut (0.42% UACR
  coverage, wrong outcome); live 546k tool re-load cut (subsampled anyway, feature mismatch, DB risk);
  sampling-sensitivity kept (harness 0.902 on tool's 800/1,600 ≈ 0.907 ≈ 0.914 — no inflation artefact).
- **Only open item**: funding/conflicts (TRIPOD+AI item 20), author-supplied.
- Kavi deliverable: `~/Downloads/results_tables.docx` (journal-formatted 7-table results pack).

## Done this session
- Restarted stack after laptop slept (colima vz; re-provisioned PM session).
- Added 8 phenotypes (ASCVD, dyslipidemia, hypertension, CKD, T2D, OSA, prediabetes, asthma)
  with ICD code sets + per-phenotype self-comorbidity `exclude_features`.
- Made `run_all_phenotypes.sh` a single reproducible script (config-driven + auto BigQuery pull).
- Built all 11; generated the publication results table .docx; updated the manuscript to 11.

## Backlog / next
- [ ] Coauthor review (Wagholikar et al.); author list + i2b2-ML citation (Klann et al., TBD).
- [ ] Phenotype-tailored feature sets (esp. respiratory — asthma/OSA underserved by the
      cardiovascular feature set); config change.
- [ ] Temporal / leakage-aware feature window for any clinical-prediction framing.
- [ ] Review the ICD definitions with Kavi (config has comments; easy to adjust).
- [ ] LLM follow-up paper (separate; `feature/llm-module`).
