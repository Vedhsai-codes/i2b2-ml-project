#!/usr/bin/env bash
# ============================================================================
# run_all_phenotypes.sh — ONE-COMMAND reproduction of every phenotype model,
# built THROUGH the i2b2-ML JSON API on MIMIC-IV.
#
#   ./pipeline/run_all_phenotypes.sh
#
# It derives the phenotype list from pipeline/config/phenotypes.yaml (so adding a
# phenotype is a config edit, nothing else), renders each cohort SQL, pulls the
# cohort from BigQuery if not already on disk, loads it into i2b2, builds the model
# through the API, and writes a combined results table. To add a phenotype: add an
# entry to phenotypes.yaml and re-run this script.
#
# PREREQUISITES
#   1. The i2b2 stack is up with the jobWatcher running and a PM auth session
#      provisioned — see HANDOFF.md "Infra notes" (colima vz; etl image via skopeo;
#      `docker compose up -d --no-deps i2b2-pg-vol-loader i2b2-pg i2b2-etl i2b2-ml`).
#   2. gcloud authenticated with BigQuery access and an approved PhysioNet MIMIC-IV
#      DUA (`bq query` must work against physionet-data.mimiciv_3_1_hosp).
#   3. Python venv with pandas, pyyaml, requests (pip install -r requirements.txt).
#
# Isolation: every phenotype's MIMIC facts + patient sets are wiped before the next
# loads, so cohorts never share observation_fact (no cross-phenotype contamination).
# Trained models (concept_blob under \ML\Diagnosis\) persist for retrieval.
# ============================================================================
set -uo pipefail

cd "$(dirname "$0")/.."
export PY="${PY:-$(pwd)/.venv/bin/python}"
MIMIC="${MIMIC:-$HOME/mimic_data}"
mkdir -p "$MIMIC"

# Phenotype list comes straight from the config — single source of truth.
PHENOTYPES=$($PY -c "import yaml; print(' '.join(yaml.safe_load(open('pipeline/config/phenotypes.yaml'))['phenotypes']))")
echo "Phenotypes: $PHENOTYPES"

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

echo "########## RENDER SQL $(date '+%H:%M:%S') ##########"
$PY pipeline/render_cohort_sql.py --all

echo "########## CLEAN SLATE $(date '+%H:%M:%S') ##########"
wipe_facts
wipe_models

for ph in $PHENOTYPES; do
  csv="$MIMIC/cohort_${ph}.csv"
  if [ ! -s "$csv" ]; then
    echo "########## $ph : PULL COHORT from BigQuery  $(date '+%H:%M:%S') ##########"
    bq query --use_legacy_sql=false --format=csv --max_rows=100000 < "sql/cohort_${ph}.sql" > "$csv" \
      || { echo "  bq pull FAILED for $ph; skipping"; rm -f "$csv"; continue; }
  fi
  rows=$(( $(wc -l < "$csv") - 1 ))
  echo "########## $ph : LOAD + BUILD ($rows cohort rows)  $(date '+%H:%M:%S') ##########"
  ./pipeline/load_and_build.sh "$ph" "$csv"
  echo "########## $ph : runbook rc=$? ##########"
  wipe_facts   # isolate before the next phenotype (model blob persists)
done

echo "########## AGGREGATE $(date '+%H:%M:%S') ##########"
$PY pipeline/aggregate_results.py
echo "########## ALL PHENOTYPES DONE $(date '+%H:%M:%S') ##########"
