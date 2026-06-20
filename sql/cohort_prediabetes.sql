-- ============================================================================
-- cohort_template.sql  —  MIMIC-IV phenotype cohort + structured features
-- ----------------------------------------------------------------------------
-- SOURCE template. Rendered into sql/cohort_<phenotype>.sql by
--   pipeline/render_cohort_sql.py <phenotype>
-- which substitutes the double-at placeholder tokens (label predicate, sampling
-- caps) from pipeline/config/phenotypes.yaml. Do NOT run this file directly (it
-- still contains placeholders); run the rendered output.
--
-- Output: ONE ROW PER PATIENT (subject_id) — the i2b2-ML "analysis unit".
--   subject_id   patient id (becomes observation_fact.patient_num via
--                fact load --mrn-are-patient-numbers)
--   index_date   index-admission date; ALL emitted facts are dated here (v1)
--   label        1 = case (phenotype+), 0 = control (phenotype-)
--   <features>   columns named to match pipeline/config/phenotypes.yaml `features:`
--
-- Cases: earliest admission carrying a label ICD code (Prediabetes / impaired glucose regulation on MIMIC (silver standard ICD-10 R73)).
-- Controls: patients with NONE of the negative-exclusion codes; index = earliest
--           admission. Deterministic sampling via FARM_FINGERPRINT (reproducible).
-- Schema verified 2026-06-18 against physionet-data.mimiciv_3_1_hosp.
-- ============================================================================

WITH
dx AS (
  SELECT subject_id, hadm_id, icd_code, icd_version
  FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
),
adm AS (
  SELECT subject_id, hadm_id, admittime, dischtime, DATE(admittime) AS adm_date
  FROM `physionet-data.mimiciv_3_1_hosp.admissions`
),

-- Patient-level case / exclusion flags across ALL admissions.
flags AS (
  SELECT
    subject_id,
    MAX(CASE WHEN ((d.icd_version = 10 AND (d.icd_code LIKE 'R7303%' OR d.icd_code LIKE 'R7309%' OR d.icd_code LIKE 'R739%')) OR (d.icd_version = 9 AND (d.icd_code LIKE '79021%' OR d.icd_code LIKE '79022%' OR d.icd_code LIKE '79029%'))) THEN 1 ELSE 0 END)        AS is_case,
    MAX(CASE WHEN ((d.icd_version = 10 AND (d.icd_code LIKE 'R73%' OR d.icd_code LIKE 'E08%' OR d.icd_code LIKE 'E09%' OR d.icd_code LIKE 'E10%' OR d.icd_code LIKE 'E11%' OR d.icd_code LIKE 'E13%')) OR (d.icd_version = 9 AND (d.icd_code LIKE '7902%' OR d.icd_code LIKE '250%'))) THEN 1 ELSE 0 END)  AS is_excluded
  FROM dx d
  GROUP BY subject_id
),

-- Index admission for CASES = earliest admission that carries a label code.
case_idx AS (
  SELECT subject_id, hadm_id AS index_hadm, admittime AS index_admittime,
         dischtime AS index_dischtime, adm_date AS index_date
  FROM (
    SELECT a.subject_id, a.hadm_id, a.admittime, a.dischtime, a.adm_date,
           ROW_NUMBER() OVER (PARTITION BY a.subject_id ORDER BY a.admittime) AS rn
    FROM adm a
    JOIN dx d ON d.subject_id = a.subject_id AND d.hadm_id = a.hadm_id
    WHERE ((d.icd_version = 10 AND (d.icd_code LIKE 'R7303%' OR d.icd_code LIKE 'R7309%' OR d.icd_code LIKE 'R739%')) OR (d.icd_version = 9 AND (d.icd_code LIKE '79021%' OR d.icd_code LIKE '79022%' OR d.icd_code LIKE '79029%')))
  )
  WHERE rn = 1
),

-- Index admission for CONTROLS = earliest admission overall.
ctrl_idx AS (
  SELECT subject_id, hadm_id AS index_hadm, admittime AS index_admittime,
         dischtime AS index_dischtime, adm_date AS index_date
  FROM (
    SELECT a.subject_id, a.hadm_id, a.admittime, a.dischtime, a.adm_date,
           ROW_NUMBER() OVER (PARTITION BY a.subject_id ORDER BY a.admittime) AS rn
    FROM adm a
  )
  WHERE rn = 1
),

cases AS (
  SELECT subject_id, index_hadm, index_admittime, index_dischtime, index_date, 1 AS label
  FROM (
    SELECT c.*, ROW_NUMBER() OVER (ORDER BY FARM_FINGERPRINT(CAST(c.subject_id AS STRING))) AS rn
    FROM case_idx c JOIN flags f USING (subject_id)
    WHERE f.is_case = 1
  )
  WHERE rn <= 800
),

