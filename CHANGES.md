# CHANGES — i2b2-ML LLM Integration (Track C)

## 1. Summary

This change adds a new `i2b2_cdi/LLM/` module that mirrors the existing `i2b2_cdi/ML/`
job-engine pattern and registers a fourth job type family — `llm`, `llm-label`,
`llm-extract`, `llm-feature` — dispatched through the same `BaseEngine` /
`jobWatcher` lifecycle the published JAMIA Open paper documents. The first
use case (cohort labeling from clinical notes) ships fully implemented with
four real providers (Anthropic, OpenAI-compatible, Ollama, local HuggingFace),
schema + hallucination validators, a `llm_audit` table for reproducibility,
and a 128-test pytest suite that runs with zero real network calls.

The module is auto-discovered by `jobOrchestrator.get_engine_modules()` —
no edits to `jobOrchestrator.py` or `__main__.py` were required. The single
production-file edit outside the new tree is two physical lines added to
`i2b2_cdi/loader/i2b2_cdi_app.py` to register the LLM Flask-RESTX namespace.

## 2. Files created

### Module code (`i2b2_cdi/LLM/`)
- `__init__.py`
- `llmEngine.py` — `llmEngine(BaseEngine)` (lowercase first letter to match filename, D-2.naming)
- `runner.py` — CLI subcommand stub (auto-discovered by `__main__.get_config_modules`)
- `llm_API.py` — `register_with_api(api, auth, projectNameHeader)` builds `nsLLM`
- `concept_API.py` — POST `/etl/llm_build_model` handler
- `llm_usecase.py` — `dispatch_usecase` routes on jobType suffix
- `perform_LLM.py` — `build_llm_concept` validates + persists augmented blob
- `apply_LLM.py` — `run_label` end-to-end per-patient loop
- `llm_helper.py` — `render_prompt`, `chunk_notes`, `retry_with_backoff`,
  `compute_prompt_hash`, `RetryableValidationError`
- `audit.py` — `PromptAuditLogger`
- `providers/__init__.py` — registry with auto-managed LOCAL/EXTERNAL sets + invariant
- `providers/base.py` — `LLMProvider` ABC + `LLMResponse` pydantic model
- `providers/anthropic.py` — `claude-sonnet-4-5` default, prompt caching off by default
- `providers/openai_compatible.py` — requires base_url+model at __init__, api_key defaults to "not-needed"
- `providers/ollama.py` — stdlib urllib, default `http://localhost:11434`
- `providers/local_hf.py` — 4bit-bnb → fp16/bf16 GPU → fp32 CPU fallback
- `validators/__init__.py`
- `validators/structured_output.py` — `SchemaValidator` + `coerce_text_to_dict` (whole→XML→fence→brace→None)
- `validators/hallucination_guard.py` — case-insensitive evidence check by default
- `prompts/cohort_labeling.txt`
- `prompts/concept_extraction.txt`
- `prompts/README.md`
- `README.md`

### Tests (`tests/LLM/`)
- `__init__.py`
- `conftest.py` — sys.modules stubs (Mozilla, psycopg2, pyodbc, tabulate),
  sqlite-backed `FakeCrcDataSource` with PG-placeholder translator, fixtures
- `test_helpers.py` — 18 tests
- `test_validators.py` — 26 tests
- `test_registry.py` — 15 tests
- `test_providers.py` — 16 tests
- `test_audit.py` — 9 tests
- `test_engine.py` — 8 tests
- `test_build_and_retry.py` — 7 tests
- `test_real_providers.py` — 26 tests (Anthropic/OpenAI-compat/Ollama exception translation)
- `test_api.py` — 3 Flask-RESTX namespace tests
- `fixtures/__init__.py`
- `fixtures/mock_provider.py` — `MockProvider` with 5 fail modes
- `fixtures/mimic_note_sample.json` — 5 synthetic notes with expected labels
- `README.md`

### Sample files (`sample_files/LLM/`)
- `note_label_usecase.json`
- `concept_extract_usecase.json` (placeholder — Sprint 3+)
- `README.md`

