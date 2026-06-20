# STATE.md

**Updated:** 2026-06-20 (overnight live-build session on the new laptop)
**Branch:** `feature/phenotype-ml-pipeline`

## Where we are

The aligned grant deliverable is **done end-to-end**: three phenotype models built
**through the i2b2-ML JSON API** on MIMIC-IV, each `COMPLETED` with the model retrieved
from `concept_blob`. A full manuscript draft exists.

| Phenotype | ROC AUC | Acc | Prec | Rec | F1 | Status |
|---|---|---|---|---|---|---|
| Ischemic stroke | 0.891 | 0.811 | 0.686 | 0.792 | 0.736 | ✅ COMPLETED |
| Heart failure | 0.914 | 0.842 | 0.734 | 0.824 | 0.776 | ✅ COMPLETED |
| Ischemic heart disease | 0.893 | 0.807 | 0.659 | 0.872 | 0.751 | ✅ COMPLETED |

Artifacts: `paper/MANUSCRIPT.md` (+ `.docx`), `paper/tables/results_by_phenotype.md`,
`paper/tables/table1_<ph>.md`, `paper/results/<ph>_build_receipt.json`.

## How to reproduce (new laptop)

1. Runtime: `colima start --vm-type vz --cpu 4 --memory 8 --disk 60` (qemu/gVisor net
   corrupts the etl image pull; vz fixes most, but the etl image must still be fetched on
   the **host** via `skopeo` → `docker load`). See HANDOFF.md "Infra notes".
2. Stack: `cd deployment/pg && docker compose up -d --no-deps i2b2-pg-vol-loader i2b2-pg
   i2b2-etl i2b2-ml`; restart `i2b2-ml` after etl bootstraps; provision a PM session row.
3. Build all: `./pipeline/run_all_phenotypes.sh` → metrics in `paper/tables/`.

## Done this session
- New-laptop infra brought up (colima vz, skopeo image load, stack, auth session).
- Fixed `label_path` leaf-vs-code mismatch (empty-label/SMOTE crash).
- Found + fixed self-comorbidity label leakage (`exclude_features` per phenotype).
- Hardened the runbook (patient-set step) + added `run_all_phenotypes.sh`,
  `aggregate_results.py`, `cohort_table1.py`.
- Built all 3 models, generated tables + Table 1s, wrote the manuscript.

## Backlog / next
- [ ] Coauthor review (Kavi/Wagholikar et al.); fill author list + i2b2-ML citation.
- [ ] Temporal / leakage-aware feature window (features strictly before the event) for any
      clinical-prediction framing — narrow the engine `data_period` window.
- [ ] Add Kavi's emailed phenotypes/risk factors when received (config-only).
- [ ] Optional: figures (ROC curves per phenotype) from the engine output.
- [ ] LLM follow-up paper (separate; `feature/llm-module`).
- [ ] Stale-state caveat: the local i2b2 DB is wiped between builds by the runbook; the
      persisted model blobs (`*_ML` concepts) remain for retrieval.
