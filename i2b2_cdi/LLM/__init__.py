# Copyright 2025 Massachusetts General Hospital.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""i2b2_cdi.LLM — Large Language Model integration module for i2b2-ML.

Mirrors the i2b2_cdi.ML pattern. The job orchestrator auto-discovers
``llmEngine.py`` via ``glob.glob('i2b2_cdi/*/*Engine.py')``. The runner.py
in this package is auto-discovered by ``__main__.get_config_modules``.

Supports three use cases dispatched on ``jobType`` suffix:
- ``llm`` / ``llm-label`` → per-patient binary or multi-class labels
- ``llm-extract``         → structured field extraction (deferred, Sprint 3+)
- ``llm-feature``         → dense feature generation (deferred, Sprint 3+)
"""
