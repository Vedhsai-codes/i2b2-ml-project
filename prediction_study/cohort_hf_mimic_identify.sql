-- ============================================================================
-- cohort_hf_mimic_identify.sql — MIMIC-IV HF identification cohort, defined
-- IDENTICALLY to the eICU external cohort for a fair transport test:
--   one row per hospital admission, label=1 if HF (I50/428) coded for that
--   admission, all-comers, natural prevalence, features from the admission.
-- (Contrast with cohort_hf_temporal.sql, which is the incident-HF design for the
--  leakage-decay ablation; this one is the aligned identification cohort.)
-- ============================================================================
WITH
adm AS (
  SELECT subject_id, hadm_id, admittime, dischtime
  FROM `physionet-data.mimiciv_3_1_hosp.admissions`
),
hf_adm AS (
  SELECT DISTINCT subject_id, hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  WHERE (icd_version=10 AND icd_code LIKE 'I50%') OR (icd_version=9 AND icd_code LIKE '428%')
),
cohort AS (
  SELECT a.subject_id, a.hadm_id, a.admittime, a.dischtime,
         IF(h.hadm_id IS NOT NULL, 1, 0) AS label
  FROM adm a LEFT JOIN hf_adm h ON h.hadm_id = a.hadm_id
),
comorbid AS (
  SELECT co.hadm_id,
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
  FROM cohort co
  JOIN adm a2 ON a2.subject_id = co.subject_id AND a2.admittime <= co.admittime
  JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d ON d.subject_id = a2.subject_id AND d.hadm_id = a2.hadm_id
  GROUP BY co.hadm_id
),
lab_items AS (
  SELECT itemid, CASE
      WHEN label='Glucose' AND fluid='Blood' THEN 'lab_glucose'
      WHEN label LIKE '%Hemoglobin A1c%' THEN 'lab_hba1c'
      WHEN label='Creatinine' AND fluid='Blood' THEN 'lab_creat'
      WHEN label='INR(PT)' THEN 'lab_inr'
      WHEN label='Hemoglobin' AND fluid='Blood' THEN 'lab_hgb'
      WHEN label='Platelet Count' THEN 'lab_plt'
      WHEN label='White Blood Cells' THEN 'lab_wbc'
      WHEN label='Sodium' AND fluid='Blood' THEN 'lab_na'
      WHEN label='Potassium' AND fluid='Blood' THEN 'lab_k'
      WHEN label='Bicarbonate' AND fluid='Blood' THEN 'lab_hco3'
      WHEN label='Urea Nitrogen' AND fluid='Blood' THEN 'lab_bun'
      WHEN label='Chloride' AND fluid='Blood' THEN 'lab_cl' END AS feat
  FROM `physionet-data.mimiciv_3_1_hosp.d_labitems`
),
labs AS (
  SELECT hadm_id,
    MAX(IF(feat='lab_glucose',v,NULL)) lab_glucose, MAX(IF(feat='lab_hba1c',v,NULL)) lab_hba1c,
    MAX(IF(feat='lab_creat',v,NULL)) lab_creat, MAX(IF(feat='lab_inr',v,NULL)) lab_inr,
    MAX(IF(feat='lab_hgb',v,NULL)) lab_hgb, MAX(IF(feat='lab_plt',v,NULL)) lab_plt,
    MAX(IF(feat='lab_wbc',v,NULL)) lab_wbc, MAX(IF(feat='lab_na',v,NULL)) lab_na,
    MAX(IF(feat='lab_k',v,NULL)) lab_k, MAX(IF(feat='lab_hco3',v,NULL)) lab_hco3,
    MAX(IF(feat='lab_bun',v,NULL)) lab_bun, MAX(IF(feat='lab_cl',v,NULL)) lab_cl
  FROM (
    SELECT co.hadm_id, li.feat, le.valuenum AS v,
           ROW_NUMBER() OVER (PARTITION BY co.hadm_id, li.feat ORDER BY le.charttime) rn
    FROM cohort co
    JOIN `physionet-data.mimiciv_3_1_hosp.labevents` le ON le.hadm_id = co.hadm_id
    JOIN lab_items li ON li.itemid = le.itemid
    WHERE li.feat IS NOT NULL AND le.valuenum IS NOT NULL
  ) WHERE rn=1 GROUP BY hadm_id
),
omr_bp AS (
  SELECT hadm_id, sbp, dbp FROM (
    SELECT co.hadm_id, SAFE_CAST(SPLIT(o.result_value,'/')[SAFE_OFFSET(0)] AS FLOAT64) sbp,
           SAFE_CAST(SPLIT(o.result_value,'/')[SAFE_OFFSET(1)] AS FLOAT64) dbp, o.chartdate
    FROM cohort co JOIN `physionet-data.mimiciv_3_1_hosp.omr` o ON o.subject_id=co.subject_id
    WHERE o.result_name='Blood Pressure' AND o.chartdate <= DATE(co.admittime))
  WHERE sbp BETWEEN 50 AND 300 AND dbp BETWEEN 20 AND 200
  QUALIFY ROW_NUMBER() OVER (PARTITION BY hadm_id ORDER BY chartdate DESC)=1
),
omr_bmi AS (
  SELECT hadm_id, bmi FROM (
    SELECT co.hadm_id, SAFE_CAST(o.result_value AS FLOAT64) bmi, o.chartdate
    FROM cohort co JOIN `physionet-data.mimiciv_3_1_hosp.omr` o ON o.subject_id=co.subject_id
    WHERE o.result_name='BMI (kg/m2)' AND o.chartdate <= DATE(co.admittime))
  WHERE bmi BETWEEN 10 AND 100
  QUALIFY ROW_NUMBER() OVER (PARTITION BY hadm_id ORDER BY chartdate DESC)=1
),
meds AS (
  SELECT co.hadm_id,
    MAX(IF(REGEXP_CONTAINS(LOWER(p.drug), r'lisinopril|amlodipine|metoprolol|losartan|valsartan|hydrochlorothiazide|atenolol|carvedilol|enalapril|diltiazem|furosemide|chlorthalidone|olmesartan'),1,0)) med_aht,
    MAX(IF(REGEXP_CONTAINS(LOWER(p.drug), r'statin'),1,0)) med_statin,
    MAX(IF(REGEXP_CONTAINS(LOWER(p.drug), r'warfarin|heparin|apixaban|rivaroxaban|dabigatran|enoxaparin|edoxaban'),1,0)) med_ac,
    MAX(IF(REGEXP_CONTAINS(LOWER(p.drug), r'aspirin|clopidogrel|ticagrelor|prasugrel|dipyridamole'),1,0)) med_ap,
    MAX(IF(REGEXP_CONTAINS(LOWER(p.drug), r'metformin|insulin|glipizide|glyburide|sitagliptin|empagliflozin|glimepiride|pioglitazone|dapagliflozin'),1,0)) med_ad
  FROM cohort co JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` p ON p.hadm_id = co.hadm_id
  GROUP BY co.hadm_id
)
SELECT
  co.hadm_id AS subject_id, co.label,
  pt.anchor_age AS age, IF(pt.gender='M',1,0) AS sex_male,
  COALESCE(cm.cm_htn,0) cm_htn, COALESCE(cm.cm_dm,0) cm_dm, COALESCE(cm.cm_afib,0) cm_afib,
  COALESCE(cm.cm_ihd,0) cm_ihd, COALESCE(cm.cm_hld,0) cm_hld, COALESCE(cm.cm_ckd,0) cm_ckd,
  COALESCE(cm.cm_pvd,0) cm_pvd, COALESCE(cm.cm_smoke,0) cm_smoke,
  l.lab_glucose, l.lab_hba1c, l.lab_creat, l.lab_inr, l.lab_hgb, l.lab_plt,
  l.lab_wbc, l.lab_na, l.lab_k, l.lab_hco3, l.lab_bun, l.lab_cl,
  bp.sbp AS vit_sbp, bp.dbp AS vit_dbp, bm.bmi AS vit_bmi,
  COALESCE(md.med_aht,0) med_aht, COALESCE(md.med_statin,0) med_statin, COALESCE(md.med_ac,0) med_ac,
  COALESCE(md.med_ap,0) med_ap, COALESCE(md.med_ad,0) med_ad
FROM cohort co
JOIN `physionet-data.mimiciv_3_1_hosp.patients` pt ON pt.subject_id = co.subject_id
LEFT JOIN comorbid cm ON cm.hadm_id = co.hadm_id
LEFT JOIN labs     l  ON l.hadm_id = co.hadm_id
LEFT JOIN omr_bp   bp ON bp.hadm_id = co.hadm_id
LEFT JOIN omr_bmi  bm ON bm.hadm_id = co.hadm_id
LEFT JOIN meds     md ON md.hadm_id = co.hadm_id
