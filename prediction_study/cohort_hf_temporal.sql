-- ============================================================================
-- cohort_hf_temporal.sql — incident heart-failure cohort with a BLACKOUT-window
-- feature cutoff, for the leakage / lead-time ablation.
--
-- One row per patient.
--   label = 1  incident HF: patient's FIRST HF admission (ICD-10 I50 / ICD-9 428),
--              AND has >=1 prior admission (so pre-onset history exists). Because
--              onset = first HF code, no HF exists before the anchor by construction
--              (so cm_chf is structurally absent pre-onset — no self-comorbidity leak).
--   label = 0  never-HF patient with >=2 admissions.
--   anchor_time = HF onset admittime (cases) / last admittime (controls).
--   feature admission = the most recent admission with
--                       admittime <= anchor_time - <BLACKOUT> days.
--   All features are computed from that feature admission only.
--
-- Vary BLACKOUT_PLACEHOLDER in {0, 30, 90, 180}:
--   0   -> features come from the index/anchor (HF) admission itself  = CONCURRENT (leaky)
--   30/90/180 -> features come from a hospital visit >= N days before HF onset.
-- The AUROC decay from 0 -> 180 quantifies how much the concurrent design inflated it.
-- Natural prevalence (no case:control ratio forcing). MIMIC-IV v3.1 hosp.
-- ============================================================================

WITH
hf_dx AS (
  SELECT DISTINCT subject_id, hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  WHERE (icd_version = 10 AND icd_code LIKE 'I50%')
     OR (icd_version = 9  AND icd_code LIKE '428%')
),
adm AS (
  SELECT subject_id, hadm_id, admittime, dischtime
  FROM `physionet-data.mimiciv_3_1_hosp.admissions`
),
hf_onset AS (
  SELECT a.subject_id, MIN(a.admittime) AS onset_time
  FROM adm a JOIN hf_dx h USING (subject_id, hadm_id)
  GROUP BY a.subject_id
),
n_adm AS (SELECT subject_id, COUNT(*) AS n FROM adm GROUP BY subject_id),

cases AS (
  SELECT o.subject_id, o.onset_time AS anchor_time, 1 AS label
  FROM hf_onset o
  WHERE EXISTS (SELECT 1 FROM adm a
                WHERE a.subject_id = o.subject_id AND a.admittime < o.onset_time)
),
controls AS (
  SELECT a.subject_id, MAX(a.admittime) AS anchor_time, 0 AS label
  FROM adm a JOIN n_adm na USING (subject_id)
  WHERE a.subject_id NOT IN (SELECT subject_id FROM hf_onset)
    AND na.n >= 2
  GROUP BY a.subject_id
),
cohort AS (SELECT * FROM cases UNION ALL SELECT * FROM controls),

-- feature admission = most recent admission at/before the blackout cutoff
feat_adm AS (
  SELECT c.subject_id, c.label, c.anchor_time,
         a.hadm_id AS feat_hadm, a.admittime AS feat_admit, a.dischtime AS feat_disch
  FROM cohort c
  JOIN adm a
    ON a.subject_id = c.subject_id
   AND a.admittime <= TIMESTAMP_SUB(c.anchor_time, INTERVAL BLACKOUT_PLACEHOLDER DAY)
  QUALIFY ROW_NUMBER() OVER (PARTITION BY c.subject_id ORDER BY a.admittime DESC) = 1
),

