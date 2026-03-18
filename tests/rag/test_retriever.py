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
