"""Tests for retriever module."""

from langchain_core.documents import Document

from src.rag.retriever import format_retrieved_docs


def test_format_retrieved_docs_empty():
    """Empty doc list returns empty string."""
    assert format_retrieved_docs([]) == ""


def test_format_retrieved_docs_single():
    """Single doc is formatted with source annotation."""
    docs = [
        Document(
            page_content="# GetUser\n\nGet user by ID.",
            metadata={"source": "proj/mod/GetUser.md"},
        )
    ]
    result = format_retrieved_docs(docs)
    assert "文档 1" in result
    assert "proj/mod/GetUser.md" in result
    assert "# GetUser" in result


def test_format_retrieved_docs_multiple():
    """Multiple docs are formatted with numbered source annotations."""
    docs = [
        Document(
            page_content="Doc A content",
            metadata={"source": "a.md"},
        ),
        Document(
            page_content="Doc B content",
            metadata={"source": "b.md"},
        ),
    ]
    result = format_retrieved_docs(docs)
    assert "文档 1" in result
    assert "文档 2" in result
    assert "a.md" in result
    assert "b.md" in result
    assert "Doc A content" in result
    assert "Doc B content" in result


def test_format_retrieved_docs_missing_source_metadata():
    """Doc without source metadata uses 'unknown' as source."""
    docs = [Document(page_content="Some content", metadata={})]
    result = format_retrieved_docs(docs)
    assert "unknown" in result
    assert "Some content" in result


from unittest.mock import patch, MagicMock


def test_get_retriever_creates_chroma_with_correct_config():
    """get_retriever initializes Chroma with persist dir and collection name."""
    with patch("src.rag.retriever.settings") as mock_settings, \
         patch("src.rag.retriever.get_embeddings") as mock_get_embed, \
         patch("src.rag.retriever.Chroma") as MockChroma:
        mock_settings.chroma.persist_dir = "/tmp/test-chroma"
        mock_settings.chroma.collection_name = "test_docs"
        mock_embed_instance = MagicMock()
        mock_get_embed.return_value = mock_embed_instance

        mock_vectorstore = MagicMock()
        MockChroma.return_value = mock_vectorstore
        mock_retriever = MagicMock()
        mock_vectorstore.as_retriever.return_value = mock_retriever

        from src.rag.retriever import get_retriever
        # Clear lru_cache from previous calls
        get_retriever.cache_clear()

        result = get_retriever()

        MockChroma.assert_called_once_with(
            collection_name="test_docs",
            persist_directory="/tmp/test-chroma",
            embedding_function=mock_embed_instance,
        )
        mock_vectorstore.as_retriever.assert_called_once_with(
            search_kwargs={"k": 3},
        )
        assert result == mock_retriever


def test_get_retriever_is_cached():
    """get_retriever returns cached retriever on second call."""
    with patch("src.rag.retriever.settings") as mock_settings, \
         patch("src.rag.retriever.get_embeddings") as mock_get_embed, \
         patch("src.rag.retriever.Chroma") as MockChroma:
        mock_settings.chroma.persist_dir = "/tmp/test-chroma"
        mock_settings.chroma.collection_name = "test_docs"

        from src.rag.retriever import get_retriever
        get_retriever.cache_clear()

        r1 = get_retriever()
        r2 = get_retriever()

        # Chroma should only be instantiated once
        assert MockChroma.call_count == 1
        assert r1 is r2
