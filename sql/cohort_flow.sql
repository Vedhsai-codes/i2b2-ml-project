-- COHORT FLOW (CONSORT-style) — count at each filter step of sql/cohort_v1.sql.
-- Produces one row per filter step so we can render the cohort-flow figure
-- for the paper's Methods section. Each step is a CTE built on the previous.

WITH
step1_all_patients AS (
  SELECT subject_id FROM `physionet-data.mimiciv_3_1_hosp.patients`
),
step2_adults AS (
  SELECT subject_id FROM `physionet-data.mimiciv_3_1_hosp.patients`
  WHERE anchor_age >= 18
),
step3_with_note AS (
  SELECT DISTINCT n.subject_id, n.hadm_id, n.note_id
  FROM `physionet-data.mimiciv_note.discharge` n
  JOIN `physionet-data.mimiciv_3_1_hosp.patients` p
    ON n.subject_id = p.subject_id
  WHERE p.anchor_age >= 18
),
step4_length_filter AS (
  SELECT DISTINCT n.subject_id, n.hadm_id, n.note_id, n.text
  FROM `physionet-data.mimiciv_note.discharge` n
  JOIN `physionet-data.mimiciv_3_1_hosp.patients` p
    ON n.subject_id = p.subject_id
  WHERE p.anchor_age >= 18
    AND LENGTH(n.text) > 500
    AND LENGTH(n.text) < 50000
),
step5_with_gold AS (
  -- A patient/admission with note + a HF gold label assignable
  SELECT
    s.subject_id, s.hadm_id, s.note_id,
    COALESCE(MAX(CASE WHEN d.icd_version=10 AND d.icd_code LIKE 'I50%' THEN 1 ELSE 0 END), 0) AS hf_gold
  FROM step4_length_filter s
  LEFT JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d
    ON s.hadm_id = d.hadm_id
  GROUP BY s.subject_id, s.hadm_id, s.note_id
),
step6_final_cohort AS (
  -- After ORDER BY + LIMIT 1000 (matches sql/cohort_v1.sql)
  SELECT * FROM step5_with_gold ORDER BY subject_id LIMIT 1000
)
SELECT
  'step1_all_patients'         AS step, COUNT(*) AS n,                                                  COUNT(DISTINCT subject_id) AS n_patients FROM step1_all_patients
UNION ALL SELECT
  'step2_adults_18plus',                COUNT(*),                                                       COUNT(DISTINCT subject_id) FROM step2_adults
UNION ALL SELECT
  'step3_with_discharge_note',          COUNT(*),                                                       COUNT(DISTINCT subject_id) FROM step3_with_note
UNION ALL SELECT
  'step4_note_length_500_to_50000',     COUNT(*),                                                       COUNT(DISTINCT subject_id) FROM step4_length_filter
UNION ALL SELECT
  'step5_after_gold_assignment',        COUNT(*),                                                       COUNT(DISTINCT subject_id) FROM step5_with_gold
UNION ALL SELECT
  'step6_final_cohort_LIMIT_1000',      COUNT(*),                                                       COUNT(DISTINCT subject_id) FROM step6_final_cohort
UNION ALL SELECT
  'step7_final_HF_positive',            (SELECT COUNT(*) FROM step6_final_cohort WHERE hf_gold = 1),    (SELECT COUNT(DISTINCT subject_id) FROM step6_final_cohort WHERE hf_gold = 1)
UNION ALL SELECT
  'step7_final_HF_negative',            (SELECT COUNT(*) FROM step6_final_cohort WHERE hf_gold = 0),    (SELECT COUNT(DISTINCT subject_id) FROM step6_final_cohort WHERE hf_gold = 0)
ORDER BY step