controls AS (
  SELECT subject_id, index_hadm, index_admittime, index_dischtime, index_date, 0 AS label
  FROM (
    SELECT c.*, ROW_NUMBER() OVER (ORDER BY FARM_FINGERPRINT(CAST(c.subject_id AS STRING))) AS rn
    FROM ctrl_idx c JOIN flags f USING (subject_id)
    WHERE f.is_case = 0 AND f.is_excluded = 0
  )
  WHERE rn <= 1600
),

cohort AS (
  SELECT * FROM cases
  UNION ALL
  SELECT * FROM controls
),

-- ---- Comorbidities: history up to & including the index admission (binary) ----
comorbid AS (
  SELECT
    co.subject_id,
    MAX(CASE WHEN (d.icd_version=10 AND (d.icd_code LIKE 'I10%' OR d.icd_code LIKE 'I11%' OR d.icd_code LIKE 'I12%' OR d.icd_code LIKE 'I13%' OR d.icd_code LIKE 'I15%'))
                OR (d.icd_version=9  AND (d.icd_code LIKE '401%' OR d.icd_code LIKE '402%' OR d.icd_code LIKE '403%' OR d.icd_code LIKE '404%' OR d.icd_code LIKE '405%')) THEN 1 ELSE 0 END) AS cm_htn,
    MAX(CASE WHEN (d.icd_version=10 AND (d.icd_code LIKE 'E08%' OR d.icd_code LIKE 'E09%' OR d.icd_code LIKE 'E10%' OR d.icd_code LIKE 'E11%' OR d.icd_code LIKE 'E13%'))
                OR (d.icd_version=9  AND d.icd_code LIKE '250%') THEN 1 ELSE 0 END) AS cm_dm,
    MAX(CASE WHEN (d.icd_version=10 AND d.icd_code LIKE 'I48%')
                OR (d.icd_version=9  AND d.icd_code LIKE '4273%') THEN 1 ELSE 0 END) AS cm_afib,
    MAX(CASE WHEN (d.icd_version=10 AND (d.icd_code LIKE 'I20%' OR d.icd_code LIKE 'I21%' OR d.icd_code LIKE 'I22%' OR d.icd_code LIKE 'I23%' OR d.icd_code LIKE 'I24%' OR d.icd_code LIKE 'I25%'))
                OR (d.icd_version=9  AND (d.icd_code LIKE '410%' OR d.icd_code LIKE '411%' OR d.icd_code LIKE '412%' OR d.icd_code LIKE '413%' OR d.icd_code LIKE '414%')) THEN 1 ELSE 0 END) AS cm_ihd,
    MAX(CASE WHEN (d.icd_version=10 AND d.icd_code LIKE 'I50%')
                OR (d.icd_version=9  AND d.icd_code LIKE '428%') THEN 1 ELSE 0 END) AS cm_chf,
    MAX(CASE WHEN (d.icd_version=10 AND d.icd_code LIKE 'E78%')
                OR (d.icd_version=9  AND d.icd_code LIKE '272%') THEN 1 ELSE 0 END) AS cm_hld,
    MAX(CASE WHEN (d.icd_version=10 AND d.icd_code LIKE 'N18%')
                OR (d.icd_version=9  AND d.icd_code LIKE '585%') THEN 1 ELSE 0 END) AS cm_ckd,
    MAX(CASE WHEN (d.icd_version=10 AND d.icd_code LIKE 'I73%')
                OR (d.icd_version=9  AND d.icd_code LIKE '4439%') THEN 1 ELSE 0 END) AS cm_pvd,
    MAX(CASE WHEN (d.icd_version=10 AND (d.icd_code LIKE 'F17%' OR d.icd_code LIKE 'Z720%'))
                OR (d.icd_version=9  AND (d.icd_code LIKE '3051%' OR d.icd_code LIKE 'V1582%')) THEN 1 ELSE 0 END) AS cm_smoke,
    MAX(CASE WHEN (d.icd_version=10 AND d.icd_code LIKE 'I652%')
                OR (d.icd_version=9  AND d.icd_code LIKE '4330%') THEN 1 ELSE 0 END) AS cm_carotid
  FROM cohort co
  JOIN dx  d ON d.subject_id = co.subject_id
  JOIN adm a ON a.subject_id = d.subject_id AND a.hadm_id = d.hadm_id
  WHERE a.admittime <= co.index_admittime
  GROUP BY co.subject_id
),

