# SELF_REVIEW.md — Pre-Kavi audit pass

**Date:** 2026-05-27
**Branch:** `feature/llm-module` (7 commits ahead of `main`)
**Auditor:** Claude (self-audit; no code changes made)
**Test state at audit time:** 129 unit passed + 3 live_pg passed = 132/0/0 (verified)

This review reads every `.py` and `.md` written for this module, classifies
findings by severity, and reports honestly. No code was modified during this
pass. Where I cut a corner, I flagged it.

---

## CRITICAL findings (must fix before showing Kavi)

**None.** Nothing in the module will cause data loss, silent corruption, or
security compromise as currently used. The "must fix" bar is empty.

---

## HIGH findings (should fix before showing Kavi)

### H-1. `bool("false")` is `True` — opt-in gate bypassable by string

**Where:** `i2b2_cdi/LLM/providers/__init__.py:136`
```python
opt_in = bool(provider_config.get("external_provider", False))
```

**Problem:** Python's `bool("false")` returns `True` (any non-empty string is
truthy). A misconfigured blob with `"external_provider": "false"` would
*bypass* the PHI-leaves-Docker gate and silently allow external API calls.
Confirmed in this audit by running `python -c 'print(bool("false"))'` → `True`.
Same applies to `"no"`, `"0"`, etc.

**Suggested fix (do NOT implement here):** Replace with explicit boolean check:
`opt_in = provider_config.get("external_provider") is True`. Or convert with
explicit string handling: accept `True`, `"true"`, `"True"`, `True`; reject
everything else.

**Why it matters:** Concept blobs are user-authored JSON. If a researcher
writes `"external_provider": "false"` in a config (a natural typo for someone
not familiar with JSON booleans), they would trigger an external API call
with PHI they thought was protected. This is the only safety gate between
clinical text and the Anthropic API.

### H-2. `llm_audit.job_id` missing the FK to `job(id)` specified in the SPEC

**Where:** `deployment/pg/100_llm_audit.sql:8`, `deployment/mssql/100_llm_audit.sql:9`

**Problem:** `LLM_MODULE_SPEC.md §2.6` declares the column as:
```sql
job_id BIGINT NOT NULL REFERENCES job(id),
```
Both migrations declare it as `BIGINT NOT NULL` but **omit** `REFERENCES job(id)`.
Schema drift from the spec.

**Suggested fix:** Add `REFERENCES job(id)` to both DDLs, with `ON DELETE CASCADE`
or `ON DELETE SET NULL` per Dr. W's preference. Add a separate migration file
(`110_llm_audit_fk.sql`) so existing deployments can opt in.

**Why it matters:** Without the FK, you can have audit rows orphaned from
deleted jobs, breaking the reproducibility story the audit table exists for.
A reviewer might check the spec compliance and ding this on first read.

### H-3. LocalHFProvider uses raw `pipeline("text-generation")` instead of chat templates

**Where:** `i2b2_cdi/LLM/providers/local_hf.py:103-108`
```python
self._pipeline = pipeline(
    "text-generation",
    model=model_obj,
    tokenizer=tokenizer,
    device_map=None if not use_gpu else self.device_map,
)
```

**Problem:** The default `model` is `meta-llama/Meta-Llama-3-8B-Instruct` —
an instruction-tuned chat model. These models expect a structured chat
template (system/user/assistant turns) and produce significantly worse output
when given raw text continuation. Our prompt is passed as a single raw string
to a text-generation pipeline.

**Suggested fix:** Detect chat-tuned models (or accept a `chat_format: true`
flag in `provider` config) and use `pipe(prompt, ...)` only after rendering
via `tokenizer.apply_chat_template([{"role": "user", "content": prompt}], ...)`.

**Why it matters:** If anyone benchmarks this provider against Anthropic for
the paper, the LocalHF numbers will be artificially low. The Qwen-0.5B smoke
worked in spite of this because Qwen is small and lenient; an 8B instruct
run on MIMIC would show degraded labeling quality. This affects the
paper's defensibility.

### H-4. `apply_LLM._today()` is clinically wrong for time-series labels

**Where:** `i2b2_cdi/LLM/apply_LLM.py:288-294, 317-318`
```python
fact_rows.append({
    "mrn": patient_num, "code": conceptCode,
    "start-date": _today(), "value": label_int,
})
```

