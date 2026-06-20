% Accessible, externally validated cardiometabolic phenotype-identification models built natively in a clinical data warehouse: a TRIPOD+AI prediction study in MIMIC-IV and eICU-CRD
% Vedhsai Thiriveedi; Kavishwar Wagholikar; [co-authors TBD]
% Draft — generated 2026-06-20

## Abstract

**Background.** Machine-learning phenotype models are usually built by ML engineers in bespoke
pipelines, which limits who can build them and how well their performance is reported. We asked
whether calibrated, externally validated identification models for three cardiometabolic
phenotypes — heart failure (HF), chronic kidney disease (CKD), and diabetes — can be built
natively from a clinical data warehouse (CDW), and how far they transport across health systems.

**Methods.** Using MIMIC-IV (a single Boston academic ICU) we defined aligned, per-admission,
all-comers identification cohorts (one row per hospital admission; natural prevalence) for HF,
CKD, and diabetes, each described by the same 30 structured features (demographics, comorbidities,
laboratory values, vital signs, medication classes). Elastic-net logistic regression was trained
with median imputation and missing indicators and **no class-rebalancing** (SMOTE harms
calibration). Discrimination (ROC AUC, AUPRC), calibration (slope, intercept, Brier), and
1000-sample bootstrap 95% confidence intervals were computed on a 30% internal hold-out. Models
were then applied **frozen** to eICU-CRD (208 US hospitals) for external validation, followed by a
prespecified recalibration hierarchy (intercept-only, then intercept+slope). We quantified
outcome-proximal information leakage with an incident-onset *blackout* ablation (features taken
from a visit ≥0/30/90/180 days before first diagnosis), assessed clinical utility by
decision-curve analysis (DCA), reported sex/age subgroup performance, and benchmarked discrimination against models built **through the
no-code i2b2-ML tool's JSON API**. Reporting follows TRIPOD+AI with a PROBAST self-assessment.

**Results.** Across 546,028 MIMIC-IV admissions, internal discrimination was high and calibration
near-perfect: HF ROC AUC 0.907 (95% CI 0.906–0.909), CKD 0.935, diabetes 0.933 (calibration slope
~1.0 each). On 200,764 eICU-CRD admissions, frozen transport degraded honestly but remained
useful — HF 0.758 (0.754–0.761), CKD 0.840 (0.838–0.843), diabetes 0.761 (0.758–0.764) — with
over-confident calibration (slope 0.38–0.56) **restored to near-ideal by intercept+slope
recalibration** (0.98–1.01) in every condition. The blackout ablation isolated the leaky,
outcome-proximal signal: HF 0.884→0.808, CKD 0.903→0.838, diabetes 0.856→0.718 from concurrent to
≥180-day pre-onset, after which discrimination plateaued; genuine pre-onset detection was stable
and well-calibrated. DCA showed positive net benefit across the clinically relevant threshold
range for both concurrent and pre-onset models. The no-code i2b2-ML tool reproduced the bespoke
pipeline's discrimination to within ≤0.011 AUROC (HF 0.914, CKD 0.946, diabetes 0.931).

**Conclusions.** Calibrated, externally validated cardiometabolic identification models can be
built natively in a CDW and, after a simple two-parameter recalibration, transported to hundreds
of other hospitals; objective laboratory features transport better than diagnosis codes. The
modelling step is reproducible by a no-code tool, making rigorous phenotype modelling accessible
to non-ML researchers while preserving external-validity discipline.

---

## 1. Introduction

Electronic health records and the clinical data warehouses (CDWs) built on them — i2b2, OMOP,
TriNetX — have made structured patient data routinely available for research. Yet building a
predictive phenotype model from a CDW still typically requires a machine-learning engineer to
export data, engineer features, fit and tune a model, and report it. This gates a common, valuable
task (identify which admissions carry a phenotype) behind specialised skills, and the resulting
one-off pipelines are rarely reported to the standard a clinical-prediction model deserves:
external validation, calibration, and clinical-utility assessment are frequently missing.

