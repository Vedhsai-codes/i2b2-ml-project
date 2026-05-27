# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Concept creation route for LLM concepts (mirrors ``ML/concept_API.py``).

Posts to ``/etl/llm_build_model`` arrive here. The flow:
    1. Project routing via X-Project-Name header (same convention as ML).
    2. Write a temp CSV with the concept row, invoke ``concept.runner.mod_run``
       to create the ``concept_dimension`` entry (definition_type = 'LLM-BUILD').
    3. Call ``perform_LLM.build_llm_concept`` to validate prompt/schema/provider
       and persist the augmented blob.
"""
from __future__ import annotations

import csv
import json
import os
import shutil
from datetime import datetime

from flask import jsonify, make_response
from loguru import logger

from i2b2_cdi.common.utils import formatPath
from i2b2_cdi.config.config import Config
from i2b2_cdi.database.cdi_database_connections import I2b2crcDataSource, I2b2metaDataSource
from i2b2_cdi.loader import _exception_response
from i2b2_cdi.loader.validation_helper import validate_concept_cd, validate_path


@validate_concept_cd
@validate_path
def _validate_code_path(code, path):
    return True


def processRequest_build_llm_concept(request):
    """Top-level entry point for POST ``/etl/llm_build_model``."""
    try:
        login_project = request.headers.get("X-Project-Name")
        if login_project != "Demo":
            crc_db_name = login_project
            ont_db_name = login_project
        else:
            crc_db_name = os.environ["CRC_DB_NAME"]
            ont_db_name = os.environ["ONT_DB_NAME"]

        config = Config().new_config(
            argv=["concept", "load", "--crc-db-name", crc_db_name, "--ont-db-name", ont_db_name]
        )
        crc_ds = I2b2crcDataSource(config)

        body = request.data.decode("UTF-8")
        data = json.loads(body)
        code = data["code"]
        path = data["path"] if "path" in data else data["conceptPath"]
        blob = data.get("blob") or {}
        description = data.get("description") or ""

        _validate_code_path(code=code, path=path)

        _generate_load_csv(data=data, crc_db=crc_db_name, ont_db=ont_db_name)

        augmented_blob = _persist_and_augment(crc_ds, code, blob)

        response_body = {
            "path": formatPath(path),
            "code": code,
            "description": description,
            "blob": augmented_blob,
            "definitionType": "LLM-BUILD",
        }
        response = make_response(jsonify(response_body))
        response.status_code = 200
        return response
    except Exception as err:
        return _exception_response(err)


def _persist_and_augment(crc_ds, code, blob):
    from i2b2_cdi.LLM.perform_LLM import build_llm_concept

    return build_llm_concept(crc_ds=crc_ds, concept_code=code, concept_blob=blob)


def _generate_load_csv(data, crc_db, ont_db):
    """Create the temp CSV + invoke concept runner. Mirrors ML/concept_API."""
    code = data["code"]
    path = data["path"] if "path" in data else data["conceptPath"]
    formatted_path = formatPath(path)
    description = data.get("description") or ""
    unit = data.get("unit")
    blob = data.get("blob")

    now = datetime.now()
    dfstring = now.strftime("%d-%m-%Y_%H:%M:%S%f")
    upload_id = now.strftime("%Y%m%d%H%M%S%f")[:19]
    config = Config().new_config(
        argv=[
            "concept",
            "load",
            "--crc-db-name",
            crc_db,
            "--ont-db-name",
            ont_db,
            "--upload-id",
            upload_id,
            "--input-dir",
            "/usr/src/app/tmp/" + dfstring,
        ]
    )
    row = [
        ["type", "unit", "path", "code", "description", "definition_type", "blob"],
        ["largeString", unit, formatted_path, code, description, "LLM-BUILD", json.dumps(blob)],
    ]
    tmpdir = "/usr/src/app/tmp/" + dfstring
    if not os.path.exists(tmpdir):
        os.makedirs(tmpdir)
    filename = tmpdir + "/LLM_concepts.csv"
    with open(filename, "w") as fh:
        csv.writer(fh).writerows(row)

    import i2b2_cdi.concept.runner as concept_runner

    result = concept_runner.mod_run(config)
    logger.info("LLM concept load result: {}", result)

    try:
        os.remove(filename)
        if os.path.exists(tmpdir):
            shutil.rmtree(tmpdir)
    except OSError as e:
        logger.warning("cleanup of {} failed: {!r}", tmpdir, e)
    return result
