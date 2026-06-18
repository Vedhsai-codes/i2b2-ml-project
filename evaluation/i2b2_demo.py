#!/usr/bin/env python
# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""End-to-end demonstration of the i2b2 LLM-jobWatcher path on REAL MIMIC data.

Distinct from ``run_demonstration.py`` (which uses the LLM module as a
library, no i2b2 stack required). THIS script proves the actual paper
claim: an LLM concept + job posted through the i2b2 system gets picked
up by the jobWatcher daemon, processed by ``llmEngine``, and results
land in ``observation_fact`` + ``llm_audit`` exactly the way the
existing ML pipeline does.

Steps performed:

    1. Open psycopg2 connection to the i2b2-pg container (search_path = i2b2demodata).
    2. Seed real MIMIC patient/note/cohort concepts into concept_dimension +
       observation_fact:
         - /LLM/Diagnosis/HF_Demo            (the LLM concept under test)
         - /cohort/demo_hf                   (1-patient cohort)
         - /MIMIC/notes/discharge_demo       (note concept)
    3. Insert one job row into i2b2demodata.job with job_type='llm-label'.
    4. Wait up to 60s for the jobWatcher (running in the i2b2-ml container) to
       pick it up and transition status PENDING -> PROCESSING -> COMPLETED.
    5. Query llm_audit + observation_fact + job.output for the receipt.
    6. Print a pretty summary.

Prerequisites: Docker stack up (i2b2-pg, i2b2-etl, i2b2-ml); the
LLM_ENABLE_MOCK_PROVIDER=1 env var in the i2b2-ml container so the
mock provider is registered; cohort row at /tmp/i2b2_demo_patient.json.

Usage::

    python evaluation/i2b2_demo.py [--patient-json PATH] [--timeout-s 60]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional


def _pg_conn():
    import psycopg2

    return psycopg2.connect(
        host="localhost",
        port=5432,
        user="i2b2",
        password="demouser",
        dbname="i2b2",
        options="-c search_path=i2b2demodata,public",
        connect_timeout=5,
    )


def _bold(s):
    return f"\033[1m{s}\033[0m" if sys.stdout.isatty() else s


def _green(s):
    return f"\033[32m{s}\033[0m" if sys.stdout.isatty() else s