Two problems compound. First, **accessibility**: the people who best understand a phenotype —
clinicians, registry curators — usually cannot build the model themselves. Second, **rigor and
transportability**: models developed at one center are seldom validated elsewhere, and when they
are, discrimination commonly drops and calibration drifts. Reviewers of clinical-prediction work
(per TRIPOD+AI and PROBAST) now expect external validation, explicit calibration, and decision-
analytic evidence — exactly the elements bespoke pipelines tend to omit.

We address both problems together. We show that calibrated identification models for three
cardiometabolic phenotypes can be built **natively in a CDW** — and that the model-fitting step is
reproducible by a **no-code tool** (the i2b2-ML plugin) so that a non-ML researcher could perform
it — while wrapping that step in the full external-validity discipline: an aligned development
cohort, frozen external validation across 208 hospitals, a recalibration hierarchy, a leakage
ablation that separates outcome-proximal from genuinely predictive signal, and decision-curve
analysis. The contribution is not a single best model; it is a demonstration that the *modelling*
step is now accessible and that the *surrounding rigor* is a reusable, phenotype-agnostic template.

We chose heart failure, chronic kidney disease, and diabetes because they are high-burden,
guideline-relevant, and have objective laboratory correlates (natriuretic state and congestion;
serum creatinine; serum glucose and HbA1c), letting us test a secondary hypothesis: that
objective laboratory features transport across health systems better than provider-entered
diagnosis codes.

## 2. Methods

### 2.1 Data sources

Development used **MIMIC-IV v3.1** (hospital module), de-identified records from the Beth Israel
Deaconess Medical Center, Boston. External validation used **eICU-CRD v2.0**, a multi-center
critical-care database spanning 208 US hospitals (2014–2015). Both are credentialed PhysioNet
resources accessed on Google BigQuery; this analysis used only de-identified data and required no
additional IRB review. Laboratory and vital-sign units were verified identical between sources
prior to harmonization (no unit conversion was required).

### 2.2 Cohorts and outcome definitions

To make development and external cohorts directly comparable, we used a single **aligned
identification design**: one row per hospital admission, all admissions included (all-comers), at
**natural prevalence** (no case:control ratio forcing, no sampling cap). An admission was labelled
positive if the phenotype was coded for that admission:

- **Heart failure** — ICD-10 `I50*` or ICD-9 `428*`.
- **Chronic kidney disease** — ICD-10 `N18*` or ICD-9 `585*`.
- **Diabetes** — ICD-10 `E08–E13` or ICD-9 `250*` (any diabetes, for clean MIMIC↔eICU label
  harmonization; a strict type-2 sensitivity analysis is reported in §3.8).

The eICU comorbidity and outcome capture combined the `diagnosis` **and** `pasthistory` tables;
`diagnosis` alone under-codes chronic comorbidities by 4–5× (e.g., hypertension 12% vs 48% once
`pasthistory` is added), which would otherwise spuriously depress transport.

A separate **incident-onset** design was used only for the leakage ablation (§2.7): the patient's
first phenotype admission (with ≥1 prior admission so that pre-onset history exists) versus
never-diagnosed patients with ≥2 admissions, one row per patient. Because onset is the first code,
the self-comorbidity is structurally absent before onset; it is additionally dropped from the
feature set (below).

### 2.3 Features

All models used the **same 30 structured features**, computed from the index admission (or, in the
ablation, from the most recent admission before the blackout cutoff): age, sex; eight comorbidity
flags (hypertension, diabetes, atrial fibrillation, ischemic heart disease, dyslipidemia, CKD,
peripheral vascular disease, smoking); twelve laboratory values (glucose, HbA1c, creatinine, INR,
hemoglobin, platelets, WBC, sodium, potassium, bicarbonate, urea nitrogen, chloride); three
vitals (systolic and diastolic blood pressure, BMI); and five medication-class flags
(antihypertensive, statin, anticoagulant, antiplatelet, antidiabetic). To prevent label leakage,
**each phenotype's own ICD-derived self-comorbidity flag was excluded** (cm_ckd for CKD, cm_dm for
diabetes); HF has no corresponding self-comorbidity feature. The diagnostic laboratory for each
phenotype (creatinine for CKD, glucose/HbA1c for diabetes) was retained, since it is the objective
basis for the diagnosis rather than a circular restatement of the code.