-- ---- Labs: first measured value during the index admission ----
-- NOTE: d_labitems.label strings below are the common MIMIC-IV names. Confirm on
-- first run with: SELECT DISTINCT label,fluid FROM d_labitems WHERE label LIKE ...
lab_items AS (
  SELECT itemid,
    CASE
      WHEN label = 'Glucose'           AND fluid = 'Blood' THEN 'lab_glucose'
      WHEN label LIKE '%Hemoglobin A1c%'                    THEN 'lab_hba1c'
      WHEN label LIKE 'Cholesterol, LDL%'                   THEN 'lab_ldl'
      WHEN label = 'Cholesterol, HDL'                       THEN 'lab_hdl'
      WHEN label = 'Cholesterol, Total'                     THEN 'lab_chol'
      WHEN label = 'Triglycerides'                          THEN 'lab_trig'
      WHEN label = 'Creatinine'        AND fluid = 'Blood' THEN 'lab_creat'
      WHEN label = 'INR(PT)'                                THEN 'lab_inr'
      WHEN label = 'Hemoglobin'        AND fluid = 'Blood' THEN 'lab_hgb'
      WHEN label = 'Platelet Count'                         THEN 'lab_plt'
      WHEN label = 'White Blood Cells'                      THEN 'lab_wbc'
      WHEN label = 'Sodium'            AND fluid = 'Blood' THEN 'lab_na'
    END AS feat
  FROM `physionet-data.mimiciv_3_1_hosp.d_labitems`
  WHERE (label = 'Glucose'         AND fluid = 'Blood')
     OR  label LIKE '%Hemoglobin A1c%'
     OR  label LIKE 'Cholesterol, LDL%'
     OR  label = 'Cholesterol, HDL'
     OR  label = 'Cholesterol, Total'
     OR  label = 'Triglycerides'
     OR (label = 'Creatinine'      AND fluid = 'Blood')
     OR  label = 'INR(PT)'
     OR (label = 'Hemoglobin'      AND fluid = 'Blood')
     OR  label = 'Platelet Count'
     OR  label = 'White Blood Cells'
     OR (label = 'Sodium'          AND fluid = 'Blood')
),
labs_long AS (
  SELECT co.subject_id, li.feat, le.valuenum,
         ROW_NUMBER() OVER (PARTITION BY co.subject_id, li.feat ORDER BY le.charttime) AS rn
  FROM cohort co
  JOIN `physionet-data.mimiciv_3_1_hosp.labevents` le
    ON le.subject_id = co.subject_id AND le.hadm_id = co.index_hadm
  JOIN lab_items li ON li.itemid = le.itemid
  WHERE li.feat IS NOT NULL AND le.valuenum IS NOT NULL
    AND le.charttime BETWEEN co.index_admittime AND co.index_dischtime
),
labs AS (
  SELECT subject_id,
    MAX(IF(feat='lab_glucose', valuenum, NULL)) AS lab_glucose,
    MAX(IF(feat='lab_hba1c',   valuenum, NULL)) AS lab_hba1c,
    MAX(IF(feat='lab_ldl',     valuenum, NULL)) AS lab_ldl,
    MAX(IF(feat='lab_hdl',     valuenum, NULL)) AS lab_hdl,
    MAX(IF(feat='lab_chol',    valuenum, NULL)) AS lab_chol,
    MAX(IF(feat='lab_trig',    valuenum, NULL)) AS lab_trig,
    MAX(IF(feat='lab_creat',   valuenum, NULL)) AS lab_creat,
    MAX(IF(feat='lab_inr',     valuenum, NULL)) AS lab_inr,
    MAX(IF(feat='lab_hgb',     valuenum, NULL)) AS lab_hgb,
    MAX(IF(feat='lab_plt',     valuenum, NULL)) AS lab_plt,
    MAX(IF(feat='lab_wbc',     valuenum, NULL)) AS lab_wbc,
    MAX(IF(feat='lab_na',      valuenum, NULL)) AS lab_na
  FROM labs_long
  WHERE rn = 1
  GROUP BY subject_id
),

