-- Copyright 2025 Massachusetts General Hospital.
-- Apache-2.0
--
-- Adds the missing foreign-key from llm_audit.job_id to job(id) for
-- deployments that applied 100_llm_audit.sql before the H-2 fix
-- (commits before 2026-05-27 had the column NOT NULL but no FK).
--
-- ON DELETE CASCADE matches the H-2 rationale: audit rows are meaningless
-- without their parent job; orphans should be cleaned up automatically.
--
-- Safe to run on a fresh database (100_llm_audit.sql now creates the FK
-- inline, so this script will no-op via the IF NOT EXISTS guard).
--
-- Edit the search_path below for deployments that use a different CRC
-- schema name (must match $CRC_DB_NAME).
SET search_path TO i2b2demodata, public;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_llm_audit_job'
    ) THEN
        ALTER TABLE llm_audit
            ADD CONSTRAINT fk_llm_audit_job
            FOREIGN KEY (job_id) REFERENCES job(id) ON DELETE CASCADE;
    END IF;
END
$$;
