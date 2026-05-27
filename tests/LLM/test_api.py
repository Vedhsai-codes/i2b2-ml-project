# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Smoke tests for the Flask-RESTX namespace registration.

Avoids booting the full app (which requires environment + DB). Verifies the
namespace builds via ``register_with_api`` against a fresh Flask + Api, and
that the routes appear in the Swagger doc.
"""
from __future__ import annotations

import pytest

flask = pytest.importorskip("flask")
flask_restx = pytest.importorskip("flask_restx")


def _make_app():
    from flask import Flask
    from flask_httpauth import HTTPBasicAuth
    from flask_restx import Api

    app = Flask(__name__)
    api = Api(app, doc="/swagger/")
    auth = HTTPBasicAuth()

    @auth.verify_password
    def _verify(u, p):  # always allow in tests
        return True

    @auth.get_user_roles
    def _roles(u):
        return ["DATA_AUTHOR"]

    header_parser = api.parser()
    header_parser.add_argument("X-Project-Name", location="headers", default="Demo")
    return app, api, auth, header_parser


def test_register_with_api_returns_namespace():
    from i2b2_cdi.LLM.llm_API import register_with_api

    app, api, auth, hdr = _make_app()
    ns = register_with_api(api, auth, hdr)
    assert ns is not None
    assert ns.name == "LLM Concepts"


def test_namespace_contains_build_and_apply_endpoints():
    from i2b2_cdi.LLM.llm_API import register_with_api

    app, api, auth, hdr = _make_app()
    register_with_api(api, auth, hdr)
    rules = sorted(str(r) for r in app.url_map.iter_rules())
    assert any("/etl/llm_build_model" in r for r in rules), rules
    assert any("/etl/llm_apply_model" in r for r in rules), rules


def test_swagger_doc_includes_llm_namespace():
    from i2b2_cdi.LLM.llm_API import register_with_api

    app, api, auth, hdr = _make_app()
    register_with_api(api, auth, hdr)
    with app.test_client() as c:
        resp = c.get("/swagger.json")
        assert resp.status_code == 200
        body = resp.get_json()
        tags = [t.get("name") for t in body.get("tags", [])]
        assert "LLM Concepts" in tags