-- ---- OMR vitals: most recent PLAUSIBLE value on/before the index date ----
-- (plausibility filter applied BEFORE ranking so a garbage most-recent reading
--  doesn't shadow a valid earlier one.)
omr_bp AS (
  SELECT subject_id, sbp, dbp FROM (
    SELECT co.subject_id,
      SAFE_CAST(SPLIT(o.result_value, '/')[SAFE_OFFSET(0)] AS FLOAT64) AS sbp,
      SAFE_CAST(SPLIT(o.result_value, '/')[SAFE_OFFSET(1)] AS FLOAT64) AS dbp,
      o.chartdate
    FROM cohort co
    JOIN `physionet-data.mimiciv_3_1_hosp.omr` o ON o.subject_id = co.subject_id
    WHERE o.result_name = 'Blood Pressure' AND o.chartdate <= co.index_date
  )
  WHERE sbp BETWEEN 50 AND 300 AND dbp BETWEEN 20 AND 200
  QUALIFY ROW_NUMBER() OVER (PARTITION BY subject_id ORDER BY chartdate DESC) = 1
),
omr_bmi AS (
  SELECT subject_id, bmi FROM (
    SELECT co.subject_id,
      SAFE_CAST(o.result_value AS FLOAT64) AS bmi,
      o.chartdate
    FROM cohort co
    JOIN `physionet-data.mimiciv_3_1_hosp.omr` o ON o.subject_id = co.subject_id
    WHERE o.result_name = 'BMI (kg/m2)' AND o.chartdate <= co.index_date
  )
  WHERE bmi BETWEEN 10 AND 100
  QUALIFY ROW_NUMBER() OVER (PARTITION BY subject_id ORDER BY chartdate DESC) = 1
),

-- ---- Medications: any order during the index admission (binary) ----
meds AS (
  SELECT co.subject_id,
    MAX(IF(REGEXP_CONTAINS(LOWER(p.drug), r'lisinopril|amlodipine|metoprolol|losartan|valsartan|hydrochlorothiazide|atenolol|carvedilol|enalapril|diltiazem|furosemide|chlorthalidone|olmesartan'), 1, 0)) AS med_aht,
    MAX(IF(REGEXP_CONTAINS(LOWER(p.drug), r'statin'), 1, 0))                                                                                                                                      AS med_statin,
    MAX(IF(REGEXP_CONTAINS(LOWER(p.drug), r'warfarin|heparin|apixaban|rivaroxaban|dabigatran|enoxaparin|edoxaban'), 1, 0))                                                                        AS med_ac,
    MAX(IF(REGEXP_CONTAINS(LOWER(p.drug), r'aspirin|clopidogrel|ticagrelor|prasugrel|dipyridamole'), 1, 0))                                                                                       AS med_ap,
    MAX(IF(REGEXP_CONTAINS(LOWER(p.drug), r'metformin|insulin|glipizide|glyburide|sitagliptin|empagliflozin|glimepiride|pioglitazone|dapagliflozin'), 1, 0))                                      AS med_ad
  FROM cohort co
  JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` p
    ON p.subject_id = co.subject_id AND p.hadm_id = co.index_hadm
  GROUP BY co.subject_id
)

SELECT
  co.subject_id,
  co.index_date,
  co.label,
  -- demographics
  pt.anchor_age                       AS age,
  IF(pt.gender = 'M', 1, 0)           AS sex_male,
  -- comorbidities
  COALESCE(cm.cm_htn,    0)           AS cm_htn,
  COALESCE(cm.cm_dm,     0)           AS cm_dm,
  COALESCE(cm.cm_afib,   0)           AS cm_afib,
  COALESCE(cm.cm_ihd,    0)           AS cm_ihd,
  COALESCE(cm.cm_chf,    0)           AS cm_chf,
  COALESCE(cm.cm_hld,    0)           AS cm_hld,
  COALESCE(cm.cm_ckd,    0)           AS cm_ckd,
  COALESCE(cm.cm_pvd,    0)           AS cm_pvd,
  COALESCE(cm.cm_smoke,  0)           AS cm_smoke,
  COALESCE(cm.cm_carotid,0)           AS cm_carotid,
  -- labs (NULL when not measured during index admission)
  lb.lab_glucose, lb.lab_hba1c, lb.lab_ldl, lb.lab_hdl, lb.lab_chol, lb.lab_trig,
  lb.lab_creat, lb.lab_inr, lb.lab_hgb, lb.lab_plt, lb.lab_wbc, lb.lab_na,
  -- vitals
  bp.sbp                              AS vit_sbp,
  bp.dbp                              AS vit_dbp,
  bm.bmi                              AS vit_bmi,
  -- medications
  COALESCE(md.med_aht,    0)          AS med_aht,
  COALESCE(md.med_statin, 0)          AS med_statin,
  COALESCE(md.med_ac,     0)          AS med_ac,
  COALESCE(md.med_ap,     0)          AS med_ap,
  COALESCE(md.med_ad,     0)          AS med_ad
FROM cohort co
JOIN `physionet-data.mimiciv_3_1_hosp.patients` pt ON pt.subject_id = co.subject_id
LEFT JOIN comorbid cm ON cm.subject_id = co.subject_id
LEFT JOIN labs     lb ON lb.subject_id = co.subject_id
LEFT JOIN omr_bp   bp ON bp.subject_id = co.subject_id
LEFT JOIN omr_bmi  bm ON bm.subject_id = co.subject_id
LEFT JOIN meds     md ON md.subject_id = co.subject_id
ORDER BY co.subject_id
