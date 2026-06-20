#!/usr/bin/env bash
# ============================================================================
# load_and_build.sh — end-to-end: MIMIC cohort CSV -> model built THROUGH the
#                     i2b2-ML API. Run from the repo root on the Mac cockpit.
#
# Prereqs:
#   * The i2b2 stack is up (deployment/pg docker compose: i2b2-pg, i2b2-etl, i2b2-ml).
#   * The jobWatcher daemon is running in the i2b2-ml container.
#   * You have the wide cohort CSV (from `bq query < sql/cohort_<ph>.sql`).
#   * Python venv active with pandas + pyyaml + requests.
#
# This script is intentionally explicit (one step per i2b2 operation) so each
# step can be run/inspected on its own. Tune the CONFIG block, then run:
#   ./pipeline/load_and_build.sh stroke ~/mimic_data/cohort_stroke.csv
# ============================================================================
set -euo pipefail

PHENOTYPE="${1:?usage: load_and_build.sh <phenotype> <cohort_csv>}"
COHORT_CSV="${2:?usage: load_and_build.sh <phenotype> <cohort_csv>}"

# ---- CONFIG (override via env) ----
ETL_CONTAINER="${ETL_CONTAINER:-i2b2-etl}"      # concept/fact loader runs here
ML_CONTAINER="${ML_CONTAINER:-i2b2-ml}"         # jobWatcher + patient-set creation
BASE_URL="${BASE_URL:-http://localhost:5005}"   # etl Flask (host port; 5000 in-container)
OUT_DIR="${OUT_DIR:-pipeline/out}"
CONTAINER_LOAD_DIR="/usr/src/app/tmp/${PHENOTYPE}_load"
VENV_ACT="source /usr/src/app/.venv/bin/activate"
PY="${PY:-python}"

# Where each step runs:
#   steps 0,1,6  -> HOST (Mac cockpit): SQL render, CSV gen, and the HTTP API driver.
#   steps 2,3,4,5 -> IN-CONTAINER (docker exec): loaders + patient-set creation need
#                    the i2b2_cdi module AND a live CRC DB connection.
# `set -euo pipefail` (above) means any failed step aborts before run_ml_build runs.

echo "== Preflight: stack must be up =="
if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker is not responding. Start Docker Desktop (it was wedged per HANDOFF) and bring up the stack:" >&2
  echo "  cd deployment/pg && docker compose up -d i2b2-pg-vol-loader i2b2-pg i2b2-etl i2b2-ml" >&2
  exit 1
fi
for c in "$ETL_CONTAINER" "$ML_CONTAINER"; do
  if ! docker ps --format '{{.Names}}' | grep -qx "$c"; then
    echo "ERROR: container '$c' is not running. Bring the stack up first." >&2
    exit 1
  fi
done

echo "== [0/6] Render SQL (informational; cohort CSV is assumed already pulled) =="
$PY pipeline/render_cohort_sql.py "$PHENOTYPE"

echo "== [1/6] Generate i2b2 concept/fact/membership CSVs from the cohort CSV =="
$PY pipeline/build_cohort.py "$PHENOTYPE" --cohort "$COHORT_CSV" --out-dir "$OUT_DIR"

echo "== [2/6] Copy load files + patient-set script into the etl container =="
# All loader steps (3,4,5) run in the etl container: it has i2b2_cdi + a live CRC
# DB connection, and is where the concept/fact loaders write. Route everything here
# (no silent 2>/dev/null masking — a failed cp must abort under `set -e`).
docker exec "$ETL_CONTAINER" mkdir -p "$CONTAINER_LOAD_DIR"
docker cp "${OUT_DIR}/${PHENOTYPE}_concepts.csv"   "${ETL_CONTAINER}:${CONTAINER_LOAD_DIR}/"
docker cp "${OUT_DIR}/${PHENOTYPE}_facts.csv"      "${ETL_CONTAINER}:${CONTAINER_LOAD_DIR}/"
docker cp "${OUT_DIR}/${PHENOTYPE}_membership.csv" "${ETL_CONTAINER}:${CONTAINER_LOAD_DIR}/"
docker cp pipeline/create_patient_sets.py "${ETL_CONTAINER}:/usr/src/app/pipeline_create_patient_sets.py"

echo "== [3/6] Load concepts (writes concept_dimension + i2b2 ontology) =="
docker exec "$ETL_CONTAINER" bash -lc "$VENV_ACT && python -m i2b2_cdi concept load -i '$CONTAINER_LOAD_DIR'"

echo "== [4/6] Load facts (--mrn-are-patient-numbers: patient_num == subject_id) =="
docker exec "$ETL_CONTAINER" bash -lc "$VENV_ACT && python -m i2b2_cdi fact load -i '$CONTAINER_LOAD_DIR' --mrn-are-patient-numbers"

echo "== [5/6] Create named positive/negative patient sets (in etl: needs CRC DB + i2b2_cdi) =="
docker exec "$ETL_CONTAINER" bash -lc "$VENV_ACT && python /usr/src/app/pipeline_create_patient_sets.py '$PHENOTYPE' --membership '${CONTAINER_LOAD_DIR}/${PHENOTYPE}_membership.csv'"

echo "== [6/6] Register ML concept + POST jobType:ml build + poll + retrieve model =="
$PY pipeline/run_ml_build.py "$PHENOTYPE" --base-url "$BASE_URL"

echo "== DONE: ${PHENOTYPE} model built through the i2b2-ML API. =="
echo "Inspect the model: GET ${BASE_URL}/etl/concepts?hpath=<ml_concept_path> -> concept_blob.serialized_model"
