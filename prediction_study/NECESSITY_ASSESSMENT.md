# Necessity assessment of the three additions (keep the paper tight)

Asked: run additions 1/2/3, then judge whether each is actually necessary. Verdict below; the goal
is to keep only what strengthens the paper and not bloat it.

## 1. TRIPOD+AI gap-closers (coefficients, EPV, sex/age fairness) — **NECESSARY, keep all**

| Sub-item | Verdict | Why |
|---|---|---|
| EPV statement (item 8) | **Keep** | One methods sentence; reviewers ask for it; trivially satisfied (EPV 1,254–2,123). |
| Coefficient/spec table (item 14) | **Keep (supplement)** | A development+validation model that isn't fully specified can't be used or replicated — this is a hard requirement, not polish. |
| Sex/age subgroup fairness (AI-3) | **Keep — highest value** | TRIPOD+AI requires it, AND it surfaced a *real, material* finding: HF AUROC 0.85 (≥65) vs 0.93 (<65). Reporting only the pooled 0.907 would have hidden this. Strengthens credibility. |

Net: all three are necessary; the fairness analysis is the most valuable because it changes how the
headline number is read.

## 2. Faithful published risk equations (KFRE, PREVENT-HF) — **mostly NOT necessary**

| Equation | Verdict | Why |
|---|---|---|
| **KFRE** | **CUT (not viable, not applicable)** | Requires urine albumin-creatinine ratio, present in **0.42%** of admissions (2,269/546,028). It also predicts *ESKD progression among known-CKD patients*, not CKD identification — wrong target entirely. Forcing it would be misleading. |
| **PREVENT-HF** | **OPTIONAL → supplement at most** | Computable from CDW variables, but predicts *10-year incident HF in ambulatory adults* — a horizon and population mismatched to ICU identification. The guideline-variable reference model (§3.7) already answers the real question ("does the full model beat established risk factors?") cleanly and without the mismatch. Implementing PREVENT-HF risks inviting more reviewer criticism than it resolves. |

Net: the existing **guideline-variable reference model** is the right comparator. KFRE is cut with a
concrete reason (now in Limitation 6). PREVENT-HF, if implemented, belongs in the supplement as a
transparency item, not the main results.

## 3. Exact-cohort i2b2-ML tool re-load — **live re-load NOT necessary; the sensitivity IS**

| Component | Verdict | Why |
|---|---|---|
| Balanced-sampling sensitivity (harness 0.902 on the tool's 800/1,600) | **Keep** | Rigorously closes the only real apples-to-oranges objection (does the tool's balanced sampling inflate its 0.914?). Answer: no — 0.902 ≈ 0.907 ≈ 0.914. Zero DB risk. |
| Live re-load of the 546k aligned cohort through the tool | **CUT (not necessary)** | (a) The plugin caps training (`sample_size_limit`) and subsamples, so it would not reproduce 0.907 on the full cohort anyway; (b) `build_cohort.py` requires the config's feature set, which differs from the aligned cohort (cm_chf/cm_carotid/lipids vs K/HCO3/BUN/Cl) — needs pipeline surgery; (c) it writes ~13M facts into the live DB shared with the grant paper's build state; (d) existing durable receipts + the sensitivity already substantiate the accessibility claim. |

Net: the sensitivity analysis was the necessary part and it's done. The literal live re-load is
high-risk, low-marginal-value, and partly unachievable — recommend not doing it. (Steps to do it in
isolation are documented in NEXT_STEPS if ever wanted.)

## Bottom line

Keep: all of #1, and the #3 sampling sensitivity. Cut: KFRE (#2) and the live tool re-load (#3).
Optional/supplement: PREVENT-HF (#2). Net effect on the paper: one strong new results section
(fairness), a fully specified model, a closed apples-to-oranges objection, and two honest "we
considered X and here's why we didn't force it" notes — tighter and more defensible, not more
bloated.
