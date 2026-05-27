# AUDIT.md — i2b2-ML LLM Integration

**Audit date:** 2026-05-27
**Branch:** `feature/llm-module` (2 commits ahead of `main`)
**Auditor:** Claude (this session, no code changes performed)

This audit was performed against the working tree at
`/Users/Vedhsai/i2b2-ml-project/` immediately after the `feature/llm-module`
branch was pushed and PR #1 opened. **No files were modified during this audit.**

---

## TL;DR

| Step | Status | Notes |
|---|---|---|
| 1. Scaffold | ✅ completed | All §2.2 files exist with full implementations (not stubs) |
| 2. Engine + provider abstraction + Mock | ✅ completed | 8/8 Step-2 named tests pass |
| 3. Routes + retry + registry consistency | ✅ completed | Flask-RESTX Namespace registered; loader edit applied |
| 4. Validators + audit | ✅ completed | 26 validator + 9 audit tests pass |
| 5. Real providers | ✅ completed | 26 real-provider tests pass with stubbed SDKs |
| **6. Acceptance / live-PG** | **⚠ PARTIAL** | **Docker not installed on this machine; live-PG smoke never ran. 7/8 §2.10 criteria covered by named unit tests; criterion #4 (job status transitions) NOT proven end-to-end** |
| 7. Polish (samples + READMEs) | ✅ completed | All 4 READMEs + 2 sample JSONs present with real content |
| 8. CHANGES.md | ✅ completed | 12 sections, exceeds the 8 required |

**Tests:** 129 passed, 0 skipped, 0 failed, 6 pre-existing warnings.

---

## A. Step 6 — Acceptance / live-PG

### Did Docker actually run?

**NO.** Docker is not installed on this machine:

```
$ which docker
docker not found
$ docker ps
zsh: command not found: docker
```

No `docker-compose up` was ever executed in this session. The user noted in
their initial handoff: *"Docker isn't installed yet. Need brew install --cask docker or a pip-based install."* That gap was not closed.

### Did the live-PG smoke test (RUN_LIVE_PG=1) execute?

**NO.** Stronger statement: **the `live_pg` pytest marker was never implemented.**

```
$ grep -n "RUN_LIVE_PG\|live_pg" tests/LLM/*.py
(no matches)
```

The PLAYBOOK §Step 6 prompt called for tests gated by `RUN_LIVE_PG=1` and
runnable via `pytest -m live_pg`. No such marker exists in the suite. The
manual procedure is documented in [CHANGES.md §7](CHANGES.md), but no
automation exists, and no human has run it yet.

### Acceptance criteria → test mapping (per LLM_MODULE_SPEC §2.10)

| # | Criterion | Test name | Status | Proves criterion? |
|---|---|---|---|---|
| 1 | jobWatcher logs `Engine Modules are: [..., 'llm']` | None directly — verified by inspection: `python -c "import glob; print(glob.glob('i2b2_cdi/*/*Engine.py'))"` finds `llmEngine.py` | ✅ glob discovery confirmed at runtime in this session | **Partial.** Glob is verified; jobWatcher boot is not. |
| 2 | POST `/etl/llm_build_model` returns 200 + creates concept | `test_api.py::test_register_with_api_returns_namespace`, `::test_namespace_contains_build_and_apply_endpoints`, `test_build_and_retry.py::test_build_concept_persists_augmented_blob` | ✅ 3 tests pass | **Partial.** Tests prove the namespace exists and the build function persists the blob; no test issues an actual HTTP POST. |
| 3 | POST `/etl/job` (jobType=llm-label) enters PENDING | None directly — relies on unchanged `i2b2_cdi.job.jobs.processRequestJob` | ✅ existing code path unchanged | **No.** Not directly tested. Inherits correctness from existing ML flow. |
| 4 | Status transitions PENDING → PROCESSING → COMPLETED | **None.** Documented in CHANGES.md as ⚠ deferred. | ❌ NOT PROVEN | **No.** Requires live jobWatcher + Postgres. Never executed end-to-end. |
| 5 | `observation_fact` contains one row per labeled patient | `test_engine.py::test_run_label_iterates_target_and_calls_send_facts` | ✅ passes | **Partial.** Asserts the DataFrame passed to `send_facts` is well-shaped; does not assert rows actually land in `observation_fact` (that uses the real `i2b2_cdi.fact.runner`, which is stubbed in tests). |
| 6 | `llm_audit` contains one row per provider call | `test_audit.py::test_audit_log_writes_one_row_full_mode`, `::test_audit_rows_written_counter_increments`, `test_build_and_retry.py::test_run_label_retries_on_schema_invalid_and_then_succeeds`, `::test_run_label_exhausts_writes_extra_exhausted_row` | ✅ 4 tests pass | **Yes** (against sqlite). The schema column names + insert sequence are exercised. PG-specific JSONB column behavior is not. |
| 7 | `job.output` JSON contains §2.7 summary stats | `test_engine.py::test_run_label_populates_summary_keys` | ✅ passes | **Yes** at the return-value level. Does not test that `BaseEngine.save_output` actually writes it to the `job` table (that path runs but uses the sqlite fake). |
| 8 | All unit tests pass with mocked provider; no real API calls in CI | `pytest tests/LLM/` → 129 passed | ✅ | **Yes.** Verified in this session. |

