-- ============================================================================
-- cohort_hf_eicu.sql — eICU-CRD external-validation cohort for the HF model.
-- One row per ICU stay (patientunitstayid). label=1 if HF coded for the stay
-- (ICD 428 / I50 or diagnosisstring 'heart failure'), else 0. Same 30 features
-- as the MIMIC concurrent model, harmonized from eICU tables. Concurrent design
-- (features from the index ICU stay) — eICU is single-stay so this transports the
-- MIMIC concurrent IDENTIFICATION model. Natural prevalence.
-- ============================================================================
WITH
dx AS (
  SELECT patientunitstayid, icd9code, diagnosisstring FROM `physionet-data.eicu_crd.diagnosis`
),
hf AS (
  SELECT DISTINCT patientunitstayid FROM dx
  WHERE REGEXP_CONTAINS(IFNULL(icd9code,''), r'428\.|I50') OR LOWER(diagnosisstring) LIKE '%heart failure%'
),
comorbid AS (
  SELECT patientunitstayid,
    MAX(IF(REGEXP_CONTAINS(IFNULL(icd9code,''), r'40[1-5]\.|I1[0-5]'),1,0)) AS cm_htn,
    MAX(IF(REGEXP_CONTAINS(IFNULL(icd9code,''), r'250\.|E0[89]|E1[013]'),1,0)) AS cm_dm,
    MAX(IF(REGEXP_CONTAINS(IFNULL(icd9code,''), r'427\.3|I48'),1,0)) AS cm_afib,
    MAX(IF(REGEXP_CONTAINS(IFNULL(icd9code,''), r'41[0-4]\.|I2[0-5]'),1,0)) AS cm_ihd,
    MAX(IF(REGEXP_CONTAINS(IFNULL(icd9code,''), r'272\.|E78'),1,0)) AS cm_hld,
    MAX(IF(REGEXP_CONTAINS(IFNULL(icd9code,''), r'585\.|N18'),1,0)) AS cm_ckd,
    MAX(IF(REGEXP_CONTAINS(IFNULL(icd9code,''), r'443\.9|I73'),1,0)) AS cm_pvd,
    MAX(IF(REGEXP_CONTAINS(IFNULL(icd9code,''), r'305\.1|V15\.82|F17|Z72\.0'),1,0)) AS cm_smoke
  FROM dx GROUP BY patientunitstayid
),
lab_map AS (
  SELECT patientunitstayid,
    CASE labname
      WHEN 'creatinine' THEN 'lab_creat' WHEN 'glucose' THEN 'lab_glucose'
      WHEN 'Hgb' THEN 'lab_hgb' WHEN 'platelets x 1000' THEN 'lab_plt'
      WHEN 'WBC x 1000' THEN 'lab_wbc' WHEN 'sodium' THEN 'lab_na'
      WHEN 'potassium' THEN 'lab_k' WHEN 'bicarbonate' THEN 'lab_hco3'
      WHEN 'BUN' THEN 'lab_bun' WHEN 'chloride' THEN 'lab_cl'
      WHEN 'PT - INR' THEN 'lab_inr' WHEN 'Hgb A1C' THEN 'lab_hba1c'
    END AS feat,
    labresult, labresultoffset
  FROM `physionet-data.eicu_crd.lab`
),
labs AS (
  SELECT patientunitstayid,
    MAX(IF(feat='lab_glucose',v,NULL)) lab_glucose, MAX(IF(feat='lab_hba1c',v,NULL)) lab_hba1c,
    MAX(IF(feat='lab_creat',v,NULL)) lab_creat, MAX(IF(feat='lab_inr',v,NULL)) lab_inr,
    MAX(IF(feat='lab_hgb',v,NULL)) lab_hgb, MAX(IF(feat='lab_plt',v,NULL)) lab_plt,
    MAX(IF(feat='lab_wbc',v,NULL)) lab_wbc, MAX(IF(feat='lab_na',v,NULL)) lab_na,
    MAX(IF(feat='lab_k',v,NULL)) lab_k, MAX(IF(feat='lab_hco3',v,NULL)) lab_hco3,
    MAX(IF(feat='lab_bun',v,NULL)) lab_bun, MAX(IF(feat='lab_cl',v,NULL)) lab_cl
  FROM (
    SELECT patientunitstayid, feat, labresult AS v,
           ROW_NUMBER() OVER (PARTITION BY patientunitstayid, feat ORDER BY labresultoffset) rn
    FROM lab_map WHERE feat IS NOT NULL AND labresult IS NOT NULL
  ) WHERE rn=1 GROUP BY patientunitstayid
),
bp AS (
  SELECT patientunitstayid,
    APPROX_QUANTILES(noninvasivesystolic, 2)[OFFSET(1)] AS vit_sbp,
    APPROX_QUANTILES(noninvasivediastolic, 2)[OFFSET(1)] AS vit_dbp
  FROM `physionet-data.eicu_crd.vitalaperiodic`
  WHERE noninvasivesystolic BETWEEN 50 AND 300 AND noninvasivediastolic BETWEEN 20 AND 200
  GROUP BY patientunitstayid
),
meds AS (
  SELECT patientunitstayid,
    MAX(IF(REGEXP_CONTAINS(LOWER(drugname), r'lisinopril|amlodipine|metoprolol|losartan|valsartan|hydrochlorothiazide|atenolol|carvedilol|enalapril|diltiazem|furosemide|chlorthalidone|olmesartan'),1,0)) med_aht,
    MAX(IF(REGEXP_CONTAINS(LOWER(drugname), r'statin'),1,0)) med_statin,
    MAX(IF(REGEXP_CONTAINS(LOWER(drugname), r'warfarin|heparin|apixaban|rivaroxaban|dabigatran|enoxaparin|edoxaban'),1,0)) med_ac,
    MAX(IF(REGEXP_CONTAINS(LOWER(drugname), r'aspirin|clopidogrel|ticagrelor|prasugrel|dipyridamole'),1,0)) med_ap,
    MAX(IF(REGEXP_CONTAINS(LOWER(drugname), r'metformin|insulin|glipizide|glyburide|sitagliptin|empagliflozin|glimepiride|pioglitazone|dapagliflozin'),1,0)) med_ad
  FROM `physionet-data.eicu_crd.medication` GROUP BY patientunitstayid
)
SELECT
  p.patientunitstayid AS subject_id,
  IF(p.patientunitstayid IN (SELECT patientunitstayid FROM hf), 1, 0) AS label,
  CASE WHEN p.age = '> 89' THEN 90 ELSE SAFE_CAST(p.age AS INT64) END AS age,
  IF(p.gender='Male',1,0) AS sex_male,
  COALESCE(c.cm_htn,0) cm_htn, COALESCE(c.cm_dm,0) cm_dm, COALESCE(c.cm_afib,0) cm_afib,
  COALESCE(c.cm_ihd,0) cm_ihd, COALESCE(c.cm_hld,0) cm_hld, COALESCE(c.cm_ckd,0) cm_ckd,
  COALESCE(c.cm_pvd,0) cm_pvd, COALESCE(c.cm_smoke,0) cm_smoke,
  l.lab_glucose, l.lab_hba1c, l.lab_creat, l.lab_inr, l.lab_hgb, l.lab_plt,
  l.lab_wbc, l.lab_na, l.lab_k, l.lab_hco3, l.lab_bun, l.lab_cl,
  bp.vit_sbp, bp.vit_dbp,
  CASE WHEN p.admissionheight BETWEEN 100 AND 250 AND p.admissionweight BETWEEN 20 AND 400
       THEN ROUND(p.admissionweight / POW(p.admissionheight/100, 2), 1) END AS vit_bmi,
  COALESCE(m.med_aht,0) med_aht, COALESCE(m.med_statin,0) med_statin, COALESCE(m.med_ac,0) med_ac,
  COALESCE(m.med_ap,0) med_ap, COALESCE(m.med_ad,0) med_ad
FROM `physionet-data.eicu_crd.patient` p
LEFT JOIN comorbid c ON c.patientunitstayid = p.patientunitstayid
LEFT JOIN labs     l ON l.patientunitstayid = p.patientunitstayid
LEFT JOIN bp          ON bp.patientunitstayid = p.patientunitstayid
LEFT JOIN meds     m ON m.patientunitstayid = p.patientunitstayid
WHERE SAFE_CAST(p.age AS INT64) IS NOT NULL OR p.age = '> 89'
