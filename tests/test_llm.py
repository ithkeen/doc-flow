"""Tests for get_node_llm factory."""

from unittest.mock import patch, MagicMock
from src.config.llm import get_node_llm


def test_get_node_llm_uses_global_defaults():
    """When no per-node config is set, falls back to global LLM settings."""
    with patch("src.config.llm.settings") as mock_settings, \
         patch("src.config.llm.ChatOpenAI") as MockChatOpenAI:
        mock_settings.llm.base_url = "https://global.api/v1"
        mock_settings.llm.api_key = "global-key"
        mock_settings.llm.model = "gpt-4"

        node_cfg = MagicMock()
        node_cfg.base_url = None
        node_cfg.api_key = None
        node_cfg.model = None
        mock_settings.doc_gen_llm = node_cfg

        get_node_llm("doc_gen")

        MockChatOpenAI.assert_called_once_with(
            base_url="https://global.api/v1", api_key="global-key", model="gpt-4"
        )


def test_get_node_llm_uses_per_node_override():
    """When per-node config is set, it overrides global."""
    with patch("src.config.llm.settings") as mock_settings, \
         patch("src.config.llm.ChatOpenAI") as MockChatOpenAI:
        mock_settings.llm.base_url = "https://global.api/v1"
        mock_settings.llm.api_key = "global-key"
        mock_settings.llm.model = "gpt-4"

        node_cfg = MagicMock()
        node_cfg.base_url = "https://node.api/v1"
        node_cfg.api_key = "node-key"
        node_cfg.model = "gpt-4o"
        mock_settings.doc_gen_llm = node_cfg

        get_node_llm("doc_gen")

        MockChatOpenAI.assert_called_once_with(
            base_url="https://node.api/v1", api_key="node-key", model="gpt-4o"
        )


def test_get_node_llm_unknown_node_uses_global():
    """Unknown node name falls back to all global settings."""
    with patch("src.config.llm.settings") as mock_settings, \
         patch("src.config.llm.ChatOpenAI") as MockChatOpenAI:
        mock_settings.llm.base_url = "https://global.api/v1"
        mock_settings.llm.api_key = "global-key"
        mock_settings.llm.model = "gpt-4"

        get_node_llm("nonexistent")

        MockChatOpenAI.assert_called_once_with(
            base_url="https://global.api/v1", api_key="global-key", model="gpt-4"
        )
