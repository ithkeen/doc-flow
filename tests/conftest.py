# tests/conftest.py
"""Shared test fixtures."""

import os

import pytest

# Dummy env vars required by src.config.settings.Settings() so that tool
# modules can be imported in the test environment without a real .env file.
_DUMMY_ENV = {
    "CODE_SPACE_DIR": "/tmp/test-code",
    "DOCS_SPACE_DIR": "/tmp/test-docs",
    "LOG_LEVEL": "DEBUG",
    "LOG_DIR": "/tmp/test-logs",
    "LOG_BACKUP_COUNT": "1",
    "LANGSMITH_TRACING": "false",
    "LANGSMITH_API_KEY": "test-key",
    "LANGSMITH_PROJECT": "test",
    "LANGSMITH_ENDPOINT": "https://localhost",
    "LLM_BASE_URL": "https://localhost",
    "LLM_API_KEY": "test-key",
    "LLM_DEFAULT_MODEL": "test-model",
    "LLM_DOC_GEN_MODEL": "test-model",
    "LLM_CHAT_MODEL": "test-model",
}


@pytest.fixture(autouse=True)
def _stub_env(monkeypatch):
    """Inject dummy env vars so Settings() can be constructed in tests."""
    for key, val in _DUMMY_ENV.items():
        monkeypatch.setenv(key, val)
