-- Copyright 2025 Massachusetts General Hospital.
-- Apache-2.0
-- LLM audit table — one row per provider call (plus terminal "exhausted" rows).
-- Created for LLM_MODULE_SPEC §2.6.

CREATE TABLE IF NOT EXISTS llm_audit (
    audit_id        BIGSERIAL PRIMARY KEY,
    job_id          BIGINT NOT NULL,
    patient_num     BIGINT,
    concept_cd      VARCHAR(50),
    provider_name   VARCHAR(64) NOT NULL,
    model_name      VARCHAR(256) NOT NULL,
    prompt_hash     CHAR(64) NOT NULL,
    prompt_text     TEXT,
    response_text   TEXT,
    parsed_output   JSONB,
    finish_reason   VARCHAR(32),
    prompt_tokens   INT,
    completion_tokens INT,
    cost_usd        NUMERIC(12,6),
    latency_ms      INT,
    guardrail_outcome VARCHAR(32),
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llm_audit_job ON llm_audit(job_id);
CREATE INDEX IF NOT EXISTS idx_llm_audit_patient ON llm_audit(patient_num);
CREATE INDEX IF NOT EXISTS idx_llm_audit_concept ON llm_audit(concept_cd);
