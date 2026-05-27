# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Flask-RESTX Namespace for LLM endpoints.

D-3.1: This is a Flask-RESTX *Namespace*, NOT a plain Blueprint. The existing
loader (``i2b2_cdi/loader/i2b2_cdi_app.py``) uses ``api.add_namespace(nsX)``
exclusively. Plain Blueprints would silently bypass auth (security regression)
and skip Swagger registration (the paper cites Swagger as the user interface).

Public entry point:
    register_with_api(api, auth, projectNameHeader)

The loader calls this once at startup; two lines are added at L164-165 of
``loader/i2b2_cdi_app.py``.
"""
from __future__ import annotations

import json

from flask import jsonify, make_response, request
from flask_restx import Namespace, Resource, fields
from loguru import logger

from i2b2_cdi.loader import _exception_response


def register_with_api(api, auth, projectNameHeader):
    """Build and register the LLM namespace. Returns the namespace for tests."""
    nsLLM = Namespace("LLM Concepts", description="LLM-backed cohort labeling, extraction, features", path="/")

    create_llm_concept_model = api.model(
        "createLLMConcept",
        {
            "code": fields.String,
            "description": fields.String,
            "path": fields.String,
            "blob": fields.Raw,
        },
    )

    apply_llm_concept_model = api.model(
        "applyLLMConcept",
        {
            "path": fields.String,
            "target_path": fields.String,
        },
    )

    response_codes = {
        200: "Success",
        201: "Created",
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        500: "Internal Server Error",
    }

    @nsLLM.route("/etl/llm_build_model", endpoint="llm_build_model")
    @api.expect(projectNameHeader)
    class LLMConcept(Resource):
        decorators = [auth.login_required(role="DATA_AUTHOR")]

        @api.doc(
            description="Build (validate + register) an LLM concept",
            body=create_llm_concept_model,
            responses=response_codes,
        )
        def post(self):
            """Build LLM Model (validate prompts/schema/provider, persist blob)."""
            from i2b2_cdi.LLM.concept_API import processRequest_build_llm_concept

            return processRequest_build_llm_concept(request)

    @nsLLM.route("/etl/llm_apply_model", endpoint="llm_apply_model")
    @api.expect(projectNameHeader)
    class LLMConceptApply(Resource):
        decorators = [auth.login_required(role="DATA_AUTHOR")]

        @api.doc(
            description="Apply an LLM Model to a target patient set",
            body=apply_llm_concept_model,
            responses=response_codes,
        )
        def post(self):
            """Submit an apply-LLM job through the standard job system."""
            try:
                requestDict = request.data
                requestBody = requestDict.decode("UTF-8")
                payload = json.loads(requestBody) if requestBody else {}
                payload.setdefault("input", {"path": payload.get("path")})
                if "target_path" in payload:
                    payload["input"]["target_patient_set"] = [payload["target_path"]]
                payload["jobType"] = payload.get("jobType", "llm-label")
                from i2b2_cdi.job.jobs import processRequestJob

                request.data = json.dumps(payload).encode("UTF-8")
                return processRequestJob(request)
            except Exception as err:
                logger.exception("llm_apply_model failed: {!r}", err)
                return _exception_response(err)

    api.add_namespace(nsLLM)
    return nsLLM
