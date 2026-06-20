#!/usr/bin/env bash
# Item 4 evals (identification cohorts, 546k rows — slow):
#   1. any-diabetes internal baseline (reproduce ~0.933)
#   2. strict type-2 diabetes internal (the sensitivity)
#   3. HF identification full model (reproduce ~0.907)
#   4. HF guideline-variable reference model (PREVENT-HF-available factors + CKD-EPI eGFR)
#   5. DCA: full vs guideline-variable reference (the established-risk-factor comparator)
set -u
cd "$(dirname "$0")"
PY=/Users/Vedhsai/i2b2-ml-project/.venv/bin/python
LOG=logs/item4_eval.log
: > "$LOG"
run() { echo "[$(date +%H:%M:%S)] $*" >>"$LOG"; "$@" >>"$LOG" 2>&1; }

run $PY identify_eval.py --csv data/dm_mimic.csv       --drop cm_dm  --tag dm_id_full
run $PY identify_eval.py --csv data/dmstrict_mimic.csv --drop cm_dm  --tag dmstrict_id_full
run $PY identify_eval.py --csv data/hf_mimic_identify.csv            --tag hf_id_full
run $PY identify_eval.py --csv data/hf_mimic_identify.csv \
        --keep age,sex_male,vit_sbp,med_aht,cm_dm,cm_smoke,vit_bmi --egfr --tag hf_id_ref
echo "[$(date +%H:%M:%S)] DCA full-vs-reference" >>"$LOG"
$PY dca.py --concurrent hf_id_full --preonset hf_id_ref --label "heart failure (identification)" \
        --out hf_reference_dca --leg1 "Full CDW model (30 features)" \
        --leg2 "Guideline risk factors + eGFR" --col1 "#185FA5" --col2 "#cc8a1a" >>"$LOG" 2>&1
echo "[$(date +%H:%M:%S)] ITEM4 EVALS COMPLETE" >>"$LOG"
