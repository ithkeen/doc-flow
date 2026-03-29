"""Tests for the project_explore node and routing."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

if "mysql" not in sys.modules:
    sys.modules["mysql"] = MagicMock()
    sys.modules["mysql.connector"] = MagicMock()


@pytest.fixture
def mock_state():
    return {
        "messages": [HumanMessage(content="探索 ubill-access-api 项目")],
        "intent": "project_explore",
    }


@pytest.fixture
def mock_config():
    return {"configurable": {}}


async def test_project_explore_binds_tools_and_returns_message(mock_state, mock_config):
    """project_explore binds EXPLORE_TOOLS to the LLM and returns its response."""
    mock_response = AIMessage(content="开始探索项目...")
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)
    mock_llm.bind_tools.return_value = mock_llm

    with patch("src.graph.nodes.get_llm", return_value=mock_llm), \
         patch("src.graph.nodes.load_prompt") as mock_load:
        mock_prompt = MagicMock()
        mock_prompt.format_messages.return_value = []
        mock_load.return_value = mock_prompt

        from src.graph.nodes import project_explore, EXPLORE_TOOLS
        result = await project_explore(mock_state, mock_config)

    mock_llm.bind_tools.assert_called_once_with(EXPLORE_TOOLS)
    assert result == {"messages": [mock_response]}


async def test_project_explore_uses_correct_prompt(mock_state, mock_config):
    """project_explore loads the 'project_explore' prompt."""
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok"))
    mock_llm.bind_tools.return_value = mock_llm

    with patch("src.graph.nodes.get_llm", return_value=mock_llm), \
         patch("src.graph.nodes.load_prompt") as mock_load:
        mock_prompt = MagicMock()
        mock_prompt.format_messages.return_value = []
        mock_load.return_value = mock_prompt

        from src.graph.nodes import project_explore
        await project_explore(mock_state, mock_config)

    mock_load.assert_called_once_with("project_explore")


class TestRouteProjectExplore:
    def test_routes_to_tools_when_tool_calls_present(self):
        """route_project_explore returns 'explore_tools' when tool_calls present."""
        from src.graph.nodes import route_project_explore

        msg = AIMessage(content="", tool_calls=[{"name": "list_directory", "args": {"path": "proj"}, "id": "1"}])
        state = {"messages": [msg]}

        assert route_project_explore(state) == "explore_tools"

    def test_routes_to_end_when_no_tool_calls(self):
        """route_project_explore returns END when no tool_calls."""
        from src.graph.nodes import route_project_explore
        from langgraph.graph import END

        msg = AIMessage(content="探索完成")
        state = {"messages": [msg]}

        assert route_project_explore(state) == "doc_gen_dispatcher"


class TestRouteByIntent:
    def test_routes_to_project_explore(self):
        """route_by_intent returns 'project_explore' for project_explore intent."""
        from src.graph.nodes import route_by_intent

        state = {"intent": "project_explore"}

        assert route_by_intent(state) == "project_explore"