-- comorbidities: any qualifying dx in admissions up to & including the feature admission
comorbid AS (
  SELECT f.subject_id,
    MAX(CASE WHEN (d.icd_version=10 AND (d.icd_code LIKE 'I10%' OR d.icd_code LIKE 'I11%' OR d.icd_code LIKE 'I12%' OR d.icd_code LIKE 'I13%' OR d.icd_code LIKE 'I15%'))
              OR (d.icd_version=9 AND (d.icd_code LIKE '401%' OR d.icd_code LIKE '402%' OR d.icd_code LIKE '403%' OR d.icd_code LIKE '404%' OR d.icd_code LIKE '405%')) THEN 1 ELSE 0 END) AS cm_htn,
    MAX(CASE WHEN (d.icd_version=10 AND (d.icd_code LIKE 'E08%' OR d.icd_code LIKE 'E09%' OR d.icd_code LIKE 'E10%' OR d.icd_code LIKE 'E11%' OR d.icd_code LIKE 'E13%'))
              OR (d.icd_version=9 AND d.icd_code LIKE '250%') THEN 1 ELSE 0 END) AS cm_dm,
    MAX(CASE WHEN (d.icd_version=10 AND d.icd_code LIKE 'I48%') OR (d.icd_version=9 AND d.icd_code LIKE '4273%') THEN 1 ELSE 0 END) AS cm_afib,
    MAX(CASE WHEN (d.icd_version=10 AND (d.icd_code LIKE 'I20%' OR d.icd_code LIKE 'I21%' OR d.icd_code LIKE 'I22%' OR d.icd_code LIKE 'I23%' OR d.icd_code LIKE 'I24%' OR d.icd_code LIKE 'I25%'))
              OR (d.icd_version=9 AND (d.icd_code LIKE '410%' OR d.icd_code LIKE '411%' OR d.icd_code LIKE '412%' OR d.icd_code LIKE '413%' OR d.icd_code LIKE '414%')) THEN 1 ELSE 0 END) AS cm_ihd,
    MAX(CASE WHEN (d.icd_version=10 AND d.icd_code LIKE 'E78%') OR (d.icd_version=9 AND d.icd_code LIKE '272%') THEN 1 ELSE 0 END) AS cm_hld,
    MAX(CASE WHEN (d.icd_version=10 AND d.icd_code LIKE 'N18%') OR (d.icd_version=9 AND d.icd_code LIKE '585%') THEN 1 ELSE 0 END) AS cm_ckd,
    MAX(CASE WHEN (d.icd_version=10 AND d.icd_code LIKE 'I73%') OR (d.icd_version=9 AND d.icd_code LIKE '4439%') THEN 1 ELSE 0 END) AS cm_pvd,
    MAX(CASE WHEN (d.icd_version=10 AND (d.icd_code LIKE 'F17%' OR d.icd_code LIKE 'Z720%')) OR (d.icd_version=9 AND (d.icd_code LIKE '3051%' OR d.icd_code LIKE 'V1582%')) THEN 1 ELSE 0 END) AS cm_smoke
  FROM feat_adm f
  JOIN adm a2 ON a2.subject_id = f.subject_id AND a2.admittime <= f.feat_admit
  JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d
    ON d.subject_id = a2.subject_id AND d.hadm_id = a2.hadm_id
  GROUP BY f.subject_id
),

lab_items AS (
  SELECT itemid,
    CASE
      WHEN label = 'Glucose'            AND fluid='Blood' THEN 'lab_glucose'
      WHEN label LIKE '%Hemoglobin A1c%'                  THEN 'lab_hba1c'
      WHEN label = 'Creatinine'         AND fluid='Blood' THEN 'lab_creat'
      WHEN label = 'INR(PT)'                              THEN 'lab_inr'
      WHEN label = 'Hemoglobin'         AND fluid='Blood' THEN 'lab_hgb'
      WHEN label = 'Platelet Count'                       THEN 'lab_plt'
      WHEN label = 'White Blood Cells'                    THEN 'lab_wbc'
      WHEN label = 'Sodium'             AND fluid='Blood' THEN 'lab_na'
      WHEN label = 'Potassium'          AND fluid='Blood' THEN 'lab_k'
      WHEN label = 'Bicarbonate'        AND fluid='Blood' THEN 'lab_hco3'
      WHEN label = 'Urea Nitrogen'      AND fluid='Blood' THEN 'lab_bun'
      WHEN label = 'Chloride'           AND fluid='Blood' THEN 'lab_cl'
    END AS feat
  FROM `physionet-data.mimiciv_3_1_hosp.d_labitems`
),
labs_long AS (
  SELECT f.subject_id, li.feat, le.valuenum,
         ROW_NUMBER() OVER (PARTITION BY f.subject_id, li.feat ORDER BY le.charttime) AS rn
  FROM feat_adm f
  JOIN `physionet-data.mimiciv_3_1_hosp.labevents` le
    ON le.subject_id = f.subject_id AND le.hadm_id = f.feat_hadm
  JOIN lab_items li ON li.itemid = le.itemid
  WHERE li.feat IS NOT NULL AND le.valuenum IS NOT NULL
),
labs AS (
  SELECT subject_id,
    MAX(IF(feat='lab_glucose', valuenum, NULL)) AS lab_glucose,
    MAX(IF(feat='lab_hba1c',   valuenum, NULL)) AS lab_hba1c,
    MAX(IF(feat='lab_creat',   valuenum, NULL)) AS lab_creat,
    MAX(IF(feat='lab_inr',     valuenum, NULL)) AS lab_inr,
    MAX(IF(feat='lab_hgb',     valuenum, NULL)) AS lab_hgb,
    MAX(IF(feat='lab_plt',     valuenum, NULL)) AS lab_plt,
    MAX(IF(feat='lab_wbc',     valuenum, NULL)) AS lab_wbc,
    MAX(IF(feat='lab_na',      valuenum, NULL)) AS lab_na,
    MAX(IF(feat='lab_k',       valuenum, NULL)) AS lab_k,
    MAX(IF(feat='lab_hco3',    valuenum, NULL)) AS lab_hco3,
    MAX(IF(feat='lab_bun',     valuenum, NULL)) AS lab_bun,
    MAX(IF(feat='lab_cl',      valuenum, NULL)) AS lab_cl
  FROM labs_long WHERE rn = 1 GROUP BY subject_id
),

