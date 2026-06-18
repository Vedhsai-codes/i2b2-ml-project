# HANDOFF.md — read this first in a new chat

**Written:** 2026-05-28 (end of a long session, migrating to a fresh chat)
**Repo:** `~/i2b2-ml-project` · branch `feature/llm-module` · HEAD `84f2f6f`
**GitHub:** https://github.com/Vedhsai-codes/i2b2-ml-project (PR #1 open)
**Owner:** Vedhsai Thiriveedi · Lab: MGH / Dr. Kavishwar Wagholikar (Kavi)

New chat: read this file + `CHANGES.md`, then continue. Do NOT re-derive.

---

## ⭐ THE MOST IMPORTANT THING — the realignment

A prior session built a lot of **standalone** analysis (an LLM eval harness,
a standalone sklearn LogReg baseline, bootstrap CIs, CONSORT, Table 1).
Useful — but a 2026-05-28 lab meeting transcript revealed it is **NOT what
Kavi's grant paper needs.** Kavi said, repeatedly and explicitly:

> "you'd be using **this tool** to build the model"
> "we want to show you can use the **JSON UI** with your embedded code to
>  build a model so anybody who doesn't know ML can come and do it"
> "we validated the **i2b2 ML tool** on these mimic [data]"

**Kavi's paper is a TOOL-VALIDATION paper.** The claim is NOT "we have a good
model" — it is "the i2b2-ML tool, driven through its JSON API, builds
phenotype models on MIMIC, so a non-ML researcher can do it." Standalone
sklearn scripts prove a model works; they do NOT prove the *tool* works.
Only the second claim counts for his grant.

### What Kavi actually wants (verbatim asks)
1. Load a MIMIC phenotype into i2b2 as **concepts + facts** (like the
   `diabetes_concepts.csv` + facts Shambhavi loaded via the webclient ETL tab).
2. Build the model **THROUGH the i2b2 ML JSON API** — POST a `job_type: ml`
   job; the jobWatcher + `mlEngine` (existing logistic regression) builds it;
   retrieve the model + score **from the tool**.
3. Repeat for **4–5 phenotypes**: heart failure (Kavi already did), **stroke**,
   ischemic heart disease, + a couple Kavi will email risk factors for.
4. That is the whole paper: "validated i2b2-ML builds phenotype models on
   MIMIC across 5 conditions."

Kavi assigned the homework verbatim: *"take stroke and see if you can build a
model for stroke in mimic."*

### Where the LLM module fits
The entire `i2b2_cdi/LLM/` module (built + tested + committed, 167 tests) is
Kavi's **NEXT** excitement ("extend ML with LLMs — read notes, produce a fact,
fact goes back in" — the diabetes-from-notes example). It is Vedhsai's
**first-author follow-up paper**, NOT the immediate grant deliverable. Keep it;
don't lead with it. Lead with "I can build phenotype models through the i2b2
ML API on MIMIC."

---

## THE ALIGNED NEXT STEP (do this)

> **STATUS 2026-06-18:** the pipeline below is BUILT in `pipeline/` and cheap-verified
> (smoke tests + bq dry-run). Remaining: run it end-to-end on a live stack for the
> `COMPLETED` receipt, then repeat for IHD + Kavi's list. See `pipeline/README.md`.

Build a **stroke phenotype model THROUGH the i2b2 ML tool on MIMIC**:

1. Pull a MIMIC stroke cohort from BigQuery — silver standard = ICD-10
   `I63%`/`I64%`. Features pulled as structured facts (labs, dx, meds, vitals).
2. Format as i2b2 concept + fact CSVs (match `sample_files/ML/` layout —
   `*_concepts.csv` and `*_facts.csv`).
3. Load into i2b2 (`etl concept load` + `etl fact load`, or the webclient ETL tab).
4. POST the ML build job through the Swagger API (`job_type: ml`).
5. Watch the jobWatcher build the logistic-regression model; retrieve the
   score **from the tool** (model artifact lands in `concept_dimension.concept_blob`).
6. Wrap into a repeatable script so HF, stroke, IHD, + Kavi's list all run
   the same way → that repeatability IS the paper.

**Blocked on:** Kavi will email the heart-failure risk factors + the full
phenotype list "by tomorrow" (2026-05-29). The risk factors = the features
you load as facts. Cohort-feature design partly waits on that email — but you
can build the stroke cohort SQL + the load-CSV pipeline ahead of it.

---

## LIVE INFRASTRUCTURE STATE

