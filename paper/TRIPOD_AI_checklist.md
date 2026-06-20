# TRIPOD+AI reporting checklist

Mapping of TRIPOD+AI (Collins et al., *BMJ* 2024) items to `PREDICTION_MANUSCRIPT.md`. This is a
**development + external validation** study of clinical-prediction (phenotype-identification)
models; items are addressed for both the MIMIC-IV development and the eICU-CRD validation.

| # | TRIPOD+AI item | Addressed? | Where / note |
|---|---|---|---|
| **Title & abstract** | | | |
| 1 | Identify as ML prediction model; population/outcome | Yes | Title; Abstract |
| 2 | Structured summary (objectives, data, methods, results) | Yes | Abstract (Background/Methods/Results/Conclusions) |
| **Introduction** | | | |
| 3a | Background, rationale, existing models | Yes | §1 |
| 3b | Objectives / hypotheses | Yes | §1 (accessibility + transportability; lab-vs-code hypothesis) |
| **Methods — Source of data** | | | |
| 4a | Study design, key dates | Yes | §2.1 (MIMIC-IV v3.1; eICU-CRD v2.0, 2014–2015) |
| 4b | Development vs validation data separation | Yes | §2.1, §2.6 (frozen MIMIC→eICU) |
| **Methods — Participants** | | | |
| 5a | Setting (centers, ICU) | Yes | §2.1 (1 academic ICU dev; 208 hospitals validation) |
| 5b | Eligibility (all-comers, ≥… admissions) | Yes | §2.2 |
| 5c | Data flow / cohort derivation | Yes | §2.2; cohort SQL released |
| **Methods — Outcome** | | | |
| 6a | Outcome definition (ICD code sets) | Yes | §2.2 (I50/428; N18/585; E08–E13/250) |
| 6b | Outcome assessment blinded to predictors | N/A | code-derived label; §4 (silver standard) limitation |
| **Methods — Predictors** | | | |
| 7a | Predictors + timing | Yes | §2.3 (30 features; index-admission / blackout window) |
| 7b | Predictor assessment blinded to outcome | Partial | features computed independently of label; self-comorbidity excluded (§2.3) |
| **Methods — Sample size** | | | |
| 8 | Sample size justification | Yes | §2.5 — EPV 1,254–2,123 (56k–93k events / 44–45 predictors), far above ≥10–20 (`results/epv.json`) |
| **Methods — Missing data** | | | |
| 9 | Missing-data handling | Yes | §2.4 (median imputation + missing indicators) |
| **Methods — Analytical methods** | | | |
| 10a | Model type / architecture | Yes | §2.4 (elastic-net logistic regression) |
| 10b | Predictor handling, preprocessing | Yes | §2.4 (scaling, passthrough binary) |
| 10c | Model building / tuning (CV, grid, seed) | Yes | §2.4 (4-fold inner CV; grid; seed 42) |
| 10d | Class imbalance handling | Yes | §2.4 (natural prevalence; **no SMOTE**, with rationale) |
| 10e | Internal validation method | Yes | §2.5 (30% stratified hold-out; 1000× bootstrap CIs) |
| **Methods — Performance & fairness** | | | |
| 11 | Discrimination, calibration, utility measures | Yes | §2.5–2.8 (AUROC/AUPRC; slope/intercept/Brier; DCA) |
| 12 | External validation procedure | Yes | §2.6 (frozen transport + recalibration hierarchy) |
| **Results** | | | |
| 13a | Participant flow / characteristics | Yes | §3.1 (N, prevalence per source) |
| 13b | Comparison dev vs validation cohorts | Yes | §3.1, §3.3 (prevalence shift, harmonization) |
| 14 | Model specification / coefficients | Yes | §3.2 + standardized coefficients/odds ratios per model (`results/model_spec_{hf,ckd,dm}.md`); serialized tool models in receipts |
| 15 | Model performance (with CIs) | Yes | §3.2–3.3 (Tables 1–2; bootstrap CIs) |
| 16 | Model updating / recalibration results | Yes | §3.3 (intercept-only vs intercept+slope) |
| **Discussion** | | | |
| 17 | Limitations | Yes | §5 (six items) |
| 18 | Interpretation vs evidence | Yes | §4 |
| 19 | Generalizability | Yes | §4 (transport), §5 (ICU, single external family) |
| **Other** | | | |
| 20 | Funding / conflicts | TBD | to be completed by authors |
| 21 | Data/code availability | Yes | §6 |
| **AI-specific (TRIPOD+AI)** | | | |
| AI-1 | Open science: code, data access, model availability | Yes | §6 (SQL, code, receipts, figures released) |
| AI-2 | Reproducibility (seeds, environment, pipeline) | Yes | §2.4 (seed 42); released env + one-command rebuild |
| AI-3 | Fairness considerations / subgroup analysis | Yes | §3.9 — AUROC + calibration by sex and age band (`results/fairness_{hf,ckd,dm}.md`); age gap disclosed; race-free eGFR used |
| AI-4 | No outcome leakage into predictors | Yes | §2.3 (self-comorbidity excluded) + §2.7/§3.4 (leakage ablation quantifies residual proximity) |

**Summary:** the manuscript addresses the TRIPOD+AI items required of a development + external
validation prediction study, including the previously-open items now closed — sample-size/EPV
(item 8), the per-model coefficient/specification supplement (item 14), and the sex/age subgroup
fairness analysis (AI-3). The only remaining author-supplied item is funding/conflicts (item 20).

---

# PROBAST risk-of-bias self-assessment

PROBAST (Wolff et al., 2019) — four domains, signalling questions summarised. Rating: **Low / High
/ Unclear** risk of bias and concern for applicability.

| Domain | Key signalling questions | RoB | Rationale |
|---|---|---|---|
| **1. Participants** | Appropriate data source? Inclusions/exclusions? | **Low** | Retrospective CDW cohorts, all-comers per-admission, natural prevalence; aligned dev/val definitions. ICU setting noted under applicability. |
| **2. Predictors** | Defined/assessed without outcome knowledge? Available at intended use? | **Low–Unclear** | 30 routine CDW features; self-comorbidity excluded; leakage ablation quantifies outcome-proximal signal. Concurrent design is identification, not forecasting (stated). |
| **3. Outcome** | Defined appropriately? Determined without predictor knowledge? | **Unclear** | ICD-code (silver) labels, not chart-adjudicated; eICU required `pasthistory` augmentation. Transparent and consistent across sources. |
| **4. Analysis** | Reasonable sample size/EPV? Missing data handled? Overfitting avoided? Calibration & discrimination reported? Model evaluated externally? | **Low** | Very large N with ample events; median+indicator imputation; elastic-net regularization + inner-CV; bootstrap CIs; calibration + DCA; **external validation across 208 hospitals** with recalibration. No SMOTE. |

**Applicability:** intended use is CDW phenotype identification in inpatient/critical-care settings;
applicability concern is **moderate** for non-ICU populations (both sources are critical-care).

**Overall:** low risk of bias for analysis and participants; the main residual concern is
outcome-label standard (code-derived), explicitly disclosed and partially mitigated by the
strict-type-2 sensitivity and the leakage ablation.
