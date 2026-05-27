# i2b2_cdi.LLM

LLM integration for i2b2-ML — sibling to `i2b2_cdi.ML`. Auto-discovered by
the job orchestrator via `glob.glob('i2b2_cdi/*/*Engine.py')`.

## At a glance

```
                                ┌──────────────────────────────────┐
POST /etl/llm_build_model  ──▶  │  concept_API.processRequest_     │
(via Flask-RESTX nsLLM)         │    build_llm_concept             │
                                │     │                            │
                                │     ▼                            │
                                │  perform_LLM.build_llm_concept   │
                                │  (validate prompt / schema /     │
                                │   provider, persist blob)        │
                                └──────────────────────────────────┘

POST /etl/job  (jobType=llm-label)
        │   inserts row into `job` table (status=PENDING)
        ▼
┌──────────────────────────────────────────────────────────────────┐
│ jobWatcher (BackgroundScheduler, every 10s)                      │
│   → jobOrchestrator picks PENDING rows                           │
│   → dynamic_engine_importer loads i2b2_cdi/LLM/llmEngine.py      │
│   → engineObj.run(jobId, projectName, input, ...)                │
└──────────────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────────────┐
│ llmEngine.run → llm_usecase.dispatch_usecase                     │
│   suffix "label" → apply_LLM.run_label                           │
│                                                                  │
│   for each patient in target cohort:                             │
│     render_prompt(template, vars)                                │
│     retry_with_backoff(provider.generate)                        │
│         → coerce_text_to_dict                                    │
│         → SchemaValidator                                        │
│         → HallucinationGuard                                     │
│         → PromptAuditLogger.log  (one row per attempt)           │
│     on success: append to fact rows                              │
│     on terminal failure: extra "exhausted" audit row             │
│                                                                  │
│   send_facts(df)  → BaseEngine writes observation_fact           │
│   return summary dict → saved into job.output                    │
└──────────────────────────────────────────────────────────────────┘
```

## Adding a new provider

1. Subclass `LLMProvider` in `providers/your_provider.py`. Set `name` and
   `is_external`. Implement `generate()` and `health_check()`. Translate
   SDK exceptions per the contract in `providers/base.py`.
2. Add `"your_provider": YourProvider` to `PROVIDER_REGISTRY` in
   `providers/__init__.py`, OR call `register_provider("your_provider", YourProvider)`
   at module load time. The LOCAL/EXTERNAL sets auto-update.
3. Add a row to the exception-translation table in `CHANGES.md`.

## Adding a new use case

1. Add a prompt template under `prompts/<name>.txt`.
2. Extend the `if suffix == "..."` ladder in `llm_usecase.dispatch_usecase`.
3. Implement the new function in `apply_LLM.py` (or a sibling file). Follow
   the same retry / validate / audit / send_facts flow.
4. Add an example use-case JSON under `sample_files/LLM/`.

## Full specification

See `LLM_MODULE_SPEC.md` at the repo root for the canonical reference.
