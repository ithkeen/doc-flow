"""Tests for get_embeddings factory."""

from unittest.mock import patch, MagicMock


def test_get_embeddings_uses_settings():
    """get_embeddings returns OpenAIEmbeddings with correct config."""
    with patch("src.rag.embeddings.settings") as mock_settings, \
         patch("src.rag.embeddings.OpenAIEmbeddings") as MockEmbed:
        mock_settings.llm.base_url = "https://api.example.com/v1"
        mock_settings.llm.api_key = "test-key"
        mock_settings.llm.embed_model = "text-embedding-3-small"

        from src.rag.embeddings import get_embeddings
        result = get_embeddings()

        MockEmbed.assert_called_once_with(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="text-embedding-3-small",
        )
        assert result == MockEmbed.return_value
