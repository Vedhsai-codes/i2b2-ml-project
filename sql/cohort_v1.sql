-- DEMONSTRATION COHORT v1
-- Adult patients with at least one discharge note + ICD-10 coding
-- Gold standard: heart failure = any I50.* in diagnoses
--
-- Source dataset: physionet-data.mimiciv_3_1_hosp + physionet-data.mimiciv_note
-- DUA: PhysioNet Credentialed Health Data License (per-user, CITI-required).
--
-- Run from BigQuery console or `bq query --use_legacy_sql=false < cohort_v1.sql > cohort.csv`.
-- Expected runtime: < 60 seconds. Expected row count: up to 1000 (LIMIT).
--
-- Output columns:
--   subject_id  - de-identified patient ID
--   hadm_id     - de-identified hospital admission ID
--   note_id     - discharge-note ID
--   note_date   - charttime of the note
--   text        - discharge-summary free text (the LLM input)
--   hf_gold     - 1 if any I50.* ICD-10 code for this admission, else 0

WITH cohort AS (
  SELECT DISTINCT
    n.subject_id,
    n.hadm_id,
    n.note_id,
    n.charttime AS note_date,
    n.text
  FROM `physionet-data.mimiciv_note.discharge` n
  JOIN `physionet-data.mimiciv_3_1_hosp.patients` p
    ON n.subject_id = p.subject_id
  WHERE p.anchor_age >= 18
    AND LENGTH(n.text) > 500       -- filter blanks/stubs
    AND LENGTH(n.text) < 50000     -- filter extreme outliers
),
gold AS (
  SELECT
    hadm_id,
    MAX(CASE
      WHEN icd_version = 10 AND icd_code LIKE 'I50%' THEN 1
      ELSE 0
    END) AS hf_gold
  FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  GROUP BY hadm_id
)
SELECT
  c.subject_id,
  c.hadm_id,
  c.note_id,
  c.note_date,
  c.text,
  COALESCE(g.hf_gold, 0) AS hf_gold
FROM cohort c
LEFT JOIN gold g ON c.hadm_id = g.hadm_id
ORDER BY c.subject_id
LIMIT 1000