**Bottom line for Step 6:** 7/8 criteria have at least partial automated
coverage; criterion #4 is the only one with **zero** automated coverage and
no manual execution either. CHANGES.md §5 correctly marks it ⚠.

---

## B. Step 7 — Polish

### Sample files

```
sample_files/LLM/
├── README.md                          (real content, ~40 lines)
├── concept_extract_usecase.json       (36 lines, real JSON — but marked "Sprint 3+ placeholder" in description)
└── note_label_usecase.json            (44 lines, real JSON — the canonical Sprint 2 example)
```

- `note_label_usecase.json` — **real content**: full §2.5 blob schema with
  HF labeling example, all required fields (provider, schema, guardrails,
  sampling, date range, audit level), plus a `_comment_cache_prompt` hint.
- `concept_extract_usecase.json` — **real JSON that parses**, but
  describes the `llm-extract` use case which is itself a `NotImplementedError`
  stub. Useful as schema reference, not as a working payload.
- `README.md` — explains both files, workflow, and PHI considerations.

### LLM module README

`i2b2_cdi/LLM/README.md` **exists** (verified) and contains:
- ASCII architecture diagram showing POST → Flask Namespace → build → job
  → jobWatcher → llmEngine → dispatch → run_label → providers/validators/audit
- "Adding a new provider" instructions
- "Adding a new use case" instructions
- Pointer to LLM_MODULE_SPEC.md for the full reference

### Other READMEs

| File | Status |
|---|---|
| `tests/LLM/README.md` | ✅ exists, covers run command + live-PG procedure + how to add tests |
| `i2b2_cdi/LLM/prompts/README.md` | ✅ exists, covers Jinja2 conventions + how to add templates |
| `sample_files/LLM/README.md` | ✅ exists |

Step 7 is **fully covered**.

---

## C. Step 8 — CHANGES.md

### Exists at repo root?

**Yes.** `/Users/Vedhsai/i2b2-ml-project/CHANGES.md`, 13,461 bytes, committed.

### Section coverage (PLAYBOOK Step 8 required 8 sections)

| Step-8-prompt required section | CHANGES.md section | Present? |
|---|---|---|
| 1. Summary (1 paragraph) | §1 Summary | ✅ |
| 2. Files created (grouped) | §2 Files created | ✅ |
| 3. Files modified outside i2b2_cdi/LLM/ | §3 Files modified outside `i2b2_cdi/LLM/` | ✅ |
| 4. requirements.txt additions w/ justification | §3 includes the 4-line addition list with one-line justifications | ✅ |
| 5. D-N.N decisions with rationale | §8 Architectural decisions log | ✅ |
| 6. Assumptions to validate with Dr. W (§2.11 open questions) | §9 Open questions for Dr. Wagholikar | ✅ |
| 7. Known limitations (Sprint 3+) | §10 Known limitations | ✅ |
| 8. End-to-end install verification (5-step procedure) | §12 How to verify end-to-end install | ✅ (5 commands listed) |