omr_bp AS (
  SELECT subject_id, sbp, dbp FROM (
    SELECT f.subject_id,
      SAFE_CAST(SPLIT(o.result_value,'/')[SAFE_OFFSET(0)] AS FLOAT64) AS sbp,
      SAFE_CAST(SPLIT(o.result_value,'/')[SAFE_OFFSET(1)] AS FLOAT64) AS dbp, o.chartdate
    FROM feat_adm f
    JOIN `physionet-data.mimiciv_3_1_hosp.omr` o ON o.subject_id = f.subject_id
    WHERE o.result_name='Blood Pressure' AND o.chartdate <= DATE(f.feat_admit))
  WHERE sbp BETWEEN 50 AND 300 AND dbp BETWEEN 20 AND 200
  QUALIFY ROW_NUMBER() OVER (PARTITION BY subject_id ORDER BY chartdate DESC) = 1
),
omr_bmi AS (
  SELECT subject_id, bmi FROM (
    SELECT f.subject_id, SAFE_CAST(o.result_value AS FLOAT64) AS bmi, o.chartdate
    FROM feat_adm f
    JOIN `physionet-data.mimiciv_3_1_hosp.omr` o ON o.subject_id = f.subject_id
    WHERE o.result_name='BMI (kg/m2)' AND o.chartdate <= DATE(f.feat_admit))
  WHERE bmi BETWEEN 10 AND 100
  QUALIFY ROW_NUMBER() OVER (PARTITION BY subject_id ORDER BY chartdate DESC) = 1
),
meds AS (
  SELECT f.subject_id,
    MAX(IF(REGEXP_CONTAINS(LOWER(p.drug), r'lisinopril|amlodipine|metoprolol|losartan|valsartan|hydrochlorothiazide|atenolol|carvedilol|enalapril|diltiazem|furosemide|chlorthalidone|olmesartan'),1,0)) AS med_aht,
    MAX(IF(REGEXP_CONTAINS(LOWER(p.drug), r'statin'),1,0)) AS med_statin,
    MAX(IF(REGEXP_CONTAINS(LOWER(p.drug), r'warfarin|heparin|apixaban|rivaroxaban|dabigatran|enoxaparin|edoxaban'),1,0)) AS med_ac,
    MAX(IF(REGEXP_CONTAINS(LOWER(p.drug), r'aspirin|clopidogrel|ticagrelor|prasugrel|dipyridamole'),1,0)) AS med_ap,
    MAX(IF(REGEXP_CONTAINS(LOWER(p.drug), r'metformin|insulin|glipizide|glyburide|sitagliptin|empagliflozin|glimepiride|pioglitazone|dapagliflozin'),1,0)) AS med_ad
  FROM feat_adm f
  JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` p
    ON p.subject_id = f.subject_id AND p.hadm_id = f.feat_hadm
  GROUP BY f.subject_id
)

SELECT
  f.subject_id, f.label,
  DATE(f.anchor_time) AS anchor_date, DATE(f.feat_admit) AS feature_date,
  DATE_DIFF(DATE(f.anchor_time), DATE(f.feat_admit), DAY) AS days_before_anchor,
  pt.anchor_age AS age, IF(pt.gender='M',1,0) AS sex_male,
  COALESCE(cm.cm_htn,0) AS cm_htn, COALESCE(cm.cm_dm,0) AS cm_dm,
  COALESCE(cm.cm_afib,0) AS cm_afib, COALESCE(cm.cm_ihd,0) AS cm_ihd,
  COALESCE(cm.cm_hld,0) AS cm_hld, COALESCE(cm.cm_ckd,0) AS cm_ckd,
  COALESCE(cm.cm_pvd,0) AS cm_pvd, COALESCE(cm.cm_smoke,0) AS cm_smoke,
  lb.lab_glucose, lb.lab_hba1c, lb.lab_creat, lb.lab_inr, lb.lab_hgb, lb.lab_plt,
  lb.lab_wbc, lb.lab_na, lb.lab_k, lb.lab_hco3, lb.lab_bun, lb.lab_cl,
  bp.sbp AS vit_sbp, bp.dbp AS vit_dbp, bm.bmi AS vit_bmi,
  COALESCE(md.med_aht,0) AS med_aht, COALESCE(md.med_statin,0) AS med_statin,
  COALESCE(md.med_ac,0) AS med_ac, COALESCE(md.med_ap,0) AS med_ap, COALESCE(md.med_ad,0) AS med_ad
FROM feat_adm f
JOIN `physionet-data.mimiciv_3_1_hosp.patients` pt ON pt.subject_id = f.subject_id
LEFT JOIN comorbid cm ON cm.subject_id = f.subject_id
LEFT JOIN labs     lb ON lb.subject_id = f.subject_id
LEFT JOIN omr_bp   bp ON bp.subject_id = f.subject_id
LEFT JOIN omr_bmi  bm ON bm.subject_id = f.subject_id
LEFT JOIN meds     md ON md.subject_id = f.subject_id