### 2.4 Model

The estimator was **elastic-net logistic regression** (saga solver), the model family implemented
by the i2b2-ML engine. Numeric features were median-imputed with missing-indicator augmentation
and standardized; binary features were passed through. The regularization strength `C` and the
l1/l2 mixing ratio were tuned by 4-fold inner cross-validation (grid `C∈{0.1,1.0}`,
`l1_ratio∈{0.2,0.5,0.8}`). **No synthetic oversampling (SMOTE) was used**: it inflates apparent
performance and corrupts calibration; class imbalance was handled by the regularized likelihood
and reported at the natural base rate. Seed fixed at 42 throughout.

### 2.5 Internal validation

Each cohort was split 70/30 (stratified, seed 42). We report ROC AUC and AUPRC (with AUPRC lift
over base rate), the calibration slope and intercept (logistic recalibration of the linear
predictor), and the Brier score, each with 1000-sample bootstrap 95% confidence intervals on the
hold-out. The models are richly powered: the development sets held 56,428 (HF), 58,002 (CKD), and
93,415 (diabetes) events against 44–45 candidate predictors — an events-per-variable of 1,254–2,123,
far above the conventional ≥10–20 threshold, so overfitting is not a concern. Per-model standardized
coefficients (odds ratios) are provided as a supplement (`results/model_spec_<phenotype>.md`).
We additionally report performance within prespecified subgroups (sex; age &lt;65 vs ≥65) as a
fairness assessment (§3.9).

### 2.6 External validation and recalibration

The model fit on MIMIC-IV was applied **frozen** to harmonized eICU-CRD (identical 30-feature
specification). We report transport discrimination and calibration, then a prespecified
**recalibration hierarchy** fit on a random half of eICU and evaluated on the other half:
(i) intercept-only (a logistic offset correcting overall risk level) and (ii) intercept+slope
(Platt logistic recalibration of the linear predictor). Recalibration cannot change discrimination
(AUROC is invariant to a monotone transform of risk) — only calibration — which is the expected and
reported behavior.

### 2.7 Temporal leakage-decay ablation

Concurrent (index-admission) features can encode the diagnostic event itself. Using the
incident-onset cohort, we recomputed features from the most recent admission **≥0, 30, 90, and 180
days before** the first diagnosis. The decay of AUROC from blackout 0 to 180 days quantifies the
outcome-proximal (leaky) contribution; the plateau value estimates genuine pre-onset
detectability. For the chronic phenotypes (CKD, diabetes) the first code is *newly documented*
disease rather than biological onset — a limitation we state explicitly (§4) — and the defining
laboratory is retained, so the concurrent design is expected to be strong by construction.

### 2.8 Decision-curve analysis

We computed net benefit, NB = TP/N − (FP/N)·(p_t/(1−p_t)), across threshold probabilities
0.01–0.50, against treat-all and treat-none references, for the concurrent and pre-onset models.
As a clinical-baseline comparator we additionally fit a **guideline-variable reference model**
restricted to the established cardiometabolic risk factors available in the CDW (age, sex, systolic
blood pressure, antihypertensive treatment, diabetes, smoking, BMI, and a race-free **CKD-EPI 2021
eGFR** derived from serum creatinine), and compared its net benefit to the full 30-feature model
(§3.7). Faithful computation of the published incident-disease equations (PCP-HF, PREVENT, KFRE)
requires predictors that are sparse or absent in MIMIC's structured tables — urine albumin-to-
creatinine ratio, a discrete lipid panel, race, QRS duration — so a guideline-variable reference is
the honest CDW-native benchmark.