Plus three sections beyond the Step-8 spec:
- §4 Test results
- §5 Acceptance-criteria → named-test mapping (this is what Step 6 was supposed to produce; it's here instead)
- §6 Per-provider exception translation table
- §7 Manual live-PG smoke procedure
- §11 Banked for post-Step-8 cleanup

**All 12 section headings (verbatim from CHANGES.md):**
```
## 1. Summary
## 2. Files created
## 3. Files modified outside `i2b2_cdi/LLM/`
## 4. Test results
## 5. Acceptance-criteria → named-test mapping (LLM_MODULE_SPEC §2.10)
## 6. Per-provider exception translation table (D-5.7)
## 7. Manual smoke procedure (live-PG, real providers)
## 8. Architectural decisions log (Steps 1-5 from DECISIONS.md, plus implementation pass)
## 9. Open questions for Dr. Wagholikar (LLM_MODULE_SPEC §2.11)
## 10. Known limitations (deferred to Sprint 3+ per LLM_MODULE_SPEC §2.9)
## 11. Banked for post-Step-8 cleanup
## 12. How to verify end-to-end install
```

Step 8 is **complete and exceeds the required scope**.

---

## D. Test suite truth check

### Command run

```bash
cd /Users/Vedhsai/i2b2-ml-project
source .venv/bin/activate
python -m pytest tests/LLM/ -v --tb=short
```

### Result

```
======================= 129 passed, 6 warnings in 0.47s ========================
```

- **Passed:** 129
- **Skipped:** 0
- **Failed:** 0
- **Collection errors:** 0
- **Warnings:** 6 (all the same: Flask-RESTX `body=` deprecation in
  `test_api.py`. Pre-existing convention; ML endpoints all use `body=`.
  D-3.6 says keep it. Not actionable in this scope.)

### Skipped tests

**None.** No `pytest.mark.skip`, `pytest.mark.skipif`, or `pytestmark = ...skip`
exists anywhere in `tests/LLM/`. Confirmed by:

```
$ grep -nr "pytest.mark" tests/LLM/*.py
(no matches except mark.parametrize which is not a skip)
```

### Failed tests

**None.**

### Hidden caveats worth noting

1. The Flask-RESTX namespace tests use a fresh `Flask()` + `Api()` and a
   tiny stub `@auth.verify_password` that always returns True. They prove
   the namespace builds and routes are reachable, **not** that the real
   loader's authentication path works against PM.
2. Real-provider tests stub the SDK modules via `monkeypatch.setitem(sys.modules, ...)`.
   They prove our exception-translation code dispatches on the right SDK
   exception class **names** — they do not prove field-name accuracy
   against the SDK's actual response objects at the pinned version.
3. The conftest's `_StubDataSource` raises AssertionError on `__enter__`,
   which means any test that forgets to monkey-patch `crc_ds` fails loudly.
   That safety net is itself untested but is exercised implicitly by all
   tests that use the `fake_crc` fixture.

---

## E. External dependencies

### Added to requirements.txt (verified by `git diff main..HEAD`)

```
+anthropic>=0.40.0
+openai>=1.40.0
+pytest>=8.0.0
+pytest-mock>=3.10.0
```

| Package | Pure Python? | Installable from PyPI? | System deps? | Verified installed in this session? |
|---|---|---|---|---|
| `anthropic>=0.40.0` | Yes | Yes | None | ✅ via `pip install anthropic` |
| `openai>=1.40.0` | Yes | Yes | None | ✅ via `pip install openai` |
| `pytest>=8.0.0` | Yes | Yes | None | ✅ pytest-9.0.3 installed |
| `pytest-mock>=3.10.0` | Yes | Yes | None | ✅ pytest-mock-3.15.1 installed |

All 4 are vanilla pip installs. No system-level dependencies required for the
unit-test path.

### Optional runtime deps NOT in requirements.txt (intentional)

| Package | Used by | Install command | Why not in requirements? |
|---|---|---|---|
| `transformers` | `providers/local_hf.py` | `pip install transformers` | Heavy (~150 MB); only needed if operator picks `local_hf` |
| `torch` | `providers/local_hf.py` | `pip install torch` | Heavy (~700 MB on Mac, GBs on CUDA); same reason |
| `accelerate` | `providers/local_hf.py` | `pip install accelerate` | Same |
| `bitsandbytes` | `providers/local_hf.py` (4-bit path) | `pip install bitsandbytes` | GPU-only; not buildable on Mac without CUDA |
| `sentencepiece` | tokenizers for some HF models | `pip install sentencepiece` | Same lazy rationale |
| `tabulate` | `i2b2_cdi.loader.app_helper` (existing code) | `pip install tabulate` | Pre-existing dep, also missing from upstream requirements.txt — needed for test_api.py to import the loader transitively |

The LocalHF provider raises a clear `RuntimeError` with the install command
when these are missing. **However**: `tabulate` is required for test_api.py
to pass and is NOT in requirements.txt or the test-deps install line in
[tests/LLM/README.md](tests/LLM/README.md). I installed it ad-hoc during
the smoke session. **This is a documentation gap.**

### System-level dependencies flagged

| Tool | Used for | Installed on this machine? |
|---|---|---|
| Docker | live-PG smoke, full i2b2-etl run | **NO** (`which docker` → not found) |
| Postgres client libs (`libpq`) | psycopg2 production import path | Likely yes (anaconda ships it); psycopg2 itself is stubbed in tests so not needed for the test suite |
| CUDA toolkit | LocalHF 4-bit or fp16 GPU path | **NO** (`torch.cuda.is_available() → False`) |
| `pyodbc` ODBC drivers | MSSQL production import path | Stubbed in tests; only needed if `CRC_DB_TYPE=mssql` |

---

## F. Environmental assumptions

### Environment variables read by the LLM module

Discovered via `grep -rn "os.environ" i2b2_cdi/LLM/`:

| Variable | Used in | Required? | Default |
|---|---|---|---|
| `CRC_DB_TYPE` | `apply_LLM.py:45,78`, `audit.py:94`, `perform_LLM.py:75` | No | `"pg"` (via `.get(..., "pg")`) |
| `CRC_DB_NAME` | `concept_API.py:44` | Yes IF X-Project-Name header is `'Demo'` | none (`os.environ["..."]` raises KeyError) |
| `ONT_DB_NAME` | `concept_API.py:45` | Yes IF X-Project-Name header is `'Demo'` | none |

Plus the inherited env vars used by `BaseEngine` / `jobOrchestrator` /
`jobWatcher` (NOT changed by this work, but the module fails without them
in a real deployment):
- `CRC_DB_HOST`, `CRC_DB_PORT`, `CRC_DB_USER`, `CRC_DB_PASS`
- `ONT_DB_HOST`, `ONT_DB_PORT`, `ONT_DB_USER`, `ONT_DB_PASS`
- `PARENT_NAME`, `PARENT_IP`, `EXCLUDE_JOB_EXECUTION`
- `ENABLE_PATIENT_FACT`, `INSTITUTION_NAME`, `INSTITUTION_LOGO_URL`

The test conftest sets `CRC_DB_TYPE=pg`, `CRC_DB_NAME=i2b2demodata`,
`ONT_DB_NAME=i2b2metadata`, `ENABLE_PATIENT_FACT=True` via
`os.environ.setdefault`, so tests don't need them in the shell.

### External services the module assumes

| Service | Used by | Default URL | Required? |
|---|---|---|---|
| **Postgres** (or MSSQL) — `concept_dimension`, `observation_fact`, `job`, `llm_audit` tables | `apply_LLM`, `audit`, `perform_LLM`, `concept_API` | localhost (via `CRC_DB_HOST`) | Yes, in production |
| **Ollama server** | `OllamaProvider` | `http://localhost:11434` | Only if `blob.provider.name == "ollama"` |
| **Anthropic API** (`api.anthropic.com`) | `AnthropicProvider` | per SDK default | Only if `blob.provider.name == "anthropic"` AND `external_provider: true` |
| **HuggingFace Hub** (`huggingface.co`) | `LocalHFProvider` first load | per SDK default | Only on first model download; afterwards reads from `~/.cache/huggingface/` |
| **OpenAI-compatible endpoint** | `OpenAICompatibleProvider` | required at construction | Only if `blob.provider.name == "openai_compatible"` |
| **`concept.runner.mod_run`** and **`fact.runner.mod_run`** | `concept_API`, `BaseEngine.send_facts` | in-process | Yes — these transitively need Postgres + the i2b2 schema |

### Hardcoded filesystem paths

Discovered via `grep -rn "/usr/src/app\|/tmp/" i2b2_cdi/LLM/`:

| Path | Where | Exists on this Mac? | Notes |
|---|---|---|---|
| `/usr/src/app/tmp/{dfstring}` | `concept_API.py:108, 115` | **NO** | Container-internal path. Inherited from `ML/concept_API.py` convention. Will fail outside Docker. |
| `/usr/src/app/tmp/{ClassName}/output/llm_{ClassName}_facts.csv` | `i2b2_cdi/job/BaseEngine.py:60-62` (NOT changed by us; inherited) | **NO** | Same — container-only path the LLM module relies on inherited `send_facts`. |

These are not a regression — both inherited from the existing ML module's
convention. But the LLM module cannot run end-to-end outside the Docker
container without overriding these. No env-var fallback exists.

---

## Honest gaps summary

Things that are **not done** that the spec or playbook calls for:

1. **Step 6 live-PG smoke** — no Docker installed, no `live_pg` pytest marker,
   no real PG transactions ever observed. Manual procedure documented only.
2. **Acceptance criterion #4** (status transitions PENDING→PROCESSING→COMPLETED) —
   zero coverage; relies on inherited `jobOrchestrator` code that we did not
   exercise end-to-end.
3. **`tabulate` install gap** — required to run `test_api.py` but not in
   requirements.txt and not in the README's test-deps install command. I
   installed it ad-hoc; a fresh checkout following the README would hit a
   `ModuleNotFoundError` from the loader's transitive import.
4. **Real-provider validation** — exception-translation tests stub SDK
   modules. No call has hit `api.anthropic.com`, no real Ollama server, no
   real OpenAI-compatible endpoint. LocalHF was the only provider exercised
   live (with Qwen-0.5B on Mac CPU).
5. **`llm-extract` / `llm-feature`** — explicit `NotImplementedError` stubs
   per §2.9 (intentional, but worth naming).
6. **Hardcoded container paths** — `/usr/src/app/tmp/...` in `concept_API.py`
   means the module cannot run outside Docker without overrides.
7. **Migrations never applied** — both `100_llm_audit.sql` files exist but
   have never been run against a real DB.

Things that **are done** that the audit confirms:

- 38 files created under the four required directories
- 129 unit tests pass (sqlite + stubbed SDKs, mock provider)
- Glob auto-discovery picks up `llmEngine.py` + `runner.py`
- Flask-RESTX namespace registers and Swagger doc lists "LLM Concepts"
- Live LocalHF Qwen-0.5B end-to-end ran: prompt → generate → coerce → schema → guardrail (and caught a real prompt-template bug, which was fixed in commit `fe4b549`)
- CHANGES.md covers all 8 Step-8-required sections and 4 more
- Loader edit is exactly the 2 lines specified in D-3.2
- Requirements diff is exactly 4 lines, all pure-python
- All 4 README files exist with real content

---

## Resolutions (added 2026-05-27, post-audit gap-closure pass)

This section documents which of the 7 gaps named above were addressed
after the audit was filed, with commit references.

### Fixed

| Gap # | Audit claim | Actual fix | Commit |
|---|---|---|---|
| **1** | "tabulate missing from requirements.txt + README" | **Audit was partially wrong.** `tabulate==0.9.0` is at line 156 of upstream `requirements.txt` (since v4.1.0). The conftest also stubs `tabulate` so pytest doesn't need the real package. The actual gap was the minimal `pip install ...` line in `tests/LLM/README.md` not listing it — which breaks anyone following that line without also running `pip install -r requirements.txt`. Added `tabulate` to the README install line and added a 9-line "Note on `tabulate`" explaining the two non-pytest workflows that need the real package. | `df078fe` |
| **2** | "live_pg pytest marker was never implemented" | Registered `live_pg` marker in `pyproject.toml [tool.pytest.ini_options]`. Added `pytest_collection_modifyitems` hook in `tests/LLM/conftest.py` that **deselects** (not skips) `live_pg`-marked items when either `RUN_LIVE_PG != "1"` or `docker` is missing from PATH. Created `tests/LLM/test_live_pg.py` with three meaningful smoke bodies (audit-table-schema check, jobOrchestrator glob discovery, full PENDING→PROCESSING→COMPLETED end-to-end with MockProvider). Verified locally without Docker: `pytest tests/LLM/` → "129 passed, 3 deselected"; `pytest -m live_pg` → "132 deselected / 0 selected". | `58db416` |
| **3** | "Hardcoded `/usr/src/app/tmp/...` paths in `concept_API.py:108,115` make the module Docker-only" | Added §10.1 "Hardcoded container-internal filesystem paths" to `CHANGES.md`, naming the exact files+lines, noting the LLM module inherits the convention from `i2b2_cdi/ML/concept_API.py`, and sketching a follow-up PR design (introduce `I2B2_TMP_DIR` env var in `i2b2_cdi.common.utils`, retrofit ML + LLM + `BaseEngine`). No code paths were changed — out-of-scope for the LLM-only PR. | `d0104eb` |

### Intentionally deferred (not addressed in this pass)

| Gap # | Why deferred |
|---|---|
| **4** | **Real-provider validation.** Requires API keys (Anthropic), running services (Ollama daemon, an OpenAI-compatible endpoint), and either a real GPU or willingness to run 7B+ inference on Mac CPU. None of these are appropriate to set up from the orchestrator's perspective. LocalHF was the only provider exercised live (Qwen-0.5B during the smoke session). Real-provider validation should happen on Discovery (Dartmouth cluster) per the ResearchOS rules, not on this Mac. |
| **5** | **Migrations never applied.** Requires a running Postgres instance, which requires Docker, which is not installed on this machine. The `live_pg` test suite added in GAP 2 is the right vehicle to validate the migration end-to-end — but actually running it is gated on the operator (Vedhsai) bringing up Docker + applying the migration. Procedure is documented in `CHANGES.md` §7. |

### Test suite truth after resolutions

```
$ pytest tests/LLM/
================ 129 passed, 3 deselected, 6 warnings in 0.54s =================

$ pytest tests/LLM/ -m live_pg
=========================== 132 deselected in 0.30s ============================

$ pytest --markers | grep live_pg
@pytest.mark.live_pg: end-to-end smoke against a real Postgres + jobWatcher.
  Requires RUN_LIVE_PG=1 and a working Docker install. Auto-deselected otherwise.
```

- **Passed:** 129 (unchanged from pre-resolution)
- **Deselected:** 3 (the new `live_pg` tests, by design)
- **Skipped:** 0
- **Failed:** 0
- **Warnings:** 6 (all pre-existing flask-restx `body=` deprecations; D-3.6)

### Branch state after resolutions

```
$ git log --oneline feature/llm-module ^main
d0104eb docs(CHANGES): document /usr/src/app/tmp hardcoded paths as known limit
58db416 test(live_pg): register marker + auto-deselect when prerequisites unmet
df078fe docs(tests): note tabulate requirement for non-pytest workflows
fe4b549 Fix prompt-primer fragility on small models; add regression test
1122c9b Add i2b2_cdi/LLM module — Track C: LLM integration
```

Five commits total on `feature/llm-module`: the implementation +
prompt-fix + three audit-resolution commits.
