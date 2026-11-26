import os
import sys

# Katalog główny projektu na ścieżce importu, żeby działało `from functions...`
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


import pytest


@pytest.fixture(autouse=True)
def _isolate_llm_env(monkeypatch):
    """Testy nie mogą zależeć od LLM_PROVIDER / LLM_MODEL ustawionych w lokalnym .env."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
