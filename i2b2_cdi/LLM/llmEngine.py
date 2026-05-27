# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""``llmEngine`` — BaseEngine subclass auto-discovered by the job orchestrator.

Filename MUST be ``llmEngine.py`` and the class name MUST be ``llmEngine``
(lowercase first letter, camelCase suffix). The orchestrator's discovery uses
case-sensitive matching via ``module_name.split('/')[-1].replace('.py','')``;
a name mismatch causes silent auto-discovery failure.

``jobWatcher.py:41-42`` splits ``jobType`` on ``-`` and takes the prefix, so
``"llm"``, ``"llm-label"``, ``"llm-extract"``, ``"llm-feature"`` all dispatch
to this engine. The full ``jobType`` string (with suffix) is passed through to
``dispatch_usecase`` so each variant can vary behavior.
"""
from __future__ import annotations

from loguru import logger

from i2b2_cdi.config.config import Config
from i2b2_cdi.database.cdi_database_connections import I2b2crcDataSource
from i2b2_cdi.job.BaseEngine import BaseEngine
from i2b2_cdi.LLM.llm_usecase import dispatch_usecase


class llmEngine(BaseEngine):
    """LLM job engine. Same constructor shape as ``mlEngine`` for the orchestrator."""

    def __init__(self, job_id):
        super().__init__()
        logger.info("Inside LLM computation")
        config = Config().new_config(argv=["project", "add"])
        self.crc_ds = I2b2crcDataSource(config)
        self.job_id = job_id

    def run(self, jobId, projectName, conceptBlob, conceptCode, conceptPath, node, jobType):
        self.concept_code = conceptCode
        input_params = self.get_job_inputs(jobId)
        concept_blob = self.get_concept_blob(conceptCode)
        logger.info("LLM job {} type={} concept={}", jobId, jobType, conceptCode)
        return dispatch_usecase(
            jobType=jobType,
            conceptPath=conceptPath,
            conceptCode=conceptCode,
            crc_ds=self.crc_ds,
            job_id=jobId,
            project_name=projectName,
            concept_blob=concept_blob,
            input_params=input_params,
            send_facts=self.send_facts,
        )