### Migrations
- `deployment/pg/100_llm_audit.sql`
- `deployment/mssql/100_llm_audit.sql`

## 3. Files modified outside `i2b2_cdi/LLM/`

### `i2b2_cdi/loader/i2b2_cdi_app.py`
Two physical lines added immediately after `auth = HTTPBasicAuth()` (the L162
anchor referenced in DECISIONS.md D-3.2):
```python
from i2b2_cdi.LLM.llm_API import register_with_api as _register_llm_api
_register_llm_api(api, auth, projectNameHeader)
```

### `requirements.txt`
Added pinned/range entries:
- `anthropic>=0.40.0` — official Anthropic SDK (D-5.1)
- `openai>=1.40.0` — official OpenAI SDK for the openai_compatible provider (D-5.1)
- `pytest>=8.0.0` — test framework (was missing from the production requirements file)
- `pytest-mock>=3.10.0` — mocker fixture used by several tests

`jinja2`, `jsonschema`, `pydantic`, `flask-restx`, `flask-httpauth`, `loguru`,
and `pandas` were already pinned in the existing requirements.txt — no
changes needed for those.

LocalHF / Ollama runtime deps (`transformers`, `accelerate`, `bitsandbytes`,
`sentencepiece`) are intentionally NOT added to requirements.txt — they are
heavy and only needed when an operator actually chooses the local_hf provider.
The provider raises a clear `RuntimeError` with the install command if they
are missing.

## 4. Test results

```
128 passed, 6 warnings in 0.36s
```

(6 warnings are the pre-existing `body=` deprecation in Flask-RESTX 1.3.x —
D-3.6 says to match the existing ML endpoints which all use `body=`. Codebase-
wide cleanup is post-this-project.)

## 5. Acceptance-criteria → named-test mapping (LLM_MODULE_SPEC §2.10)

| # | Criterion | Test(s) | Status |
|---|-----------|---------|--------|
| 1 | jobWatcher logs `Engine Modules are: [..., 'llm']` | `test_engine.py::test_dispatch_routes_llm_label` + `test_live_pg.py::test_live_pg_llmengine_glob_discovery` (live) — captured log line `Engine Modules are: ['llmEngine', 'mlEngine', 'BaseEngine']` from the running `i2b2-ml` container | ✅ unit + live |
| 2 | POST `/etl/llm_build_model` returns 200 + creates concept | `test_api.py::test_register_with_api_returns_namespace`, `::test_namespace_contains_build_and_apply_endpoints`, `test_build_and_retry.py::test_build_concept_persists_augmented_blob` | ✅ |
| 3 | POST job creates PENDING row | Existing `i2b2_cdi.job.jobs.processRequestJob` is unchanged; `test_live_pg.py::test_live_pg_full_label_job_end_to_end` does the actual `INSERT INTO i2b2demodata.job ... VALUES (..., 'PENDING', 'llm-label', ...)` against real PG and the watcher picks it up within 10s | ✅ unit + live |
| 4 | Status transitions PENDING → PROCESSING → COMPLETED | `test_live_pg.py::test_live_pg_full_label_job_end_to_end` polls real PG until `job.status='COMPLETED'` (verified 2026-05-27 on macOS 15.6.1 / Docker 29.5.2; transition observed in 4-6s) | ✅ live |
| 5 | `observation_fact` contains one row per labeled patient | `test_engine.py::test_run_label_iterates_target_and_calls_send_facts` (unit) + `test_live_pg.py::test_live_pg_full_label_job_end_to_end` asserts `SELECT count(*) FROM observation_fact WHERE concept_cd='LIVE_PG_HF'` > 0 (live: 2 rows seen on 2026-05-27 with a 2-patient cohort) | ✅ unit + live |
| 6 | `llm_audit` contains one row per provider call | `test_audit.py::test_audit_log_writes_one_row_full_mode`, `::test_audit_rows_written_counter_increments`; `test_build_and_retry.py::test_run_label_retries_on_schema_invalid_and_then_succeeds` (per-attempt rows); `::test_run_label_exhausts_writes_extra_exhausted_row` (exhausted row); `test_live_pg.py::test_live_pg_full_label_job_end_to_end` asserts the real PG `llm_audit` table received one row per attempt (live: 2 rows for 2 patients, both `passed`) | ✅ unit + live |
| 7 | `job.output` JSON contains summary stats | `test_engine.py::test_run_label_populates_summary_keys` (unit); live capture from the same run: `{"n_processed": 2, "n_labeled_positive": 1, "n_failed_validation": 0, "mean_confidence": 0.885, "total_cost_usd": 0.0, "total_latency_s": 0.002, "audit_rows_written": 2}` | ✅ unit + live |
| 8 | All unit tests pass with mocked provider; no real API calls in CI | `pytest tests/LLM/` → 129 pass + 3 deselected (`live_pg`, opt-in only). `RUN_LIVE_PG=1 pytest tests/LLM/` → 132 pass total. No `import requests`/SDK-call escape-hatch outside provider tests, which stub SDK modules via `monkeypatch.setitem(sys.modules, ...)` | ✅ |

