# GOTIME — what to do the moment the cohort lands

This is the pre-flight recipe. Everything in §0 is already done. §1–§3 are
the live steps you run when data arrives.

---

## §0. Pre-flight status (verified 2026-05-27)

| Component | Status | Notes |
|---|---|---|
| Docker Desktop | ✅ Running | All 5 i2b2 containers up: `i2b2-pg`, `i2b2-etl`, `i2b2-ml`, `i2b2c-web`, `i2b2-wildfly` |
| Postgres + i2b2 schemas | ✅ Healthy | `pg_isready` OK; `i2b2demodata.concept_dimension` has 190,660 rows |
| `llm_audit` migration + FK | ✅ Applied | `100_llm_audit.sql` + `110_llm_audit_fk.sql` both present, FK `fk_llm_audit_job` verified |
| jobWatcher daemon | ✅ Running | Logs: `Engine Modules are: ['llmEngine', 'mlEngine', 'BaseEngine']` |
| Eval harness | ✅ Verified | 170/170 tests pass (167 unit + 3 live_pg) |
| Synthetic-cohort smoke | ✅ Verified | EvalMockProvider: kappa=0.92 on 50 rows |
| LocalHF Qwen-0.5B fallback | ✅ Verified | Real LLM end-to-end on synthetic cohort in 2 min (quality is poor, that's expected for 0.5B — plumbing is what we proved) |
| Google Cloud SDK | ✅ Installed | `gcloud 570.0.0`, `bq 2.1.32` — needs auth (§1) |
| Provider configs | ✅ Authored | 4 ready: `anthropic.json`, `local_hf_qwen.json`, `local_hf_llama3.json`, `ollama.json` |
| Mozilla submodule | ✅ Present | Cloned + copied into `Mozilla/` |
| Python venv | ✅ Ready | `transformers 5.9.0`, `torch 2.12.0`, `psycopg2-binary 2.9.12`, `anthropic`, `openai` |
| Latest commits | ✅ Pushed | `feature/llm-module` is at the latest |

**What is NOT pre-set and needs you:**

1. **BigQuery auth** — `gcloud` was just installed; needs an interactive login (§1)
2. **ANTHROPIC_API_KEY** — not in env yet; needed only if you're using the Anthropic config
3. **PhysioNet DUA approval** — the actual permission to query MIMIC (this is the long-pole)

---

## §1. One-time auth (do this NOW while you wait)

### BigQuery (~2 min, interactive browser)

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_GCP_PROJECT_ID
```

If you don't have a GCP project, create one at https://console.cloud.google.com/projectcreate
and link it to a billing account (queries against MIMIC are free for credentialed
users, but BigQuery still requires a project for accounting).

### Anthropic (optional — only if using `configs/anthropic.json`)

```bash
export ANTHROPIC_API_KEY='sk-ant-...'
# Or add to ~/.zshrc for persistence
```

---

## §2. Pull the cohort the moment DUA lands (~60 seconds)

```bash
cd ~/i2b2-ml-project
bq query --use_legacy_sql=false --format=csv --max_rows=10000 \
    < sql/cohort_v1.sql > /tmp/cohort_v1.csv

wc -l /tmp/cohort_v1.csv     # expect ~1000 rows + header
head -2 /tmp/cohort_v1.csv   # confirm columns: subject_id,hadm_id,note_id,note_date,text,hf_gold
```

If BigQuery is slow or the SQL has issues, the alternative is to download
the parquet snapshot from PhysioNet and use pandas. The CSV is the fastest
path.

---

## §3. Run the eval — pick a provider

### §3A. RECOMMENDED: Anthropic (best quality, fast, ~$5–10 for 1000 patients)

```bash
cd ~/i2b2-ml-project
source .venv/bin/activate
PYTHONPATH=. python evaluation/run_demonstration.py \
    --cohort  /tmp/cohort_v1.csv \
    --config  evaluation/configs/anthropic.json \
    --out-root evaluation/results
```

Watch the output. Expect roughly:
- 1000 patients × ~1 sec/call (Anthropic is fast) = **~17 minutes**
- Cost: ~$5–10 (Sonnet 4.5 at $3/Mtok input + ~$15/Mtok output, prompts are ~700 tok each)

Results land at `evaluation/results/<UTC-timestamp>/`. The key file is
`metrics_summary.json`:

```json
{
  "cohen_kappa": 0.XX,
  "sensitivity": 0.XX,
  "specificity": 0.XX,
  ...
}
```

### §3B. NO-CREDENTIAL FALLBACK: LocalHF Qwen-0.5B (works right now, bad quality)

```bash
PYTHONPATH=. python evaluation/run_demonstration.py \
    --cohort  /tmp/cohort_v1.csv \
    --config  evaluation/configs/local_hf_qwen.json \
    --out-root evaluation/results
```

Qwen-0.5B is a toy model — expect kappa near 0. **Use only to prove
the pipeline works on real data while you wait for Anthropic creds.**
~3 minutes for 1000 patients on Mac CPU.

### §3C. GOOD-QUALITY OFFLINE: LocalHF Llama-3-8B (needs GPU, or hours on Mac CPU)

```bash
PYTHONPATH=. python evaluation/run_demonstration.py \
    --cohort  /tmp/cohort_v1.csv \
    --config  evaluation/configs/local_hf_llama3.json \
    --out-root evaluation/results
```

Best on Discovery (Dartmouth GPU). On Mac CPU this would take 10–20
hours for 1000 patients. The H-3 fix means Llama-3 automatically uses
the chat template (this matters for quality).

---

## §4. After the run

```bash
# Browse results
ls -la evaluation/results/<timestamp>/

# Quick metric summary
python -c "import json; print(json.dumps(json.load(open('evaluation/results/<timestamp>/metrics_summary.json')), indent=2))"

# Look at errors
head -20 evaluation/results/<timestamp>/error_analysis.csv

# Look at audit log
sqlite3 evaluation/results/<timestamp>/audit.sqlite \
    "SELECT count(*) AS rows, count(DISTINCT patient_num) AS patients, guardrail_outcome FROM llm_audit GROUP BY guardrail_outcome"
```

---

## §5. Hand-off to Kavi (after the first real run)

The `evaluation/results/<timestamp>/` directory is fully self-contained
and reproducible — it includes `run_config.json` with the git SHA, the
prompt template hash, the cohort path, and the provider config snapshot.

Suggested email:

> **Subject:** First demonstration eval — kappa = 0.XX on N MIMIC patients
>
> The LLM module is now end-to-end against real MIMIC. Quick results:
>
> - Cohort: N adult patients with discharge notes, gold = any I50.* ICD-10
> - Provider: claude-sonnet-4-5 via Anthropic
> - Metrics: kappa=0.XX, sens=0.XX, spec=0.XX, AUROC=0.XX
> - Cost: ~$X.XX
> - Reproducibility receipt: PR #1 commit <SHA>, run timestamp <UTC>
>
> Full results table + error analysis attached. Two open questions for
> Thursday: (1) is this kappa acceptable for the paper's first table?
> (2) should I rerun with the larger Llama-3-70B on Discovery for
> comparison before we lock the numbers?

---

## §6. If something goes wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| `gcloud: command not found` | New shell didn't pick up the PATH from the brew install | `source /opt/homebrew/share/google-cloud-sdk/path.zsh.inc` or restart terminal |
| `PermissionError: Provider 'anthropic' is external...` | `external_provider` is not Python `True` | Check `evaluation/configs/anthropic.json` — must be lowercase `true` (JSON boolean, not string) |
| `KeyError: 'mock'` | Eval mock provider not registered | Set `provider.name` to `local_hf`, `ollama`, `anthropic`, or `openai_compatible` — `mock` is only auto-registered when running the sample_config |
| Live-PG tests fail in mixed pytest run | conftest stub order conflict between LLM and eval test dirs (now fixed); shouldn't recur | Run separately: `pytest tests/LLM/` then `RUN_LIVE_PG=1 pytest tests/LLM/test_live_pg.py` |
| Anthropic 401 | `ANTHROPIC_API_KEY` not set or invalid | `echo $ANTHROPIC_API_KEY` to verify; regenerate at console.anthropic.com if needed |
| `bq query` hangs | First-time BigQuery setup | `bq query --use_legacy_sql=false 'SELECT 1'` to validate auth + project setup |

---

## §7. Time-budget table

| Step | Wall-clock |
|---|---|
| §1 BigQuery auth | 2 min (one-time) |
| §1 export ANTHROPIC_API_KEY | 10 sec |
| §2 pull cohort via bq | ~1 min |
| §3A Anthropic eval (1000 patients) | ~17 min |
| §3B Qwen-0.5B eval (1000 patients) | ~3 min (bad quality) |
| §3C Llama-3-8B on Discovery | ~30 min (GPU) |
| §4 inspect results | 5 min |
| **Total §1 → §4 with Anthropic** | **~25 min** |