**Problem:** Every labeled patient gets the current wall-clock date as the
fact's `start_date`. This ignores the temporal-data-leakage concern the i2b2
paper is built around (`time_buffer`, prediction event date). For a real
clinical workflow, the label should be tied to a prediction event date
(visit, admission, etc.), not "today". The existing ML code in `ml_API.py:225`
uses `'1970-01-01 00:00:00'` as a sentinel for the same reason.

**Suggested fix:** Pull `prediction_event_path` from `concept_blob` (already
in the spec §2.5), resolve it per patient to a real event date, and use that
as `start_date`. Apply `time_buffer` (in days, per the upstream code
convention — note that the paper says seconds, see KAVI_CHECKLIST §"Bugs
found"). For now, document explicitly that labels are pinned to job-run
time; warn that downstream temporal queries will be misleading.

**Why it matters:** A reviewer looking at the resulting `observation_fact`
table will see every label dated today regardless of when the underlying
notes were written. That breaks the data-leakage story the paper sells.
Documentation alone could close this, but the code should at least accept
an event-date input.

---

## MEDIUM findings (worth fixing but not blocking)

### M-1. `LLM_ENABLE_MOCK_PROVIDER` imports test code into production

**Where:** `i2b2_cdi/LLM/providers/__init__.py:155-167`

**Problem:** The opt-in env-var path does `from tests.LLM.fixtures.mock_provider
import MockProvider`. This is a production module reaching INTO the test tree.
If `tests/` isn't on the import path (typical of production deploys), the
`try/except ImportError` silently logs a warning and continues. But the
production code now formally depends on test-tree structure.

**Suggested fix:** Move `MockProvider` (or a slim production-compatible
shim) into `i2b2_cdi/LLM/providers/_test_helpers.py`. Keep it out of the
default registry; the env var path then imports from production code,
not tests.

**Why it matters:** Future refactors of `tests/` could silently disable
the live-PG acceptance smoke. Also a soft architectural smell that a
careful reviewer (Kavi) will spot.

### M-2. `OpenAICompatibleProvider` accepts but silently drops `output_schema`

**Where:** `i2b2_cdi/LLM/providers/openai_compatible.py:73`

**Problem:** The `generate()` signature accepts `output_schema: Optional[Dict]`
but doesn't pass it to the OpenAI SDK. Real OpenAI / vLLM accept
`response_format={"type": "json_object"}` or
`response_format={"type": "json_schema", ...}` for structured output. The
Ollama provider DOES use this (sets `format: "json"`). Anthropic doesn't have
a structured-output mode in this code but its prompt template includes XML
tags. Only OpenAI-compat is inconsistent.

**Suggested fix:** When `output_schema is not None`, pass
`response_format={"type": "json_object"}` to the SDK call. Optionally pass
the full schema for vLLM's JSON-schema constrained decoding.

**Why it matters:** Operators who switch to OpenAI-compat from Ollama and
notice degraded JSON quality will be confused — they explicitly set an
`output_schema` in the blob, expecting it to do something.

### M-3. Anthropic has hardcoded system prompt; OpenAI/Ollama have none

**Where:** `i2b2_cdi/LLM/providers/anthropic.py:80-83`

**Problem:** Anthropic's `generate()` includes a system prompt:
`"You are a careful clinical assistant. When asked for structured output,
return the JSON object inside <json>...</json> tags."` That's hardcoded
and unconfigurable. The other three providers don't set a system prompt
at all. Cross-provider output drift even with identical prompts/templates
is inevitable.

**Suggested fix:** Make `system_prompt` an optional field in the blob's
`provider` config. Default to None across the board (use only the template).
If set, every provider that supports system-role messages applies it.

**Why it matters:** Paper benchmarking across providers will produce
non-comparable numbers because the system context differs. Reviewers
comparing rows in your results table will notice.

### M-4. Note ordering in `_fetch_notes_for_patient` is non-deterministic

**Where:** `i2b2_cdi/LLM/apply_LLM.py:70-116`

**Problem:** The SQL is `SELECT observation_blob FROM observation_fact
WHERE patient_num = %(p)s ...` with no `ORDER BY`. Result row order is
PostgreSQL-implementation-dependent (often insertion order but not guaranteed).
For a patient with multiple notes, identical inputs could produce different
concatenations across runs — breaking the reproducibility claim from CHANGES.md.

**Suggested fix:** Add `ORDER BY start_date, encounter_num` to both SQL
branches. Document the ordering in the docstring.

**Why it matters:** Direct contradiction with the audit/prompt-hash story.
Two runs against the same data could produce different `prompt_hash` values
in `llm_audit` for the same patient.

### M-5. Audit logger opens a new cursor per `log()` call

**Where:** `i2b2_cdi/LLM/audit.py:95-128`

**Problem:** `with self.crc_ds as cursor:` opens a fresh connection for each
audit row. For a 1000-patient cohort, that's 1000 connections (assuming
each `log()` succeeds). PG's `max_connections` default is 100; we'd
exhaust the pool. The i2b2 connection layer might use connection pooling
underneath, but we don't know.

