"""Tests for get_llm factory."""

from unittest.mock import patch, MagicMock
from src.config.llm import get_llm


def test_get_llm_default_model():
    """Default type uses default_model."""
    with patch("src.config.llm.settings") as mock_settings, \
         patch("src.config.llm.ChatOpenAI") as MockChatOpenAI:
        mock_settings.llm.base_url = "https://api.example.com/v1"
        mock_settings.llm.api_key = "test-key"
        mock_settings.llm.default_model = "gpt-4"
        mock_settings.llm.chat_model = "gpt-3.5"
        mock_settings.llm.doc_gen_model = "gpt-4o"

        get_llm("default")

        MockChatOpenAI.assert_called_once_with(
            base_url="https://api.example.com/v1", api_key="test-key", model="gpt-4"
        )


def test_get_llm_chat_model():
    """Chat type uses chat_model."""
    with patch("src.config.llm.settings") as mock_settings, \
         patch("src.config.llm.ChatOpenAI") as MockChatOpenAI:
        mock_settings.llm.base_url = "https://api.example.com/v1"
        mock_settings.llm.api_key = "test-key"
        mock_settings.llm.default_model = "gpt-4"
        mock_settings.llm.chat_model = "gpt-3.5"
        mock_settings.llm.doc_gen_model = "gpt-4o"

        get_llm("chat")

        MockChatOpenAI.assert_called_once_with(
            base_url="https://api.example.com/v1", api_key="test-key", model="gpt-3.5"
        )


def test_get_llm_doc_gen_model():
    """Doc_gen type uses doc_gen_model."""
    with patch("src.config.llm.settings") as mock_settings, \
         patch("src.config.llm.ChatOpenAI") as MockChatOpenAI:
        mock_settings.llm.base_url = "https://api.example.com/v1"
        mock_settings.llm.api_key = "test-key"
        mock_settings.llm.default_model = "gpt-4"
        mock_settings.llm.chat_model = "gpt-3.5"
        mock_settings.llm.doc_gen_model = "gpt-4o"

        get_llm("doc_gen")

        MockChatOpenAI.assert_called_once_with(
            base_url="https://api.example.com/v1", api_key="test-key", model="gpt-4o"
        )


def test_get_llm_unknown_type_falls_back_to_default():
    """Unknown model type falls back to default_model."""
    with patch("src.config.llm.settings") as mock_settings, \
         patch("src.config.llm.ChatOpenAI") as MockChatOpenAI:
        mock_settings.llm.base_url = "https://api.example.com/v1"
        mock_settings.llm.api_key = "test-key"
        mock_settings.llm.default_model = "gpt-4"
        mock_settings.llm.chat_model = "gpt-3.5"
        mock_settings.llm.doc_gen_model = "gpt-4o"

        get_llm("nonexistent")

        MockChatOpenAI.assert_called_once_with(
            base_url="https://api.example.com/v1", api_key="test-key", model="gpt-4"
        )
