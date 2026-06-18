-- Demographics + clinical fields for the i2b2-ML LLM extension cohort.
-- One row per admission in the cohort (same 1000 rows as sql/cohort_v1.sql).
-- The Python script evaluation/demographics_table.py reads this CSV and
-- emits the paper's Table 1.

WITH cohort AS (
  SELECT DISTINCT
    n.subject_id,
    n.hadm_id
  FROM `physionet-data.mimiciv_note.discharge` n
  JOIN `physionet-data.mimiciv_3_1_hosp.patients` p
    ON n.subject_id = p.subject_id
  WHERE p.anchor_age >= 18
    AND LENGTH(n.text) > 500
    AND LENGTH(n.text) < 50000
),
gold AS (
  SELECT
    hadm_id,
    MAX(CASE WHEN icd_version=10 AND icd_code LIKE 'I50%' THEN 1 ELSE 0 END) AS hf_gold,
    MAX(CASE WHEN icd_version=10 AND (icd_code LIKE 'E08%' OR icd_code LIKE 'E09%' OR icd_code LIKE 'E10%' OR icd_code LIKE 'E11%' OR icd_code LIKE 'E13%') THEN 1 ELSE 0 END) AS dm_any,
    MAX(CASE WHEN icd_version=10 AND (icd_code LIKE 'I10%' OR icd_code LIKE 'I11%' OR icd_code LIKE 'I12%' OR icd_code LIKE 'I13%' OR icd_code LIKE 'I15%') THEN 1 ELSE 0 END) AS htn,
    MAX(CASE WHEN icd_version=10 AND icd_code LIKE 'N18%' THEN 1 ELSE 0 END) AS ckd,
    MAX(CASE WHEN icd_version=10 AND icd_code LIKE 'J44%' THEN 1 ELSE 0 END) AS copd,
    MAX(CASE WHEN icd_version=10 AND icd_code LIKE 'I48%' THEN 1 ELSE 0 END) AS afib,
    MAX(CASE WHEN icd_version=10 AND (icd_code LIKE 'I20%' OR icd_code LIKE 'I21%' OR icd_code LIKE 'I22%' OR icd_code LIKE 'I23%' OR icd_code LIKE 'I24%' OR icd_code LIKE 'I25%') THEN 1 ELSE 0 END) AS ihd,
    MAX(CASE WHEN icd_version=10 AND (icd_code LIKE 'I63%' OR icd_code LIKE 'I64%') THEN 1 ELSE 0 END) AS stroke
  FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  GROUP BY hadm_id
),
cohort_with_gold AS (
  SELECT
    c.*,
    COALESCE(g.hf_gold, 0) AS hf_gold,
    COALESCE(g.dm_any, 0) AS dm_any,
    COALESCE(g.htn,    0) AS htn,
    COALESCE(g.ckd,    0) AS ckd,
    COALESCE(g.copd,   0) AS copd,
    COALESCE(g.afib,   0) AS afib,
    COALESCE(g.ihd,    0) AS ihd,
    COALESCE(g.stroke, 0) AS stroke
  FROM cohort c
  LEFT JOIN gold g ON c.hadm_id = g.hadm_id
),
selected_cohort AS (
  SELECT * FROM cohort_with_gold ORDER BY subject_id LIMIT 1000
),
icu_flag AS (
  SELECT DISTINCT hadm_id FROM `physionet-data.mimiciv_3_1_icu.icustays`
)
SELECT
  s.subject_id,
  s.hadm_id,
  s.hf_gold,
  -- demographics
  p.gender,
  p.anchor_age AS age,
  -- admission-level
  a.race,
  a.insurance,
  a.marital_status,
  a.language,
  a.admission_type,
  a.admission_location,
  a.discharge_location,
  a.hospital_expire_flag AS died_inhospital,
  TIMESTAMP_DIFF(a.dischtime, a.admittime, HOUR) / 24.0 AS los_days,
  -- ICU?
  CASE WHEN icu.hadm_id IS NOT NULL THEN 1 ELSE 0 END AS had_icu_stay,
  -- comorbidities
  s.dm_any,
  s.htn,
  s.ckd,
  s.copd,
  s.afib,
  s.ihd,
  s.stroke
FROM selected_cohort s
JOIN `physionet-data.mimiciv_3_1_hosp.patients` p
  ON s.subject_id = p.subject_id
JOIN `physionet-data.mimiciv_3_1_hosp.admissions` a
  ON s.hadm_id = a.hadm_id
LEFT JOIN icu_flag icu
  ON s.hadm_id = icu.hadm_id
ORDER BY s.subject_id