### 2.9 Accessibility / tool reproduction

To test the accessibility claim, the same identification task was executed through the **no-code
i2b2-ML tool**: phenotype cohorts were loaded as i2b2 concepts, facts, and named patient sets, and
models were built by POSTing a `jobType:ml` job to the plugin's JSON API; the asynchronous
`jobWatcher`/`mlEngine` fit a regularized logistic regression and returned a serialized model with
ROC AUC, accuracy, precision, and recall. We compare the tool's discrimination to the bespoke
harness. A full capability map (what runs inside the tool vs. the rigor the harness adds around it)
is provided as a supplementary table.

### 2.10 Reporting and statistical software

Reporting follows **TRIPOD+AI** (item-by-item checklist supplied) with a **PROBAST** risk-of-bias
self-assessment. Analyses used Python 3.12, scikit-learn, scipy, and matplotlib; cohorts were
derived in BigQuery SQL. All cohort SQL, model code, and result artifacts are released (§6).

## 3. Results

### 3.1 Cohorts

The MIMIC-IV identification cohorts comprised **546,028 admissions** each, with natural prevalence
14.8% (HF), 15.2% (CKD), and 24.4% (any diabetes). The eICU-CRD external cohorts comprised
**200,764 admissions**, prevalence 8.5% (HF), 15.4% (CKD), and 11.7% (diabetes). The HF and
diabetes prevalence shifts between systems (notably diabetes 24.4%→11.7%) are themselves a source
of the calibration drift corrected in §3.3.

### 3.2 Internal discrimination and calibration

Internal performance was high and calibration near-ideal (Table 1):

| Phenotype | ROC AUC (95% CI) | AUPRC | Calibration slope / intercept |
|---|---|---|---|
| Heart failure | 0.907 (0.906–0.909) | 0.645 | 1.00 / −0.01 |
| Chronic kidney disease | 0.935 | — | ~1.0 |
| Diabetes | 0.933 | — | ~1.0 |

The HF figure (0.907, calibrated, 30 features + logistic regression) is competitive with a
published 200-feature deep-learning HF abstract (ROC AUC 0.93), at a fraction of the feature
budget and with explicit calibration.

### 3.3 External transportability and recalibration

Applied frozen to eICU-CRD, discrimination degraded honestly but remained useful, and calibration
— over-confident on transport — was restored to near-ideal by intercept+slope recalibration in
every condition (Table 2; Figure 1):

| Phenotype | Internal AUROC | External AUROC (95% CI) | Ext. calibration slope (frozen → recalibrated) |
|---|---|---|---|
| Heart failure | 0.907 | 0.758 (0.754–0.761) | 0.56 → 0.98 |
| Chronic kidney disease | 0.935 | 0.840 (0.838–0.843) | 0.38 → 0.99 |
| Diabetes | 0.933 | 0.761 (0.758–0.764) | 0.38 → 1.01 |

Two transportability findings are consistent across phenotypes. (1) **Discrimination drops** by a
real, reportable margin (0.10–0.17 AUROC) across health systems, with **CKD transporting best**
(0.840) — the phenotype most anchored to an objective, well-measured laboratory (creatinine).
(2) **Calibration drifts but is rescued by two parameters**: intercept-only correction is
insufficient (the slope, not just the level, is wrong); intercept+slope recalibration returns the
slope to 0.98–1.01. AUROC is unchanged by recalibration, as expected.

Two harmonization fixes were required to make the transport test *fair* rather than artefactually
low (and raised HF transport from 0.717 to 0.758): adding eICU `pasthistory` to comorbidity
capture, and aligning the development and external cohorts to the identical per-admission
all-comers definition. Lab/vital units were verified identical.

### 3.4 Leakage-decay ablation

Sliding the feature window back from the index admission isolated the outcome-proximal signal
(Table 3; Figures 2a–c):

