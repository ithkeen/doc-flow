"""Tests for the doc_qa node with RAG retrieval."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage

# Mock mysql.connector which is imported by src.tools.api_index
# but not needed for doc_qa tests
if "mysql" not in sys.modules:
    sys.modules["mysql"] = MagicMock()
    sys.modules["mysql.connector"] = MagicMock()


@pytest.fixture
def mock_state():
    """State with a single human message."""
    return {
        "messages": [HumanMessage(content="GetUser 接口的参数是什么？")],
        "intent": "doc_qa",
    }


@pytest.fixture
def mock_config():
    return {"configurable": {}}


async def test_doc_qa_retrieves_docs_and_injects_context(mock_state, mock_config):
    """doc_qa node retrieves docs from Chroma and passes context to LLM."""
    fake_docs = [
        Document(
            page_content="# GetUser\n\nParameters: user_id (int)",
            metadata={"source": "proj/mod/GetUser.md"},
        )
    ]
    mock_retriever = AsyncMock()
    mock_retriever.ainvoke.return_value = fake_docs

    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = AIMessage(content="GetUser 接口的参数是 user_id")

    with patch("src.graph.nodes.get_retriever", return_value=mock_retriever), \
         patch("src.graph.nodes.get_llm", return_value=mock_llm):
        from src.graph.nodes import doc_qa
        result = await doc_qa(mock_state, mock_config)

    # Retriever was called with user question
    mock_retriever.ainvoke.assert_called_once_with(
        "GetUser 接口的参数是什么？"
    )

    # LLM was called with messages containing the context
    call_args = mock_llm.ainvoke.call_args
    all_messages = call_args[0][0]
    system_content = all_messages[0].content
    assert "GetUser" in system_content
    assert "proj/mod/GetUser.md" in system_content

    # Response is wrapped correctly
    assert result == {"messages": [mock_llm.ainvoke.return_value]}


async def test_doc_qa_handles_empty_retrieval(mock_state, mock_config):
    """doc_qa works gracefully when no docs are found."""
    mock_retriever = AsyncMock()
    mock_retriever.ainvoke.return_value = []

    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = AIMessage(content="文档库中暂无相关内容")

    with patch("src.graph.nodes.get_retriever", return_value=mock_retriever), \
         patch("src.graph.nodes.get_llm", return_value=mock_llm):
        from src.graph.nodes import doc_qa
        result = await doc_qa(mock_state, mock_config)

    # Should still return a valid response
    assert len(result["messages"]) == 1


async def test_doc_qa_handles_retriever_failure(mock_state, mock_config):
    """doc_qa returns graceful response when retriever fails."""
    mock_retriever = AsyncMock()
    mock_retriever.ainvoke.side_effect = Exception("Chroma unavailable")

    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = AIMessage(content="文档库中暂无相关内容")

    with patch("src.graph.nodes.get_retriever", return_value=mock_retriever), \
         patch("src.graph.nodes.get_llm", return_value=mock_llm):
        from src.graph.nodes import doc_qa
        result = await doc_qa(mock_state, mock_config)

    # Should still return a response (with empty context)
    assert len(result["messages"]) == 1
