import os
import sys

# Project root on the import path so that `from functions...` works
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


import pytest


@pytest.fixture(autouse=True)
def _isolate_llm_env(monkeypatch):
    """Tests must not depend on LLM_PROVIDER / LLM_MODEL set in the local .env."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
