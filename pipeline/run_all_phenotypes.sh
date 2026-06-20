#!/usr/bin/env bash
# ============================================================================
# run_all_phenotypes.sh — clean, ISOLATED end-to-end build of every configured
# phenotype THROUGH the i2b2-ML JSON API.
#
# Why isolation: all phenotype cohorts are loaded into the same observation_fact
# table. If two cohorts share a patient, that patient's feature facts get loaded
# twice (different index dates) -> duplicate/contaminated facts. To keep each
# build clean we wipe a phenotype's MIMIC facts + patient sets BEFORE the next
# phenotype loads. The trained model (concept_blob under \ML\Diagnosis\) persists
# across wipes, so all models are retrievable at the end.
#
# Run from repo root (stack must be up, jobWatcher running):
#   ./pipeline/run_all_phenotypes.sh
# ============================================================================
set -uo pipefail

cd "$(dirname "$0")/.."
export PY="${PY:-$(pwd)/.venv/bin/python}"
MIMIC="${MIMIC:-$HOME/mimic_data}"

PHENOTYPES=(
  "stroke:cohort_stroke.csv"
  "heart_failure:cohort_heart_failure.csv"
  "ischemic_heart_disease:cohort_ischemic_heart_disease.csv"
)

wipe_facts() {   # remove MIMIC concepts + facts + patient sets (KEEP \ML\ model blobs)
  docker exec -i i2b2-pg psql -U postgres -d i2b2 >/dev/null 2>&1 <<'SQL'
DELETE FROM i2b2demodata.observation_fact WHERE concept_cd IN
  (SELECT concept_cd FROM i2b2demodata.concept_dimension WHERE concept_path LIKE '\\MIMIC\\%');
DELETE FROM i2b2demodata.qt_patient_set_collection WHERE result_instance_id IN (
  SELECT qri.result_instance_id FROM i2b2demodata.qt_query_result_instance qri
  JOIN i2b2demodata.qt_query_instance qi ON qri.query_instance_id=qi.query_instance_id
  JOIN i2b2demodata.qt_query_master qm ON qi.query_master_id=qm.query_master_id
  WHERE qm.name ~ '_(pos|neg)$');
DELETE FROM i2b2demodata.qt_query_result_instance WHERE query_instance_id IN (
  SELECT qi.query_instance_id FROM i2b2demodata.qt_query_instance qi
  JOIN i2b2demodata.qt_query_master qm ON qi.query_master_id=qm.query_master_id
  WHERE qm.name ~ '_(pos|neg)$');
DELETE FROM i2b2demodata.qt_query_instance WHERE query_master_id IN (
  SELECT query_master_id FROM i2b2demodata.qt_query_master WHERE name ~ '_(pos|neg)$');
DELETE FROM i2b2demodata.qt_query_master WHERE name ~ '_(pos|neg)$';
DELETE FROM i2b2demodata.concept_dimension WHERE concept_path LIKE '\\MIMIC\\%';
SQL
}

wipe_models() {  # remove prior ML concepts + ml jobs so each rebuild is clean
  docker exec -i i2b2-pg psql -U postgres -d i2b2 >/dev/null 2>&1 <<'SQL'
DELETE FROM i2b2demodata.concept_dimension WHERE concept_path LIKE '\\ML\\%';
DELETE FROM i2b2demodata.job WHERE job_type='ml';
SQL
}

echo "########## CLEAN SLATE $(date '+%H:%M:%S') ##########"
wipe_facts
wipe_models

for entry in "${PHENOTYPES[@]}"; do
  ph="${entry%%:*}"; csv="${entry##*:}"
  echo ""
  echo "########## $ph : LOAD + BUILD  $(date '+%H:%M:%S') ##########"
  ./pipeline/load_and_build.sh "$ph" "$MIMIC/$csv"
  echo "########## $ph : runbook rc=$? ##########"
  wipe_facts   # isolate before the next phenotype (model blob persists)
done

echo ""
echo "########## AGGREGATE $(date '+%H:%M:%S') ##########"
$PY pipeline/aggregate_results.py
echo "########## ALL PHENOTYPES DONE $(date '+%H:%M:%S') ##########"