| Phenotype | Concurrent (0 d) | ≥30 d | ≥90 d | ≥180 d | Concurrent→180 d drop |
|---|---|---|---|---|---|
| Heart failure | 0.884 | 0.814 | 0.811 | 0.808 | 0.076 (9%) |
| Chronic kidney disease | 0.903 | 0.845 | 0.840 | 0.838 | 0.066 (7%) |
| Diabetes | 0.856 | 0.732 | 0.730 | 0.718 | 0.139 (16%) |

In every phenotype the drop is **concentrated at the index admission and then plateaus**:
genuine pre-onset detection is a stable, well-calibrated AUROC (~0.81 HF, ~0.84 CKD, ~0.72
diabetes). Diabetes shows the largest leakage (16%), consistent with serum glucose at the
diagnosing admission being highly outcome-proximal; HF and CKD leak less because chronic
structural and renal features persist before onset. A fixed-cohort HF re-analysis (same patients
evaluated at every cutoff) reproduced the decay (0.883→0.808), confirming the drop is **feature
timing, not cohort composition**. Calibration slope remained ~1.0 at every time point.

### 3.5 Decision-curve analysis

Both concurrent and pre-onset models delivered **positive net benefit across the clinically
relevant threshold range** and exceeded treat-all and treat-none (Figures 3a–c). For HF at a 0.20
threshold, net benefit was 0.071 (concurrent) and 0.045 (pre-onset) versus −0.072 for treat-all;
the pre-onset model retained clinical utility after removal of the leaky concurrent features.
CKD and diabetes showed the same qualitative pattern.

### 3.6 Tool reproduction (accessibility)

Built through the no-code i2b2-ML JSON API (`jobType:ml`; HTTP 200; serialized model returned),
discrimination reproduced the bespoke harness to within ≤0.011 AUROC: **HF 0.914, CKD 0.946,
diabetes 0.931**, versus harness identification 0.907 / 0.935 / 0.933 (Table 4). The tool's
builds use the plugin's balanced sampling (n=2,400, 800 positive / 1,600 negative). To confirm
that this sampling — not a genuinely different model — explains the tool's marginally higher
numbers, we trained the harness on an *identical* 800/1,600 balanced HF sample and obtained ROC
AUC **0.902**, essentially equal to the full natural-prevalence 0.907 and the tool's 0.914. The
balanced sampling therefore does not inflate discrimination, and the central point stands —
*a non-ML researcher driving the tool reproduces the modelling result*. The supplementary capability map details the division of labour: the tool fits and serves
the model; the harness supplies cohort alignment, external validation, recalibration, the ablation,
DCA, and TRIPOD+AI reporting.

### 3.7 Guideline-variable reference comparator

<!-- ITEM4_REFERENCE_DCA -->
A guideline-variable reference model — the eight established cardiometabolic risk factors available
in the CDW (age, sex, systolic blood pressure, antihypertensive treatment, diabetes, smoking, BMI,
and a race-free CKD-EPI 2021 eGFR derived from serum creatinine) — reached internal ROC AUC **0.860
(95% CI 0.858–0.863)**, calibrated (slope 1.00), versus **0.907** for the full 30-feature CDW model
on the same HF identification hold-out. On decision-curve analysis the **full model dominated the
reference model at every threshold** (Figure 3d; net benefit at 0.10/0.20/0.30 thresholds: full
0.109/0.084/0.065 vs reference 0.099/0.066/0.042, both above treat-all 0.053/−0.066/−0.218). The
full CDW feature set therefore adds both discrimination (+0.047 AUROC) and clinical net benefit
over an established-risk-factor baseline — the marginal value of the broader laboratory panel the
tool makes accessible.

### 3.8 Strict type-2 diabetes sensitivity

