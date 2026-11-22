"""Evaluation fixtures: reuse the specialist harness (private seeded DB, private index, real tools).

The specialist fixtures live in ``tests/agents/conftest.py``. They are loaded from that file and
re-exported here so the evaluation suite scores the same pipeline the graph runs.
"""

import importlib.util
import pathlib

_SOURCE = pathlib.Path(__file__).resolve().parents[1] / "agents" / "conftest.py"
_spec = importlib.util.spec_from_file_location("_agent_fixtures", _SOURCE)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

maker = _module.maker
registry = _module.registry
ticket = _module.ticket
pipeline = _module.pipeline