### AWS box (Kavi-provisioned, may be deleted — confirm before relying on it)
- `ssh dev2@3.239.204.159` · password `i2b22026`
- Has Docker 29.5.2, 21 GB free, 4 GB RAM. Stock `i2b2-docker` (webclient +
  core-server + pgsql) is cloned + running there. **NOT** the ETL/ML stack.
- Webclient: `http://3.239.204.159:8080/webclient` · login `demo` / `demouser`
- NOTE: Kavi said in the call he'd delete the temp boxes to save cost. Each
  student has their own row in a Google Sheet; Vedhsai's was the unassigned
  first row `3.239.204.159`.

### Local Mac
- `~/i2b2-ml-project` — the full i2b2-etl v4.1.0 + ML module + LLM extension.
- Docker Desktop has been **WEDGED / crashing repeatedly all day** (4×).
  `open -a Docker` then wait; if stuck, force-quit + relaunch, or Docker menu →
  Troubleshoot → Restart. The laptop also rebooted twice mid-task.
- Stack brought up via: `cd deployment/pg && docker compose up -d
  i2b2-pg-vol-loader i2b2-pg i2b2-etl i2b2-ml` (4 services, ~75s bootstrap).
  `docker-compose.override.yml` remaps etl Flask 5000→5005 (macOS AirPlay) +
  sets `LLM_ENABLE_MOCK_PROVIDER=1` on i2b2-ml.
- Mozilla submodule (gitignored): cloned from
  `github.com/i2b2/i2b2-cdi-qs-mozilla`, `Mozilla/` copied into repo root.
  Must re-copy if repo is fresh-cloned.
- We dodged the Dockerfile-build bugs the new students hit by **pulling the
  prebuilt image** `i2b2/i2b2-etl:latest` and retagging `local-v1` — no local
  build. (Kavi's `install_fix` fork fixes the build bugs: Python 3.9→newer,
  missing Dockerfile backslashes, Mozilla folder naming.)

### BigQuery / gcloud — WORKING
- Authed as `vedhsait@gmail.com`, project `i2b2-mimic-eval-1779917181`, billing
  linked, BigQuery API enabled. `bq query` works. MIMIC access confirmed
  (`physionet-data.mimiciv_3_1_hosp.patients` = 364,627 patients).
- PhysioNet DUA approved 2026-05-27.
- Cohort SQL: `sql/cohort_v1.sql` (HF, 1000 patients, 7.8% HF+).
  `sql/cohort_flow.sql` (CONSORT counts), `sql/demographics.sql` (Table 1).
- **`bq` defaults to `--max_rows=100`** — always pass `--max_rows=10000`.

### Data files (persistent, NOT in git — PHI per gitignore)
- `~/mimic_data/cohort_v1.csv` — 1000-patient HF cohort
- `~/mimic_data/cohort_demographics.csv` — Table 1 source
- `evaluation/results/` is gitignored (contains MIMIC note text).

### LLM providers
- Qwen2.5-0.5B cached at `~/.cache/huggingface/` (~1 GB). Runs on Mac CPU,
  ~8s/patient. Bad classifier (kappa 0) — pilot/plumbing only.
- 4 provider configs in `evaluation/configs/`: anthropic, ollama,
  local_hf_qwen, local_hf_llama3.
- **Anthropic API key NOT set** — intentionally deferred. Vedhsai's plan:
  validate plumbing free first, THEN spend on Anthropic for paper-quality run.

---

## WHAT'S DONE vs NOT (be honest — "fully done" = NO)

### Done (engineering + supporting analysis)
- `i2b2_cdi/LLM/` module: 167 unit tests + 3 live-PG tests pass. PR #1.
- 5 HIGH self-review findings fixed (H-1..H-5). See `SELF_REVIEW.md`.
- End-to-end LLM label demo through the real jobWatcher on a real MIMIC
  patient (`evaluation/i2b2_demo.py`, CHANGES §11.7): PENDING→PROCESSING→
  COMPLETED in 8s, wrote llm_audit + observation_fact.
- Standalone supporting analysis (NOT the grant deliverable, but reusable):
  `baseline_logreg.py` (kappa 0.645, AUROC 0.95), `bootstrap_ci.py`,
  `cohort_flow_figure.py` (→ `paper/figures/`), `demographics_table.py`
  (→ `paper/tables/table1_demographics.md`), `quick_inspect.py`,
  `compare_runs.py`.