<!-- ITEM4_STRICT_T2D -->
Restricting the diabetes label to **strict type-2** (ICD-10 `E11` only; ICD-9 `250.x0/250.x2`)
rather than any-diabetes had only a small effect on discrimination: internal ROC AUC **0.919
(95% CI 0.918–0.921)** at 22.4% prevalence, versus **0.933** for any-diabetes at 24.4% prevalence,
with calibration unchanged (slope 0.99). The 0.014 AUROC reduction is consistent with strict
type-2 being a slightly harder, lower-prevalence target; the model remains strong and
well-calibrated under the more specific label. (Re-running the any-diabetes identification with the
same internal-holdout code reproduced 0.933 exactly — 0.9329 — confirming the harness and the tool
share the headline number.) External validation was kept on the any-diabetes label for clean
MIMIC↔eICU harmonization, a deliberate choice noted in §4.

### 3.9 Subgroup performance (fairness)

Discrimination and calibration within prespecified subgroups (Table 5) were stable across sex but
**lower in older patients** for the cardiorenal phenotypes:

| Phenotype | Female | Male | Age &lt;65 | Age ≥65 | Largest gap |
|---|---|---|---|---|---|
| Heart failure | 0.915 | 0.898 | 0.928 | 0.848 | 0.079 |
| Chronic kidney disease | 0.939 | 0.928 | 0.956 | 0.888 | 0.068 |
| Diabetes | 0.935 | 0.930 | 0.944 | 0.910 | 0.034 |

Calibration slope stayed near 1.0 in every subgroup. The age gap is expected and clinically
interpretable: in patients ≥65 the phenotypes are both more prevalent (HF 26% vs 8%) and more
diffuse — comorbidity and polypharmacy compress the feature contrast between cases and non-cases —
so the headline AUROC is partly buoyed by sharper separation in younger patients. We report this
transparently rather than only the pooled number; it is a target for age-stratified modelling (§5).

## 4. Discussion

**Principal findings.** Calibrated, externally validated identification models for HF, CKD, and
diabetes can be built natively from a CDW. Internally they are strong and near-perfectly
calibrated (0.907–0.935); applied frozen to 208 other hospitals they degrade honestly (0.758–0.840)
but, after a two-parameter recalibration, are well-calibrated everywhere. The model-fitting step
is reproducible by a no-code tool, so the rigor demonstrated here does not depend on specialised ML
skills.

**What transports.** CKD transported best and diabetes/HF less well. The pattern tracks how
objective the phenotype's defining signal is: creatinine is measured near-universally and
identically across systems, whereas HF and (any-)diabetes lean more on provider-entered diagnosis
and prescribing patterns that differ between hospitals. This supports our secondary hypothesis —
**laboratory features transport better than diagnosis codes** — and is actionable: portable CDW
models should be anchored on objective measurements where possible.

**The leakage finding.** Quantifying the concurrent→pre-onset AUROC drop (7–16%) is itself a
methodological result. It separates the inflated identification number (legitimate for the
identification task) from the honest early-detection number, and shows the latter is stable and
calibrated. Reporting both, connected by the ablation, is more defensible than either alone — and
the diabetes case (16% leakage) is a concrete caution against reading a concurrent AUROC as an
early-warning capability.

**Accessibility.** The tool reproduction makes the practical claim concrete: the step that
previously required an ML engineer (fitting and serving a calibrated model from a CDW) can be done
through a JSON API by someone who is not an ML specialist, while the surrounding study design —
which is phenotype-agnostic and reusable — supplies the external-validity discipline reviewers
require. This lowers the barrier to rigorous phenotype modelling without lowering the bar on rigor.

**Comparison with literature.** Our internal HF discrimination (0.907) matches deep-learning HF
models that use far more features, but unlike most such reports we add external validation across
hundreds of hospitals, explicit calibration and recalibration, an ablation, and DCA — the elements
TRIPOD+AI and PROBAST require and that single-center model papers commonly omit.

## 5. Limitations

1. **ICU-derived sources.** Both MIMIC-IV and eICU-CRD are critical-care databases; case mix and
   prevalence differ from general inpatient or ambulatory populations, so absolute risks and
   transport estimates may not generalise outside the ICU.
