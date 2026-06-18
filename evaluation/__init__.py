# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Evaluation harness for the i2b2-ML LLM module.

This package is a CONSUMER of ``i2b2_cdi.LLM`` — it imports the provider,
validators, and audit logger as a library and does NOT depend on the
Flask app, the jobWatcher daemon, or a live i2b2 Postgres database. The
intended use is producing demonstration results from a cohort CSV for
the JAMIA Open paper (Klann et al. extension).
"""
