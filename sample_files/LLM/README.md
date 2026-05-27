# Sample LLM use-case JSONs

These are reference payloads for the LLM module. Post each to the matching
endpoint, then submit a job.

| File | Purpose | Endpoint | Job type |
|---|---|---|---|
| `note_label_usecase.json` | Cohort labeling from clinical notes (Sprint 2 vertical slice) | POST `/etl/llm_build_model` | `llm-label` |
| `concept_extract_usecase.json` | Field extraction from notes (placeholder — Sprint 3+) | POST `/etl/llm_build_model` | `llm-extract` |

## Workflow

1. **Create the concept** — POST one of the above payloads to `/etl/llm_build_model`.
   The server validates the prompt template + output schema + provider config and
   writes the augmented blob (with `prompt_template_hash` + `provider_metadata`)
   into `concept_dimension`.

2. **Apply** — POST a job to `/etl/job`:
   ```json
   { "input": { "path": "/LLM/Diagnosis/HeartFailure_LLM" }, "jobType": "llm-label" }
   ```
   The job watcher picks it up, dispatches to `llmEngine`, iterates the target
   cohort, calls the configured provider with retries, validates each output,
   and writes audit rows.

3. **Inspect results** — GET `/etl/job?jobId=N` for the run summary, or
   query `llm_audit` / `observation_fact` directly.

## Notes for the paper

- `audit_level: "full"` is safe for de-identified MIMIC. Switch to `"redacted"`
  before running against any PHI cohort.
- `provider.external_provider` must be `true` to use Anthropic or any
  OpenAI-API endpoint that leaves the Docker boundary. Local providers
  (`local_hf`, `ollama`) ignore this flag.
- `cache_prompt` (Anthropic only) defaults to OFF. Enable only for cohorts
  > 1000 patients with stable prompts — caching's 1024-token minimum +
  1.25x write cost makes it a net loss for small cohorts.