### Done (aligned deliverable — pipeline, 2026-06-18)
- **`pipeline/`** — repeatable phenotype→i2b2-ML-API pipeline (build models THROUGH
  the tool, not standalone scripts). Config-driven for stroke / HF / IHD (+ Kavi's
  list = a config edit). Files: `config/phenotypes.yaml` (single source of truth),
  `sql/cohort_template.sql` → `sql/cohort_stroke.sql` (BigQuery cohort + features),
  `build_cohort.py` (→ concept/fact/membership CSVs), `create_patient_sets.py`
  (qt_* named sets), `run_ml_build.py` (POST /etl/concepts + /etl/job jobType:ml +
  poll + retrieve), `load_and_build.sh` (runbook), `README.md`, `PLAN_*.md`.
- Verified the LIVE engine path: `jobType:ml` → `mlEngine` → `apply_build_model` reads
  cohort from `qt_patient_set_collection` (NOT the assertion-fact `ml_usecase` path).
  Reference: `tests/ML/test_ml_mimic_hf.py`.
- Cheap checks pass: `pytest pipeline/test_pipeline_smoke.py` (5), `render --all` (3
  phenotypes), `bq --dry_run` validated `cohort_stroke.sql` vs real MIMIC (6.76 GB/run).
- Adversarial multi-agent review run; fixed real items (added blob `random_seed` for
  reproducibility; negatives-have-feature-fact validation; runbook preflight + docs).
  Rejected 2 false-alarm "engine" findings about upstream `i2b2_cdi` LIKE-escaping /
  fillna (verified correct; not ours to change).

### NOT done (blocks the paper)
- **Live end-to-end receipt**: a real stroke build reaching `COMPLETED` with the model
  retrieved from `concept_blob`. Gated on a working stack (Docker was wedged). Runbook
  (`pipeline/load_and_build.sh`) is ready to execute once infra is up. THEN repeat for
  IHD + Kavi's list.
- Anthropic full-cohort LLM run (the LLM follow-up paper headline). Needs key.
- Error analysis on LLM mistakes (needs the Anthropic run first).
- The manuscript itself (zero prose written).
- Coauthor sign-off (Kavi/Praveen/Ayush). DUA check for sending MIMIC notes to
  Anthropic API.

---

## LAB CONTEXT / RELATIONSHIPS (from meeting transcripts)
- Kavi praises Vedhsai publicly: "if you look at what Vedhsai has done you'll
  blow your mind … show your UI sometime to inspire folks." Vedhsai is the
  advanced lead, **formally interning 6 months**.
- New students (Molik/Moulik, Nitin, Monique, Shreyas, Shambhavi/Chambui,
  Prabin/Praveen) are still at the install stage. Shambhavi got it running +
  is writing install docs. Praveen got model-build + API working; his blocker
  was Swagger auth.
- **Use the Google Group (mailing list), NOT Slack.** Vedhsai should join with
  a Gmail (not Outlook). Don't manage the new students — help via the group.
- Swagger auth (for when it comes up): log in `demo\demo` / `Etl@2021` — the
  PROJECT NAME (`demo`) must be prefixed. Swagger fails silently on bad auth.
- Kavi setting up **GitHub Actions CI** next week (with a company). Vedhsai's
  167 passing tests mean his repo passes out of the box — flag this.
- The published paper's docs are STALE (container renames, path changes since
  Kavi wrote it ~6 months ago). Offering corrected install notes = trust deposit.
- Roger et al. 2014 (PLOS One, PMC4134216): ICD HF coding vs chart review =
  pooled sens 75.3% / spec 96.8% / PPV ≥87%. Lets us SKIP manual inter-rater
  chart review and cite instead.

## ResearchOS operating rules (from CLAUDE.md — follow these)
- Mac = cockpit, NOT durable compute. Long jobs belong on Dartmouth/Discovery
  or the AWS box, not the flaky Mac.
- Plan → cheap sanity test → verify with a concrete artifact before claiming
  done. Atomic commits. Update STATE.md / this handoff after milestones.

---

## FIRST MESSAGE FOR THE NEW CHAT
> Read HANDOFF.md and CHANGES.md. We realigned: Kavi's grant paper needs
> phenotype models built THROUGH the i2b2 ML JSON API on MIMIC (HF done by
> Kavi; I need stroke + IHD + his emailed list), NOT standalone scripts.
> Start the aligned next step: build the MIMIC stroke cohort SQL + the i2b2
> concept/fact load pipeline, ready to POST a job_type:ml build through the API.