## 6. Per-provider exception translation table (D-5.7)

| Provider | SDK exception | Translated to | Retry? |
|---|---|---|---|
| Anthropic | `APITimeoutError` | `TimeoutError` | Yes |
| Anthropic | `APIConnectionError` | `ConnectionError` | Yes |
| Anthropic | `RateLimitError` (429) | `ConnectionError` | Yes |
| Anthropic | `APIStatusError` 5xx | `ConnectionError` | Yes |
| Anthropic | `APIStatusError` 4xx | RAW | No (config bug) |
| OpenAI-compat | same shape as Anthropic | same | same |
| Ollama | `socket.timeout` | `TimeoutError` | Yes |
| Ollama | `urllib.error.URLError` | `ConnectionError` | Yes |
| Ollama | `HTTPError` 5xx | `ConnectionError` | Yes |
| Ollama | `HTTPError` 4xx | RAW | No |
| LocalHF | `torch.cuda.OutOfMemoryError` | RAW | **No — never retry OOM** |
| LocalHF | `OSError` (HF download) | `ConnectionError` | Yes |
| LocalHF | any other load failure | `RuntimeError` (wrapped) | No (config/corruption) |
| LocalHF | inference errors other than OOM | RAW | No |

The retry helper (`llm_helper.retry_with_backoff`) only retries
`(TimeoutError, ConnectionError, RetryableValidationError)`. Everything else
propagates immediately.

## 6.5. Live-PG acceptance smoke — verification receipt

Executed end-to-end on **2026-05-27** on macOS 15.6.1 (arm64) with Docker
Desktop 29.5.2 and Python 3.12.4 against the bundled `deployment/pg/`
docker-compose stack. The 3 tests in `tests/LLM/test_live_pg.py` ran in
~8 s against a real Postgres container with a real `jobWatcher` daemon
running in the `i2b2-ml` container.

| Test | Outcome |
|---|---|
| `test_live_pg_llm_audit_table_exists` | ✅ PASS — `100_llm_audit.sql` applied; 17 columns + 3 indexes verified |
| `test_live_pg_llmengine_glob_discovery` | ✅ PASS — live `jobOrchestrator` discovered `llmEngine.py` (`Engine Modules are: ['llmEngine', 'mlEngine', 'BaseEngine']` captured from `i2b2-ml` logs) |
| `test_live_pg_full_label_job_end_to_end` | ✅ PASS — 2-patient cohort, MockProvider via `LLM_ENABLE_MOCK_PROVIDER=1`, job transitioned `PENDING → PROCESSING → COMPLETED` in ~4 s, 2 `llm_audit` rows + 2 `observation_fact` rows + correctly-shaped `job.output` |

### Reproducibility setup (what was needed beyond the SPEC)

This pass surfaced several real integration concerns the spec didn't predict.
They were resolved with **non-invasive overrides** so the upstream
`docker-compose.yml` and runtime code stay untouched:

