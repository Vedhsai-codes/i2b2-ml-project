# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""``build_llm_concept`` — the "build" step for an LLM concept.

Validates that the concept is buildable BEFORE any job runs: render-tests the
prompt template, checks the output schema against Draft 7, instantiates the
provider with its config (fail-fast on missing fields), and runs a cheap
``health_check``. On success, augments the concept_blob with provider
metadata and the prompt template hash, and persists the blob.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

from loguru import logger

from i2b2_cdi.LLM.llm_helper import compute_prompt_hash, render_prompt
from i2b2_cdi.LLM.providers import get_provider
from i2b2_cdi.LLM.validators import SchemaValidator


def build_llm_concept(
    *,
    crc_ds,
    concept_code: str,
    concept_blob: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate + augment + persist the concept_blob. Returns the updated blob.

    Raises:
        ValueError: missing required fields, malformed schema, render failure.
        PermissionError: external provider without opt-in.
        RuntimeError: provider health check failed.
    """
    required = ["prompt_template", "provider"]
    for k in required:
        if k not in concept_blob:
            raise ValueError(f"concept_blob missing required field {k!r}")

    template_name = concept_blob["prompt_template"]
    variables = dict(concept_blob.get("prompt_variables") or {})
    variables.setdefault("note_text", "<<sample note for render test>>")
    variables.setdefault("condition", variables.get("condition", "the condition"))
    variables.setdefault("definition", variables.get("definition", "see notes"))
    variables.setdefault("fields", variables.get("fields", "sample_field"))
    rendered = render_prompt(template_name, variables)
    if not rendered.strip():
        raise ValueError(f"Prompt template {template_name!r} rendered empty")

    output_schema = concept_blob.get("output_schema")
    SchemaValidator(output_schema)  # raises ValueError if malformed

    provider = get_provider(concept_blob["provider"])
    if not provider.health_check():
        raise RuntimeError(
            f"Provider {concept_blob['provider'].get('name')!r} failed health_check"
        )

    augmented = dict(concept_blob)
    augmented["prompt_template_hash"] = compute_prompt_hash(rendered)
    augmented["provider_metadata"] = {
        "name": getattr(provider, "name", concept_blob["provider"].get("name")),
        "model": getattr(provider, "model", concept_blob["provider"].get("model")),
        "is_external": bool(getattr(provider, "is_external", False)),
    }

    _persist_blob(crc_ds, concept_code, augmented)
    return augmented


def _persist_blob(crc_ds, concept_code: str, blob: Dict[str, Any]) -> None:
    """Update ``concept_dimension.concept_blob`` for ``concept_code``. PG/MSSQL aware."""
    db_type = os.environ.get("CRC_DB_TYPE", "pg")
    blob_str = json.dumps(blob)
    try:
        with crc_ds as cursor:
            if db_type == "pg":
                sql = (
                    "UPDATE concept_dimension SET concept_blob = %(blob)s "
                    "WHERE concept_cd = %(code)s"
                )
                cursor.execute(sql, {"blob": blob_str, "code": concept_code})
            elif db_type == "mssql":
                sql = (
                    "UPDATE concept_dimension SET concept_blob = ? WHERE concept_cd = ?"
                )
                cursor.execute(sql, (blob_str, concept_code))
            else:
                logger.warning("Unsupported CRC_DB_TYPE={!r}; blob not persisted", db_type)
    except Exception as e:
        logger.exception("Failed to persist augmented concept_blob: {!r}", e)
        raise