**Suggested fix:** Either keep a long-lived cursor across `log()` calls
(threading model permitting) or batch audit rows with periodic flushes
(every N rows or end-of-job). Batch flush also simplifies the sidecar
failure story.

**Why it matters:** Will surface as DB connection failures on the first
real MIMIC-scale run. Hard to debug post-hoc without enabling PG-level
connection logging.

### M-6. `perform_LLM` health_check is a no-op for Anthropic

**Where:** `i2b2_cdi/LLM/perform_LLM.py:56-59`, `providers/anthropic.py:142-148`

**Problem:** `AnthropicProvider.health_check()` does `self._get_client()`
and returns True if the client constructs. It does NOT make a network
call. So `build_llm_concept` will report a healthy Anthropic provider
even if the API key is invalid or network is down.

**Suggested fix:** Make health_check optionally ping a cheap endpoint
(Anthropic has no dedicated health endpoint, but a tiny `messages.create`
with max_tokens=1 would do — costs ~$0.0001). Gate behind a
`provider.deep_health_check: true` flag to avoid spending money on every
build call.

**Why it matters:** Operators get a false sense of validation at
concept-build time. The first patient's job will fail with a credential
error instead of failing fast at build.

### M-7. `concept_API.processRequest_build_llm_concept` leaks internal errors

**Where:** `i2b2_cdi/LLM/concept_API.py:75-76`
```python
except Exception as err:
    return _exception_response(err)
```

**Problem:** The catch-all returns the exception via `_exception_response`,
which (per the upstream loader convention) puts the exception's `str()` in
the HTTP response body. A SQL syntax error, a stack-trace fragment, or
internal path could be leaked to an unauthenticated caller.

**Suggested fix:** Log the full exception with `logger.exception(...)` and
return a generic message. The upstream `_exception_response` is used
elsewhere in i2b2 too, so this is partly a project-wide pattern issue —
flag for Dr. W rather than just patching here.

**Why it matters:** Low impact (the endpoint requires DATA_AUTHOR auth)
but standard info-disclosure hygiene. Easy fix.

### M-8. SQL queries in audit.py and apply_LLM.py are unqualified

**Where:** `i2b2_cdi/LLM/audit.py:98-110`, `apply_LLM.py:49-64, 82-112`,
`perform_LLM.py:79-89`

**Problem:** All our SQL uses unqualified table names (`INSERT INTO
llm_audit`, `SELECT ... FROM observation_fact`). This works only because
the PG user's `search_path` includes `i2b2demodata`. On the bundled i2b2-pg
seed image, that's NOT the default — the live-PG smoke had to run
`ALTER USER i2b2 SET search_path = i2b2demodata, public` as a workaround
(documented in CHANGES.md §6.5). This means a fresh deploy without that
ALTER would silently log audit-write failures every patient and silently
fail to find notes.

**Suggested fix:** Either (a) qualify SQL with `os.environ['CRC_DB_NAME']`
prefix matching the existing jobs.py convention, OR (b) call `SET search_path`
at the start of each cursor session. Option (a) matches existing convention
but is more verbose.

**Why it matters:** The live-PG smoke worked because we manually set
search_path. A reviewer trying to reproduce on a fresh stack will hit
silent failures. This is a direct contradiction with the reproducibility
receipt in CHANGES.md.

### M-9. `LocalHFProvider` ignores `timeout_s`

**Where:** `i2b2_cdi/LLM/providers/local_hf.py:119, 129`