1. **`deployment/pg/docker-compose.override.yml`** (new) — remaps the
   `i2b2-etl` Flask port from `5000:5000` to `5005:5000` so the stack can
   boot on macOS without disabling Control Center's AirPlay Receiver.
   Uses the `!override` YAML tag because compose v2.24+ merges list
   fields by default. Also adds a `tests/` bind mount + the
   `LLM_ENABLE_MOCK_PROVIDER=1` env var to the `i2b2-ml` service.

2. **`Mozilla/` submodule** — must be cloned from
   `https://github.com/i2b2/i2b2-cdi-qs-mozilla` and copied into the
   project root before the i2b2-etl service starts (it is bind-mounted
   in via `../../Mozilla:/usr/src/app/Mozilla`). Gitignored.

3. **`ALTER USER i2b2 SET search_path = i2b2demodata, public`** — the
   bundled `i2b2/i2b2-pg-vol:1.3.1` seed image creates schemas inside
   one `i2b2` database, but `jobOrchestrator`'s `SELECT * from job` is
   unqualified. Without the search_path override the watcher logs
   `relation "job" does not exist` every 10 s. This is an **upstream bug**
   in the existing jobOrchestrator (banked for Kavi in
   `KAVI_CHECKLIST.md`); the live_pg test documents the workaround.

4. **`LLM_ENABLE_MOCK_PROVIDER=1`** (new env-var gate, added to
   `i2b2_cdi/LLM/providers/__init__.py`) — opt-in registration of the
   test fixture's MockProvider in the production registry. Off by default;
   only enabled for the live-PG acceptance smoke so the watcher can run
   end-to-end without hitting a real LLM endpoint. Falls back silently if
   the test fixture is not importable.

5. **`tests/LLM/test_live_pg.py`** — uses `CRC_PG_DATABASE` env var
   (defaults to `i2b2`) for the actual psycopg2 `dbname`, distinct from
   `CRC_DB_NAME` (`i2b2demodata`) which the production code uses as the
   PostgreSQL `search_path` per `i2b2_cdi/database/database_helper.py:63-64`.

### To reproduce

```bash
git clone https://github.com/Vedhsai-codes/i2b2-ml-project.git
cd i2b2-ml-project
git checkout feature/llm-module

# venv
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # includes tabulate + psycopg2-binary
pip install pytest pytest-mock

# Mozilla submodule (gitignored, must be cloned fresh)
cd /tmp && git clone https://github.com/i2b2/i2b2-cdi-qs-mozilla.git
cp -r /tmp/i2b2-cdi-qs-mozilla/Mozilla ~/path/to/i2b2-ml-project/

# Pull pre-built image (skip local build)
docker pull i2b2/i2b2-etl:latest
docker tag i2b2/i2b2-etl:latest i2b2/i2b2-etl:local-v1

# Boot minimal stack (compose auto-loads docker-compose.override.yml)
cd ~/path/to/i2b2-ml-project/deployment/pg
docker compose up -d i2b2-pg-vol-loader i2b2-pg i2b2-etl i2b2-ml

# Wait ~90s for i2b2-etl bootstrap (project upgrade creates the job table)
sleep 90

# Fix the schema search_path so the watcher's unqualified SELECT works
docker exec i2b2-pg psql -U postgres -d i2b2 -c \
    "ALTER USER i2b2 SET search_path = i2b2demodata, public;"

# Apply the LLM migration
docker cp deployment/pg/100_llm_audit.sql i2b2-pg:/tmp/m.sql
docker exec i2b2-pg psql -U i2b2 -d i2b2 -f /tmp/m.sql

# Restart watcher to pick up the new search_path
docker restart i2b2-ml

# Run the live_pg suite
cd ~/path/to/i2b2-ml-project
CRC_DB_HOST=localhost CRC_DB_PORT=5432 \
CRC_DB_USER=i2b2 CRC_DB_PASS=demouser \
CRC_DB_NAME=i2b2demodata CRC_PG_DATABASE=i2b2 \
RUN_LIVE_PG=1 \
python -m pytest tests/LLM/test_live_pg.py -v
# expect: 3 passed
```

## 7. Manual smoke procedure (live-PG, real providers)