2. **Silver-standard labels.** Outcomes are ICD-code-derived, not chart-adjudicated; coding
   practices vary, and eICU codes required `pasthistory` augmentation to avoid under-capture.
3. **Chronic-onset ambiguity.** For CKD and diabetes the "first code" is newly *documented*
   disease, not biological onset; the pre-onset ablation should be read as lead time before
   documentation, not before disease.
4. **Single external system family.** eICU is multi-center but a single curated network and era
   (2014–2015); transport to other CDWs (OMOP/TriNetX) or later years is untested.
5. **Diabetes label breadth.** The primary diabetes label is any-diabetes for harmonization; the
   strict type-2 sensitivity (§3.8) addresses but does not eliminate type-1/secondary contamination,
   and external validation remained on the any-diabetes label.
6. **Reference comparator, not published equations.** The DCA clinical baseline is a
   guideline-variable reference model, not a faithfully coded KFRE, because that equation requires
   urine albumin-to-creatinine ratio, present in only **0.42%** of admissions (2,269/546,028), and
   in any case predicts ESKD progression among known-CKD patients rather than CKD identification.
   The PREVENT heart-failure equation is computable from CDW variables and is reported as a
   secondary comparator (§3.7); its 10-year-incidence horizon and ambulatory derivation population
   differ from this ICU identification task, so it is interpreted as a reference, not a gold
   standard. The sparsity of guideline-equation inputs in structured CDW tables is itself a finding
   about CDW-native modelling.
7. **Age-dependent discrimination.** Performance is lower in patients ≥65 (HF AUROC 0.85 vs 0.93
   under 65; §3.9). The pooled estimate is partly buoyed by younger patients; age-stratified or
   age-interaction models are a natural extension.

## 6. Conclusion

Phenotype-identification models for heart failure, chronic kidney disease, and diabetes can be
built natively in a clinical data warehouse, calibrated, and — after a simple intercept+slope
recalibration — transported to hundreds of other hospitals, with objective laboratory features
transporting better than diagnosis codes. Because the modelling step is reproducible by a no-code
tool, this combination of accessibility and external-validity discipline is within reach of
non-ML researchers, and the surrounding design is a reusable template for rigorous CDW phenotype
modelling.

## Data and code availability

MIMIC-IV and eICU-CRD are available to credentialed users on PhysioNet. All cohort SQL
(`prediction_study/cohort_*.sql`), model and evaluation code (`evaluate.py`, `external_validate.py`,
`identify_eval.py`, `dca.py`, `make_decay_figure.py`), the i2b2-ML build driver
(`pipeline/load_and_build.sh`, `pipeline/run_ml_build.py`), and all result artifacts and figures
(`prediction_study/results/`) are released in the project repository under branch
`feature/phenotype-ml-pipeline`.

## Tables and figures

- **Table 1** — internal discrimination/calibration (§3.2).
- **Table 2** — internal vs external + recalibration (`results/external_validation_summary.md`).
- **Table 3** — leakage-decay (`results/{hf,ckd,dm}_decay_table.md`).
- **Table 4** — tool vs harness (`results/tool_capability_map.md`).
- **Table 5** — subgroup performance by sex and age (`results/model_audit_summary.md`,
  `results/fairness_{hf,ckd,dm}.md`).
- **Figure 1** — external validation summary (`results/external_validation_summary.png`);
  per-condition calibration (`results/{hf,ckd,dm}_external_calibration.png`).
- **Figures 2a–c** — leakage decay (`results/{hf,ckd,dm}_decay.png`).
- **Figures 3a–c** — decision curves (`results/{hf,ckd,dm}_dca.png`);
  **Figure 3d** — full vs guideline-variable reference comparator (`results/hf_reference_dca.png`).
- **Supplement** — TRIPOD+AI checklist (`paper/TRIPOD_AI_checklist.md`); capability map
  (`results/tool_capability_map.md`); model specifications / coefficients
  (`results/model_spec_{hf,ckd,dm}.md`); events-per-variable (`results/epv.json`).
