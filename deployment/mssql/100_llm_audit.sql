-- Copyright 2025 Massachusetts General Hospital.
-- Apache-2.0
-- LLM audit table (MSSQL). Same shape as the PG migration.

IF NOT EXISTS (SELECT 1 FROM sysobjects WHERE name = 'llm_audit' AND xtype = 'U')
BEGIN
    CREATE TABLE llm_audit (
        audit_id            BIGINT IDENTITY(1,1) PRIMARY KEY,
        job_id              BIGINT NOT NULL
                                REFERENCES job(id) ON DELETE CASCADE,
        patient_num         BIGINT NULL,
        concept_cd          VARCHAR(50) NULL,
        provider_name       VARCHAR(64) NOT NULL,
        model_name          VARCHAR(256) NOT NULL,
        prompt_hash         CHAR(64) NOT NULL,
        prompt_text         NVARCHAR(MAX) NULL,
        response_text       NVARCHAR(MAX) NULL,
        parsed_output       NVARCHAR(MAX) NULL,
        finish_reason       VARCHAR(32) NULL,
        prompt_tokens       INT NULL,
        completion_tokens   INT NULL,
        cost_usd            DECIMAL(12,6) NULL,
        latency_ms          INT NULL,
        guardrail_outcome   VARCHAR(32) NULL,
        created_at          DATETIME DEFAULT GETDATE()
    );

    CREATE INDEX idx_llm_audit_job ON llm_audit(job_id);
    CREATE INDEX idx_llm_audit_patient ON llm_audit(patient_num);
    CREATE INDEX idx_llm_audit_concept ON llm_audit(concept_cd);
END;