```bash
# 1. Boot the stack
docker-compose up -d
docker exec -it i2b2-etl bash

# 2. Apply the migration
psql -U i2b2 -d i2b2demodata -f /deployment/pg/100_llm_audit.sql

# 3. Start the job watcher
source /usr/src/app/.venv/bin/activate
python -m i2b2_cdi.job.jobWatcher &

# 4. POST the concept (Swagger UI at /swagger/ or curl)
curl -u demo\\demo:Etl@2021 -H "X-Project-Name: Demo" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:5000/etl/llm_build_model \
  -d @sample_files/LLM/note_label_usecase.json

# 5. POST a job
curl -u demo\\demo:Etl@2021 -H "X-Project-Name: Demo" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:5000/etl/job \
  -d '{"input":{"path":"/LLM/Diagnosis/HeartFailure_LLM"},"jobType":"llm-label"}'

# 6. Inspect
psql -U i2b2 -d i2b2demodata -c \
  "SELECT id, status, job_type, output FROM job ORDER BY id DESC LIMIT 5;"
psql -U i2b2 -d i2b2demodata -c \
  "SELECT count(*), guardrail_outcome FROM llm_audit GROUP BY guardrail_outcome;"
```

## 8. Architectural decisions log (Steps 1-5 from DECISIONS.md, plus implementation pass)

The full decision log is in `DECISIONS.md`. Highlights that shape the code:

