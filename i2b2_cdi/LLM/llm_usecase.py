# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Dispatch a job to the right use-case implementation based on jobType suffix.

The full jobType string (e.g. ``"llm-label"``) is split on ``-``; suffix-less
``"llm"`` and ``"llm-label"`` both route to label. ``llm-extract`` and
``llm-feature`` are stubs that raise NotImplementedError with a clear pointer
(Sprint 3+).
"""
from __future__ import annotations

from typing import Callable

from loguru import logger

from i2b2_cdi.LLM.apply_LLM import run_label


def dispatch_usecase(
    *,
    jobType: str,
    conceptPath: str,
    conceptCode: str,
    crc_ds,
    job_id: int,
    project_name: str,
    concept_blob: dict,
    input_params: dict,
    send_facts: Callable,
) -> dict:
    """Route by jobType suffix and return the engine's output summary dict."""
    suffix = ""
    if jobType and "-" in jobType:
        suffix = jobType.split("-", 1)[1].lower()
    elif jobType:
        suffix = jobType.lower()

    if suffix in ("", "llm", "label"):
        logger.info("Dispatching to run_label for jobType={}", jobType)
        return run_label(
            conceptPath=conceptPath,
            conceptCode=conceptCode,
            crc_ds=crc_ds,
            job_id=job_id,
            project_name=project_name,
            concept_blob=concept_blob,
            input_params=input_params,
            send_facts=send_facts,
        )
    if suffix == "extract":
        raise NotImplementedError(
            "llm-extract is deferred to Sprint 3+. See LLM_MODULE_SPEC §2.9."
        )
    if suffix == "feature":
        raise NotImplementedError(
            "llm-feature is deferred to Sprint 3+. See LLM_MODULE_SPEC §2.9."
        )
    raise ValueError(f"Unknown LLM jobType suffix {suffix!r} (full={jobType!r})")