def _red(s):
    return f"\033[31m{s}\033[0m" if sys.stdout.isatty() else s


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--patient-json",
        default="/tmp/i2b2_demo_patient.json",
        help="Path to a JSON file with subject_id, hadm_id, note_id, note_date, text, hf_gold",
    )
    p.add_argument(
        "--timeout-s",
        type=int,
        default=60,
        help="Max seconds to wait for the jobWatcher to mark the job COMPLETED",
    )
    args = p.parse_args()

    patient = json.loads(Path(args.patient_json).read_text())
    subject_id = patient["subject_id"]
    hf_gold = patient["hf_gold"]
    note_text = patient["text"]

    print(_bold(f"\n  i2b2 end-to-end demo — patient {subject_id} (gold={hf_gold})"))
    print(f"  note: {len(note_text)} chars, hadm_id={patient['hadm_id']}\n")

    conn = _pg_conn()
    conn.autocommit = True
    cur = conn.cursor()

    # ───── 1. seed concepts ─────
    print(_bold("  [1/5] Seeding concepts + facts..."))

    concept_blob = {
        "target_patient_set": ["/cohort/demo_hf"],
        "note_concept_paths": ["/MIMIC/notes/discharge_demo"],
        "prompt_template": "cohort_labeling",
        "prompt_variables": {
            "condition": "heart failure",
            "definition": "presence of NYHA class symptoms, BNP > 400 pg/mL, or echo EF < 40%",
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "label": {"type": "integer", "enum": [0, 1]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "evidence": {"type": "string"},
            },
            "required": ["label", "confidence"],
        },
        "provider": {"name": "mock", "model": "mock-i2b2-demo"},
        "guardrails": {"min_confidence": 0.5, "max_retries": 1},
        "sampling": {"temperature": 0.0, "max_tokens": 128},
        "audit_level": "full",
    }

    # Idempotent cleanup of prior demo runs
    cur.execute(
        "DELETE FROM concept_dimension WHERE concept_path IN ("
        " '/LLM/Diagnosis/HF_Demo', '/cohort/demo_hf', '/MIMIC/notes/discharge_demo'"
        ")"
    )
    cur.execute(
        "DELETE FROM observation_fact WHERE concept_cd IN ('HF_DEMO', 'DEMO_COHORT', 'DEMO_NOTE')"
    )

    # The 3 concept rows
    cur.execute(
        "INSERT INTO concept_dimension (concept_cd, concept_path, name_char, concept_blob, definition_type) "
        "VALUES ('HF_DEMO', '/LLM/Diagnosis/HF_Demo', 'HF_DEMO', %s, 'LLM-BUILD')",
        (json.dumps(concept_blob),),
    )
    cur.execute(
        "INSERT INTO concept_dimension (concept_cd, concept_path, name_char, concept_blob, definition_type) "
        "VALUES ('DEMO_COHORT', '/cohort/demo_hf', 'DEMO_COHORT', '{}', 'PATIENT_SET')"
    )
    cur.execute(
        "INSERT INTO concept_dimension (concept_cd, concept_path, name_char, concept_blob, definition_type) "
        "VALUES ('DEMO_NOTE', '/MIMIC/notes/discharge_demo', 'DEMO_NOTE', '{}', 'NOTE')"
    )

    # Cohort membership: the patient is in /cohort/demo_hf
    cur.execute(
        "INSERT INTO observation_fact "
        "(encounter_num, patient_num, concept_cd, start_date, provider_id, modifier_cd, instance_num) "
        "VALUES (0, %s, 'DEMO_COHORT', '2018-01-01', '@', '@', 1)",
        (subject_id,),
    )
    # The patient's discharge note
    cur.execute(
        "INSERT INTO observation_fact "
        "(encounter_num, patient_num, concept_cd, start_date, provider_id, modifier_cd, instance_num, observation_blob) "
        "VALUES (0, %s, 'DEMO_NOTE', '2018-01-01', '@', '@', 1, %s)",
        (subject_id, note_text),
    )
    print(f"    {_green('✓')} concepts + facts seeded in i2b2demodata\n")

    # ───── 2. submit job ─────
    print(_bold("  [2/5] Submitting LLM-label job to i2b2demodata.job..."))
    cur.execute(
        "INSERT INTO job (project_name, priority, input, status, job_type, started_on, completed_on) "
        "VALUES (%s, %s, %s, 'PENDING', 'llm-label', NOW(), NOW()) RETURNING id",
        ("i2b2demodata", 0, json.dumps({"path": "/LLM/Diagnosis/HF_Demo"})),
    )
    job_id = cur.fetchone()[0]
    print(f"    {_green('✓')} job_id={job_id} status=PENDING\n")

    # ───── 3. wait for jobWatcher ─────
    print(_bold(f"  [3/5] Waiting up to {args.timeout_s}s for jobWatcher to process..."))
    deadline = time.time() + args.timeout_s
    final_status: Optional[str] = None
    last_status = "PENDING"
    while time.time() < deadline:
        cur.execute("SELECT status FROM job WHERE id = %s", (job_id,))
        row = cur.fetchone()
        if row:
            status = row[0]
            if status != last_status:
                elapsed = int(time.time() - (deadline - args.timeout_s))
                print(f"    [{elapsed:>3}s] transition: {last_status} → {status}")
                last_status = status
            if status in ("COMPLETED", "ERROR"):
                final_status = status
                break
        time.sleep(2)

    if final_status is None:
        print(f"    {_red('✗')} TIMEOUT — job still {last_status} after {args.timeout_s}s")
        print(f"    Check: docker logs i2b2-ml")
        sys.exit(1)
    color = _green if final_status == "COMPLETED" else _red
    print(f"    {color('✓' if final_status == 'COMPLETED' else '✗')} final status: {final_status}\n")

    # ───── 4. read receipts ─────
    print(_bold("  [4/5] Reading receipts from llm_audit + observation_fact + job.output..."))

    cur.execute(
        "SELECT count(*), count(DISTINCT patient_num), array_agg(DISTINCT guardrail_outcome) "
        "FROM llm_audit WHERE job_id = %s",
        (job_id,),
    )
    audit_rows, audit_patients, audit_outcomes = cur.fetchone()
    print(f"    llm_audit:        {audit_rows} rows | patients seen: {audit_patients} | outcomes: {audit_outcomes}")

    cur.execute(
        "SELECT count(*), array_agg(nval_num) FROM observation_fact WHERE concept_cd = 'HF_DEMO'"
    )
    fact_count, fact_values = cur.fetchone()
    print(f"    observation_fact: {fact_count} rows under concept_cd='HF_DEMO' | values: {fact_values}")

    cur.execute("SELECT output, error_stack FROM job WHERE id = %s", (job_id,))
    output_raw, error_stack = cur.fetchone()
    if error_stack:
        print(f"    {_red('✗')} job.error_stack: {error_stack[:200]}")
    print(f"    job.output:       {output_raw}")
    print()

    # ───── 5. summary card ─────
    print(_bold("  [5/5] Demo receipt"))
    print(f"    git SHA:        (run `git rev-parse HEAD` to capture)")
    try:
        import subprocess

        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(Path(__file__).resolve().parent.parent),
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        print(f"    git SHA:        {sha[:12]}")
    except Exception:
        pass
    print(f"    patient:        {subject_id} (real MIMIC, hf_gold={hf_gold})")
    print(f"    note length:    {len(note_text)} chars")
    print(f"    job_id:         {job_id}")
    print(f"    final status:   {final_status}")
    print(f"    audit rows:     {audit_rows}")
    print(f"    fact rows:      {fact_count}")
    print()
    if final_status == "COMPLETED" and audit_rows > 0 and fact_count > 0:
        print(_green(_bold("  ✓ END-TO-END i2b2 PATH VERIFIED ON REAL MIMIC DATA")))
    else:
        print(_red(_bold("  ✗ partial success — see receipts above")))
    print()


if __name__ == "__main__":
    main()