- **D-pre.1** Anthropic default is `claude-sonnet-4-5` (not Opus, not the non-existent `claude-opus-4-7`).
- **D-2.1 / D-3.3** External-provider gate reads `cls.is_external`; LOCAL/EXTERNAL sets are auto-managed views with an import-time invariant assertion.
- **D-2.2** `register_provider` / `unregister_provider` are public API for tests and future extensions.
- **D-2.5** `BaseEngine.save_output` double-encode bug is pre-existing — NOT fixed here (see KAVI_CHECKLIST.md item 3).
- **D-2.6** Sqlite fake translates `%(name)s → :name` then `%s → ?`. Named pass first.
- **D-3.1** Flask-RESTX Namespace, NOT plain Blueprint. `register_with_api` is the entry point.
- **D-3.2** Two physical lines in `loader/i2b2_cdi_app.py` at the `auth = HTTPBasicAuth()` anchor.
- **D-3.6** `body=` deprecation kept to match existing ML endpoints. Codebase-wide cleanup post-project.
- **D-4.2** Per-attempt audit row + extra "exhausted" row on terminal failure.
- **D-4.3** Audit DB failure does NOT abort the clinical job (sidecar pattern).
- **D-4.4** `SchemaValidator.__init__` runs `Draft7Validator.check_schema` so malformed schemas fail at concept-build, not at 2 AM.
- **D-4.5** `coerce_text_to_dict` order: whole → `<json>` tags → ```json fence → widest brace block → None.
- **D-4.6** Hallucination guard evidence check is case-insensitive by default; opt-in case-sensitive via `case_sensitive_evidence: true`.
- **D-4.7** `_StubDataSource.__enter__` raises AssertionError if reached without a fixture (loud failure beats silent).
- **D-4.8** `audit_rows_written` counter in `job.output` for operator reconciliation.
- **D-5.1** Anthropic + OpenAI use official SDKs; Ollama uses stdlib urllib.
- **D-5.2** Anthropic prompt caching default OFF (1024-token min + 1.25x write cost; predictable billing > optimistic optimization).
- **D-5.3** `cost_usd = 0.0` for ALL providers; operators wire pricing in per deployment.
- **D-5.4** LocalHF fallback chain: 4-bit bnb → fp16/bf16 GPU → fp32 CPU.
- **D-5.5** OpenAI-compatible rejects missing `base_url`/`model` at `__init__` (fail-fast).
- **D-5.6** OpenAI-compat `api_key` defaults to `"not-needed"` (vLLM/LM Studio convention) — foot-gun banked.

## 9. Open questions for Dr. Wagholikar (LLM_MODULE_SPEC §2.11)

These are real architectural questions that need PI input before the first
production deploy. See `KAVI_CHECKLIST.md` for current status.

1. `/LLM/` ontology branch parallel to `/ML/`, or nested?
2. `llm_audit` table in production schema, or its own `llm` schema?
3. Default local model size — 8B quantized vs 70B-class?
4. `llm-feature` storage — floats into `nval_num` vs new `blob_value` JSONB column?

## 10. Known limitations (deferred to Sprint 3+ per LLM_MODULE_SPEC §2.9)

- `llm-extract` and `llm-feature` paths are stubs (`NotImplementedError`).
- LLM-judge guardrail mode (currently only rule-based guards).
- GUI for LLM concept creation (Track A++ territory).
- Per-tenant rate limiting on external providers.
- Fine-tuning workflows.
- Multi-modal (radiology image + report).

### 10.1 Hardcoded container-internal filesystem paths

The LLM module writes to **container-internal** paths in two places:

| Path | File | Source of convention |
|---|---|---|
| `/usr/src/app/tmp/{dfstring}` (temp concept-load CSV) | `i2b2_cdi/LLM/concept_API.py:108,115` | mirrors `i2b2_cdi/ML/concept_API.py:158,172-173` |
| `/usr/src/app/tmp/{ClassName}/output/llm_{ClassName}_facts.csv` | inherited via `BaseEngine.send_facts` in `i2b2_cdi/job/BaseEngine.py:60-62` | unchanged from upstream v4.1.0; the ML module relies on the same path |

**Implication:** the LLM module is **assumed to run inside the Dockerized
i2b2-etl container** where `/usr/src/app/` is the project root. Running the
module against a real i2b2 schema from a non-container environment (e.g.,
direct Discovery / bare-metal install) will fail at the first concept-load
attempt with a permissions or missing-directory error.

**Why not fixed in this PR:** changing the path strategy means changing it
in the ML module + `BaseEngine` too, since they all share the convention.
A codebase-wide refactor — introducing an `I2B2_TMP_DIR` environment
variable with `/usr/src/app/tmp/` as the default — is the right shape, but
it touches files outside the "LLM module only" scope this PR committed to.

**Recommended follow-up PR (out of scope here):**

1. Define `I2B2_TMP_DIR = os.environ.get("I2B2_TMP_DIR", "/usr/src/app/tmp")`
   in a shared utility module (e.g., `i2b2_cdi.common.utils`).
2. Replace literal `"/usr/src/app/tmp/..."` in `i2b2_cdi/LLM/concept_API.py`,
   `i2b2_cdi/ML/concept_API.py`, `i2b2_cdi/ML/ml_API.py`, and
   `i2b2_cdi/job/BaseEngine.py` with the env-var-backed constant.
3. Document the env var in the deployment README so non-Docker operators
   can override.

This is banked rather than done because: (a) the LLM PR's scope explicitly
excludes touching ML/job, (b) changing `BaseEngine.send_facts` requires
PI sign-off (it changes the on-disk layout for an already-published
codebase), and (c) the manual live-PG smoke procedure in §7 runs inside
the container anyway, so the limitation does not block acceptance.

## 11. Banked for post-Step-8 cleanup

1. `body=` deprecation in Flask-RESTX (D-3.6) — codebase-wide cleanup, not isolated fix.
2. `api_key="not-needed"` foot-gun (D-5.6) — detect requires-real-key domains, reject literal default in those cases.
3. Two parallel ML APIs (`ml_API.py` and `ml_usecase.py`) — pre-existing duplication, not LLM module's problem to fix.
4. `BaseEngine.save_output` double-encode bug (D-2.5) — flagged to Dr. W in `KAVI_CHECKLIST.md` for upstream fix.

## 12. How to verify end-to-end install

```bash
git clone https://github.com/Vedhsai-codes/i2b2-ml-project.git
cd i2b2-ml-project
python3 -m venv .venv
source .venv/bin/activate
pip install pytest pytest-mock jsonschema jinja2 pydantic flask flask-restx \
            flask-httpauth loguru pandas anthropic openai
python -m pytest tests/LLM/ -v
# expect: 128 passed
```
