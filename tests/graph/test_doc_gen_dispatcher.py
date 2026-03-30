"""Tests for the doc_gen_dispatcher node."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

# Mock mysql.connector which is imported by src.tools.api_index
# but not needed for these tests
if "mysql" not in sys.modules:
    sys.modules["mysql"] = MagicMock()
    sys.modules["mysql.connector"] = MagicMock()


@pytest.fixture
def mock_state():
    """State with task_file_path for standalone mode."""
    return {
        "messages": [],
        "intent": "batch_doc_gen",
        "task_file_path": "test-project/task.md",
        "task_file_paths": [],
        "generated_doc_paths": [],
    }


@pytest.fixture
def mock_config():
    """Config for standalone mode (task_file_path now in state, not config)."""
    return {"configurable": {}}


@pytest.mark.asyncio
async def test_doc_gen_dispatcher_standalone_mode(mock_state, mock_config):
    """doc_gen_dispatcher reads task_file_path from config in standalone mode."""
    mock_sub_graph = AsyncMock()
    mock_sub_graph.ainvoke = AsyncMock(return_value={
        "messages": [],
        "generated_doc_path": "test-project/docs/generated/foo.md",
    })

    with patch("src.graph.nodes._get_doc_gen_react_graph", return_value=mock_sub_graph):
        with patch("src.graph.nodes._read_task_file") as mock_read:
            mock_read.return_value = ("", ["src/foo.go"])
            from src.graph.nodes import doc_gen_dispatcher
            result = await doc_gen_dispatcher(mock_state, mock_config)

    assert len(result["generated_doc_paths"]) == 1
    assert "foo.md" in result["generated_doc_paths"][0]
    mock_read.assert_called_once_with("test-project")
