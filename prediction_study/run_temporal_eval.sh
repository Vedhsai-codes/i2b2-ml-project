#!/usr/bin/env bash
# Evaluate the CKD/DM temporal cohorts at each blackout, then build decay + DCA
# figures per condition. Each eval is gated on its BigQuery pull having finished
# (DONE marker in logs/pull_temporal.log) to avoid racing a half-written CSV.
set -u
cd "$(dirname "$0")"
PY=/Users/Vedhsai/i2b2-ml-project/.venv/bin/python
LOG=logs/eval_temporal.log
: > "$LOG"

wait_for() {  # cond b -> block until pull DONE marker present (max ~10 min)
  local cond=$1 b=$2 tries=0
  while ! grep -q "DONE ${cond} b=${b} " logs/pull_temporal.log 2>/dev/null; do
    sleep 5; tries=$((tries+1)); [ $tries -gt 120 ] && { echo "TIMEOUT waiting for ${cond} b=${b}" >>"$LOG"; return 1; }
  done
}

for cond in ckd dm; do
  case $cond in
    ckd) LABEL="chronic kidney disease"; SHORT="CKD";;
    dm)  LABEL="diabetes";               SHORT="diabetes";;
  esac
  for b in 0 30 90 180; do
    wait_for "$cond" "$b" || continue
    echo "[$(date +%H:%M:%S)] eval ${cond}_b${b}" >>"$LOG"
    $PY evaluate.py --csv data/${cond}_b${b}.csv --tag ${cond}_b${b} >>"$LOG" 2>&1
    echo "[$(date +%H:%M:%S)] done ${cond}_b${b} -> $(grep -o '\"auroc\": [0-9.]*' results/${cond}_b${b}.json | head -1)" >>"$LOG"
  done
  echo "[$(date +%H:%M:%S)] figures for ${cond}" >>"$LOG"
  $PY make_decay_figure.py --prefix ${cond} --label "$LABEL" --short "$SHORT" >>"$LOG" 2>&1
  $PY dca.py --concurrent ${cond}_b0 --preonset ${cond}_b180 --label "$LABEL" --out ${cond}_dca >>"$LOG" 2>&1
  echo "[$(date +%H:%M:%S)] FIGURES DONE ${cond}" >>"$LOG"
done
echo "[$(date +%H:%M:%S)] ALL TEMPORAL EVALS + FIGURES COMPLETE" >>"$LOG"
