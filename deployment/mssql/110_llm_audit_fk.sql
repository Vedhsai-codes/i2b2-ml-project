-- Copyright 2025 Massachusetts General Hospital.
-- Apache-2.0
--
-- Adds the missing foreign-key from llm_audit.job_id to job(id) for
-- MSSQL deployments that applied 100_llm_audit.sql before the H-2 fix
-- (commits before 2026-05-27 had the column NOT NULL but no FK).
--
-- ON DELETE CASCADE matches the H-2 rationale: audit rows are meaningless
-- without their parent job; orphans should be cleaned up automatically.

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = 'fk_llm_audit_job'
)
BEGIN
    ALTER TABLE llm_audit
        ADD CONSTRAINT fk_llm_audit_job
        FOREIGN KEY (job_id) REFERENCES job(id) ON DELETE CASCADE;
END;