**Problem:** `generate()` accepts `timeout_s` but the transformers
`pipeline(prompt, ...)` call has no built-in timeout. If the model hangs
(rare but possible), the entire job hangs forever. No watcher-level timeout
either.

**Suggested fix:** Run inference inside a `concurrent.futures.ThreadPoolExecutor`
with a timeout, OR document explicitly that `timeout_s` is provider-honored
only for Anthropic/OpenAI/Ollama (where the SDK does it) and not for LocalHF.

**Why it matters:** A stuck job daemon could halt the entire LLM pipeline.

### M-10. `LocalHFProvider` doesn't probe for Apple Silicon MPS

**Where:** `i2b2_cdi/LLM/providers/local_hf.py:68`
```python
use_gpu = (not self.force_cpu) and torch.cuda.is_available()
```

**Problem:** Only checks CUDA. On Mac M-series with PyTorch MPS available,
falls through to fp32 CPU. This was observed during the Qwen-0.5B smoke
(see CHANGES.md): `load_mode: fp32-cpu` even though MPS was available.
For larger models on Mac (e.g. running on Vedhsai's laptop for dev), this
is a 5-10x slowdown.

**Suggested fix:** Add `torch.backends.mps.is_available()` to the GPU
detection and pass `device_map="mps"` accordingly.

**Why it matters:** Affects dev velocity. Not a production concern since
production runs on Discovery.

### M-11. `live_pg` test deletes `/MIMIC/notes/discharge` concept on cleanup

**Where:** `tests/LLM/test_live_pg.py:185-190`

**Problem:** The idempotent cleanup runs `DELETE FROM concept_dimension
WHERE concept_path IN ('/LLM/Diagnosis/LIVE_PG_HF', '/cohort/demo',
'/MIMIC/notes/discharge')`. The first two are test-owned. The third
(`/MIMIC/notes/discharge`) is a legitimate i2b2 concept path that real
MIMIC ingest pipelines would use. Running this test on a stack with real
MIMIC data loaded would delete that concept node.

**Suggested fix:** Use a test-prefixed path like `/LIVE_PG_TEST/MIMIC/notes/discharge`
and never touch real `/MIMIC/*` paths.

**Why it matters:** Destructive test against any real-data deployment.
Limited blast radius (just the concept_dimension row) but bad hygiene.

### M-12. MSSQL migration partial-state non-idempotent

**Where:** `deployment/mssql/100_llm_audit.sql:5-30`

**Problem:** The `IF NOT EXISTS (SELECT 1 FROM sysobjects WHERE name =
'llm_audit') BEGIN CREATE TABLE...; CREATE INDEX...; END;` block is gated
on the TABLE existing. If someone created the table manually without the
indexes (e.g. partial restore from backup), the migration would skip the
table check AND skip the index creation, leaving the table without indexes.

**Suggested fix:** Split into two separate `IF NOT EXISTS` checks: one
for the table, one for each index (`IF NOT EXISTS (SELECT 1 FROM sys.indexes
WHERE name = 'idx_llm_audit_job')`).

**Why it matters:** Production deployments do weird things with partial
state. Easy to fix, hard to debug later.

### M-13. `MSSQL parsed_output NVARCHAR(MAX)` vs PG `JSONB` — semantic mismatch

**Where:** PG migration line 16 vs MSSQL migration line 17

**Problem:** PG uses `JSONB` (binary JSON, queryable with `->`, `->>`,
`jsonb_path_query`, etc., with type validation at insert). MSSQL uses
`NVARCHAR(MAX)` (opaque text, queryable with `JSON_VALUE` but no type
enforcement). A reviewer comparing the two won't get equivalent semantics.

**Suggested fix:** Document the difference in CHANGES.md. If on
SQL Server 2025+, use the new `JSON` type. Otherwise, add a `CHECK
(ISJSON(parsed_output)=1)` constraint to give weaker but real type validation.

**Why it matters:** Mostly affects research queries against the audit
table. Won't break anything but the PG/MSSQL parity story isn't fully true.

### M-14. `_one_attempt` closure inside per-patient for-loop

**Where:** `i2b2_cdi/LLM/apply_LLM.py:179-217`

**Problem:** The closure captures `prompt`, `prompt_hash`, `patient_num`,
etc. from the outer scope by REFERENCE. Currently the for-loop is sequential,
so this works. If anyone parallelizes the per-patient loop (a natural
optimization), the closure would see whichever `patient_num` happened to
be in the variable at the time of the closure call — classic Python
closure-in-loop bug.

**Suggested fix:** Move `_one_attempt` to a module-level function taking
patient context as args, or bind via default-arg trick (`def _one(p=patient_num, pr=prompt): ...`).

**Why it matters:** Works correctly now; will silently break the first
time someone introduces concurrency. Add a comment OR refactor.

---

## LOW findings (nice-to-have)

### L-1. `n_failed_validation` counts provider errors too

**Where:** `apply_LLM.py:247-268`

The TimeoutError/ConnectionError except block increments `n_failed_validation`.
Misleading name — these aren't validation failures, they're provider failures.
Add `n_failed_provider` to the summary OR rename the field.

### L-2. Duplicate audit-log code in the two except branches

**Where:** `apply_LLM.py:225-268`

The RetryableValidationError and TimeoutError/ConnectionError branches each
write an identical "exhausted" audit row with the same kwargs (only `e` differs).
DRY violation. Extract a helper.

### L-3. Tokenizer-exception swallowed with `pass`

**Where:** `i2b2_cdi/LLM/llm_helper.py:74-77`
```python
try:
    return len(tokenizer.encode(text))
except Exception:
    pass
return max(1, len(text) // 4)
```

Falls back to char proxy silently. At least log a debug-level note so the
operator knows their tokenizer isn't being used.

### L-4. `apply_LLM` silently drops malformed confidence values

**Where:** `apply_LLM.py:281-286`

If the LLM returns `"confidence": "high"`, the `float()` raises `ValueError`,
caught with `pass`, confidence dropped from the mean but the label is still
counted. Could mask data-quality issues. Log a warning at minimum.

### L-5. `test_dispatch_routes_bare_llm` is too weak

**Where:** `tests/LLM/test_engine.py:101-114`

Asserts only `isinstance(out, dict)`. A function that returned `{}` would
pass. Make it match `test_dispatch_routes_llm_label` by asserting on
expected keys.

### L-6. `HallucinationGuard.max_retries` lives in the wrong config namespace

**Where:** `validators/hallucination_guard.py:46`

`max_retries` is a retry-system concern, not a guardrail concern. It's
read from `guardrails` config but used in `apply_LLM.py:147`. Putting it
inside the `guardrails` namespace is confusing for the JSON-blob author.

### L-7. `HallucinationGuard` evidence check has no max-length validation

**Where:** `validators/hallucination_guard.py:70-83`

An LLM could "match" the substring requirement by quoting the entire note
verbatim. A real evidence quote should be short. Add a configurable
`max_evidence_length`.

### L-8. Defaults to "unknown" provider/model names hide constructor bugs

**Where:** `apply_LLM.py:176-177`
```python
provider_name = getattr(provider, "name", "unknown")
model_name = getattr(provider, "model", "unknown")
```

If someone instantiates a provider without setting `name`/`model`, audit
rows get `"unknown"`. Better: raise at provider construction if either is
empty.

### L-9. `OpenAICompatibleProvider` lacks `max_retries` arg (Anthropic has it)

**Where:** `providers/openai_compatible.py:36-54`

`AnthropicProvider.__init__` takes `max_retries=0`; OpenAI-compat does not.
Inconsistent. Either both have it or neither.

### L-10. Ollama `timeout_s` serves double duty (connect + read + generate)

**Where:** `providers/ollama.py:65`

`urlopen(req, timeout=timeout_s)` is the socket read timeout. For slow local
models that take 2+ minutes to generate, default `timeout_s=60` is too short.
Document or separate connect/read timeouts.

### L-11. No `Retry-After` header handling

**Where:** All providers

When a 429 rate-limit comes back, our `retry_with_backoff` uses pure
exponential backoff. The SDK's recommended approach is to honor the
`Retry-After` header. Implement on a follow-up pass if/when the paper
starts running at MIMIC scale.

### L-12. `LocalHFProvider` reports zero token usage

**Where:** `providers/local_hf.py:134-138`

Hardcoded `usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}`.
Could be computed via `tokenizer.encode(prompt)` and `tokenizer.encode(text)`.
Affects `llm_audit` reporting.

### L-13. `test_live_pg` 45s deadline is tight on arm64 emulation

**Where:** `tests/LLM/test_live_pg.py:233`

Watcher polls every 10s + ~5s execution = ~15s normally, plenty of margin.
But arm64 emulation can run 2-3x slower, sometimes hitting 30+s. Could be
flaky on a slow CI runner.

### L-14. `test_live_pg` inserts notes with literal `%%`

**Where:** `tests/LLM/test_live_pg.py:218`
```python
(pn, "patient {} note: EF 30%% BNP 1800".format(pn)),
```

`format()` only substitutes `{}`. The `%%` is NOT escaping anything in this
context — psycopg2 doesn't process `%` inside parameter values. The stored
string contains literal `"EF 30%%"` rather than `"EF 30%"`. The test still
passes because it doesn't check note content, but the seeded data is wrong.

### L-15. `test_run_label_exhausts_writes_extra_exhausted_row` is loose

**Where:** `tests/LLM/test_build_and_retry.py:170-176`

Asserts `"exhausted" in outcomes` (any position). Doesn't check the count
of attempt rows vs exhausted rows. With max_retries=1, expected = 2 attempt
rows + 1 exhausted = 3 total. Could strengthen by asserting exact counts.

### L-16. `_FENCE_RE` regex is non-greedy on nested JSON

**Where:** `validators/structured_output.py:29`

`\{[\s\S]*?\}` stops at the first `}`. For `{"a": {"b": 1}}` inside a fence,
it captures `{"a": {"b": 1}` which fails parse → falls through to
widest-brace-block fallback, which succeeds. So net behavior is correct
but goes through an extra fallback. Could fix the regex to be brace-balanced.

### L-17. `request.data` mutation in `llm_apply_model` is unusual

**Where:** `i2b2_cdi/LLM/llm_API.py:96`
```python
request.data = json.dumps(payload).encode("UTF-8")
```

This mutates the Flask global request object. I confirmed (in this audit)
that Flask 3.x allows it via test_request_context, but it's a non-idiomatic
pattern. The endpoint is redundant anyway — operators can POST directly to
`/etl/job` with `jobType=llm-label`.

---

## NITS (typos, formatting, dead code)

### N-1. Unused imports (5 in production code)

Confirmed via pyflakes:
- `i2b2_cdi/LLM/llm_API.py:20` — `jsonify`, `make_response` unused
- `i2b2_cdi/LLM/llm_helper.py:20,23` — `logging`, `Iterable` unused
- `i2b2_cdi/LLM/concept_API.py:25` — `I2b2metaDataSource` unused

### N-2. Dead variable `last_exc` in `retry_with_backoff`

**Where:** `i2b2_cdi/LLM/llm_helper.py:167, 172` — assigned but never used.

### N-3. Return type `-> any` (lowercase) instead of `-> Any`

**Where:** `i2b2_cdi/LLM/llm_helper.py:145`. `any` is the builtin function;
should be `typing.Any`. Python accepts it but it's incorrect typing.

### N-4. `LLMResponse.parsed` field is unused

**Where:** `i2b2_cdi/LLM/providers/base.py:29`

Defined on the response model, but never populated — `coerce_text_to_dict`
is always called separately. Either remove the field or have providers
populate it.

### N-5. `import re` inside `_split_sentences`

**Where:** `i2b2_cdi/LLM/llm_helper.py:82`

Standard imports belong at module top. Move it.

### N-6. `LocalHFProvider._load_mode = self._load_mode or "fp16-gpu"`

**Where:** `providers/local_hf.py:90`

`self._load_mode` is None at that point (already reset before the branch).
The `or` is dead. Should just be `self._load_mode = "fp16-gpu"`.

### N-7. Concept-loader filename uses colons

**Where:** `i2b2_cdi/LLM/concept_API.py:95` — `dfstring = now.strftime("%d-%m-%Y_%H:%M:%S%f")`

Colons in filenames are illegal on Windows. We're not a Windows tool but
matches the existing ML convention so leaving it. Worth noting.

### N-8. `MockProvider` registration in `test_live_pg_full_label` is redundant

**Where:** `tests/LLM/test_live_pg.py:154`

The container has `LLM_ENABLE_MOCK_PROVIDER=1` and registers MockProvider
in its own Python process via `providers/__init__.py`. The test's
host-process registration doesn't reach the container. Harmless but
misleading — implies the test's registration matters.

### N-9. `Flask` test imports in test_api.py use `pytest.importorskip`

**Where:** `tests/LLM/test_api.py:5-6`

Documented practice but flask/flask-restx are required deps. Could be
plain imports.

---

## What I verified is solid (the positive column)

- **132 tests pass, 0 failed, 0 skipped** with `RUN_LIVE_PG=1`. Unit-only
  is 129 + 3 deselected. Numbers match the README and CHANGES.md claims.
- **Provider exception translation contract** (D-5.7 table) is consistent
  across all 4 providers. Each translates SDK errors per the documented
  table; I traced each line.
- **Registry invariant** (`LOCAL ∩ EXTERNAL = ∅`, every entry belongs to
  exactly one set matching `cls.is_external`) is checked at import time
  and after every register/unregister. Tests forge inconsistencies and
  verify the assertion catches them.
- **Audit logger D-4.3 sidecar pattern**: DB failure logs and returns
  False, never raises. Verified in `test_audit.py::test_audit_log_db_failure_does_not_raise`.
- **`SchemaValidator.__init__` runs `Draft7Validator.check_schema`** — bad
  schemas fail at concept-build time, not at 2 AM. Verified in
  `test_validators.py::test_schema_validator_bad_schema_raises_at_init`.
- **HallucinationGuard case-insensitive by default** (D-4.6) — verified
  explicitly by `test_guard_evidence_substring_case_insensitive_default`
  and the opt-in `case_sensitive_evidence: true` path.
- **Anthropic default model is `claude-sonnet-4-5`** — not the non-existent
  `claude-opus-4-7`, not `claude-opus-4-5`. Verified at the module-level
  constant and in `test_real_providers.py`.
- **`cost_usd = 0.0` for ALL providers** — verified explicitly per provider.
- **Anthropic prompt caching default OFF** — verified by both the
  constructor default and a dedicated test.
- **Live-PG smoke** ran end-to-end on real Docker + Postgres today.
  Status transitions, audit rows, observation_fact rows, and `job.output`
  shape all match the §2.10 acceptance criteria. Receipt in CHANGES.md §6.5.
- **Glob auto-discovery works in the live container**: the running
  `i2b2-ml` jobWatcher logs
  `Engine Modules are: ['llmEngine', 'mlEngine', 'BaseEngine']`. Confirmed
  in the live smoke session.
- **All sample JSONs parse** as valid JSON (just verified).
- **Architecture diagram in `i2b2_cdi/LLM/README.md`** matches the actual
  code flow (POST → Flask → concept_API → perform_LLM → ... → engine →
  dispatch → run_label → provider/validators/audit → send_facts).
- **Two physical lines in `loader/i2b2_cdi_app.py`** at the documented
  position. No accidental wider edits.
- **No TODO/FIXME/HACK** comments anywhere in the LLM module or its
  tests. Code is intentional rather than scaffolded.
- **No `print()` calls** — all logging via loguru as required by the
  project style.
- **No bare `except:`** — every except names at least `Exception`.
- **MockProvider has all 5 documented fail modes** (`schema_invalid`,
  `hallucinate`, `empty`, `timeout`, `low_confidence`) and rejects
  unknown modes at construction.
- **`tabulate` claim was wrong in AUDIT.md** but the fix is correct in
  the README: tabulate IS in upstream `requirements.txt`, conftest stubs
  it for pytest. The README documents this explicitly.

---

## Total findings count

| Severity | Count |
|---|---|
| CRITICAL | 0 |
| HIGH | 4 |
| MEDIUM | 14 |
| LOW | 17 |
| NIT | 9 |
| **Total** | **44** |

---

## Overall verdict

**"Fix 4 items first" — specifically the HIGH findings.**

The module is **functionally solid** — 132 tests pass, live-PG acceptance
verified end-to-end, and no findings rise to CRITICAL. But the 4 HIGH
items are exactly the kind of thing Kavi will probe in a 30-minute review:

- **H-1** (`bool("false")` opt-in bypass) is the only finding that could
  be called a security bug. Worth a 5-line fix before any external-PHI
  conversation.
- **H-2** (missing FK on `llm_audit.job_id`) is direct spec drift. A
  reviewer comparing CHANGES.md §6 → spec §2.6 will flag it.
- **H-3** (chat-template not used by LocalHF) affects any number you
  produce comparing LocalHF against Anthropic for the paper.
- **H-4** (`_today()` as start_date) is the temporal-data-leakage concern
  the i2b2 paper is built around. Even just documenting the limitation
  in CHANGES.md §10 (Known limitations) closes most of the risk.

The 14 MEDIUM and 17 LOW findings are all worth tracking but none should
block the conversation with Kavi. The MEDIUMs in particular are good
material for "things we noticed and want your input on" during the demo.

**Recommendation:** Fix H-1, H-2, H-3, H-4 in a follow-up commit on this
branch before opening the conversation with Kavi. Add the MEDIUM list
as a section in `KAVI_CHECKLIST.md` to surface them organically across
the next few biweeklies rather than dumping them all at once.

---

## Resolutions (2026-05-27, follow-up pass)

All 4 original HIGH items + the 1 promoted-from-MEDIUM (M-8 → H-5) are
now fixed and committed on `feature/llm-module`. Per the user's
direction in the follow-up prompt, no MEDIUM/LOW/NIT items were
addressed in this pass — those remain banked for future work.

| Item | Status | Commit | Test names |
|---|---|---|---|
| **H-1** strict external_provider opt-in (reject `bool("false") == True`) | ✅ FIXED | `1a5af3c` fix(H-1) | `test_external_provider_optin_accepted_values` (4 params), `test_external_provider_optin_rejected_values` (17 params), `test_external_provider_optin_missing_rejected`, `test_external_provider_misconfigured_string_emits_warning`, `test_is_truthy_optin_unit_table` |
| **H-5** (promoted from M-8) schema-qualify all LLM SQL | ✅ FIXED | `5aebca1` fix(H-5) | `test_audit_sql_is_schema_qualified_via_crc_db_name`, `test_audit_sql_works_with_empty_crc_db_name` |
| **H-2** missing FK on `llm_audit.job_id` | ✅ FIXED | `0e41534` fix(H-2) | `test_audit_foreign_key_to_job_enforces` |
| **H-3** chat-template support in LocalHFProvider | ✅ FIXED | `d89fa93` fix(H-3) | `test_local_hf_auto_detects_chat_template_and_applies_it`, `test_local_hf_no_chat_template_uses_raw_prompt`, `test_local_hf_explicit_use_chat_template_true_without_template_raises`, `test_local_hf_explicit_use_chat_template_false_skips_template` |
| **H-4** `prediction_event_path` for start_date + warning when absent | ✅ FIXED | `63afbcf` fix(H-4) | `test_apply_label_uses_prediction_event_date_when_provided`, `test_apply_label_warns_when_event_path_missing` |

### Final verification (after all 5 fixes)

```
$ pytest tests/LLM/                              → 162 passed, 3 deselected, 0 failed, 0 skipped
$ RUN_LIVE_PG=1 pytest tests/LLM/                → 165 passed, 0 failed, 0 skipped
```

Net test growth from the H-fix pass: **129 → 162 unit tests (+33 new),
132 → 165 total** with live-PG.

### Additional fixes performed alongside the H-items

1. **Migration self-containment (H-2 side-effect)** — Both
   `100_llm_audit.sql` files now `SET search_path TO i2b2demodata, public`
   at the top, so they no longer require pre-existing search_path
   configuration. Necessary because H-5 documentation removed the
   `ALTER USER` step from the reproduction recipe.
2. **CHANGES.md §10 documents two upstream paper bugs** that now
   surface explicitly in `apply_LLM`: the `prediction_event_path`
   semantics (H-4) and the `time_buffer` days-vs-seconds discrepancy
   (banked for Kavi). The latter is a real Klann et al. Appendix B
   bug that we follow the code, not the paper, for.

### Out-of-scope (intentionally deferred per follow-up prompt)

All 14 MEDIUM, 17 LOW, and 9 NIT findings from the original audit
remain unaddressed. They are tracked in this document above the
"Resolutions" section. Per Dr. W's expected review style:
- Surface the MEDIUM items in `KAVI_CHECKLIST.md` over the next 2-3
  biweeklies rather than dumping them at once.
- Bundle the LOW and NIT items into a single tech-debt PR after the
  initial Kavi review lands.

### Updated verdict

**Ready to show Kavi.** All 5 originally-identified HIGH items are
fixed with regression tests. The MEDIUM/LOW backlog is documented
above and is appropriate to surface across multiple meetings rather
than blocking the first conversation.
