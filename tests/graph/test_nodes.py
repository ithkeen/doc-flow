"""graph 节点单元测试。"""

import pytest
from typing import get_type_hints, Annotated
from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage


class TestStateDefinition:
    """State 类型结构验证。"""

    def test_state_has_messages_field(self):
        from src.graph.nodes import State

        hints = get_type_hints(State, include_extras=True)
        assert "messages" in hints

    def test_state_has_intent_field(self):
        from src.graph.nodes import State

        hints = get_type_hints(State)
        assert "intent" in hints

    def test_state_has_confidence_field(self):
        from src.graph.nodes import State

        hints = get_type_hints(State)
        assert "confidence" in hints

    def test_state_has_params_field(self):
        from src.graph.nodes import State

        hints = get_type_hints(State)
        assert "params" in hints


class TestIntentRecognize:
    """意图识别节点测试。"""

    @patch("src.graph.nodes.ChatOpenAI")
    def test_returns_intent_fields(self, mock_chat_cls):
        from src.graph.nodes import intent_recognize

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(
            content='{"intent": "doc_gen", "confidence": 0.95, "params": {"directory_path": "./handler"}}'
        )
        mock_chat_cls.return_value = mock_llm

        state = {
            "messages": [HumanMessage(content="请为 ./handler 生成文档")],
            "intent": "",
            "confidence": 0.0,
            "params": {},
        }

        result = intent_recognize(state)

        assert result["intent"] == "doc_gen"
        assert result["confidence"] == 0.95
        assert result["params"]["directory_path"] == "./handler"

    @patch("src.graph.nodes.ChatOpenAI")
    def test_calls_llm_with_intent_prompt(self, mock_chat_cls):
        from src.graph.nodes import intent_recognize

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(
            content='{"intent": "unknown", "confidence": 0.3, "params": {}}'
        )
        mock_chat_cls.return_value = mock_llm

        state = {
            "messages": [HumanMessage(content="你好")],
            "intent": "",
            "confidence": 0.0,
            "params": {},
        }

        intent_recognize(state)

        mock_llm.invoke.assert_called_once()
        call_args = mock_llm.invoke.call_args[0][0]
        assert len(call_args) == 2
        assert call_args[0].type == "system"
        assert call_args[1].type == "human"

    @patch("src.graph.nodes.ChatOpenAI")
    def test_parses_json_wrapped_in_markdown_code_block(self, mock_chat_cls):
        """LLM 返回 ```json ... ``` 包裹的 JSON 时应正确解析。"""
        from src.graph.nodes import intent_recognize

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(
            content='```json\n{"intent": "doc_gen", "confidence": 0.95, "params": {"file_path": "handler.go"}}\n```'
        )
        mock_chat_cls.return_value = mock_llm

        state = {
            "messages": [HumanMessage(content="请为 handler.go 生成文档")],
            "intent": "",
            "confidence": 0.0,
            "params": {},
        }

        result = intent_recognize(state)

        assert result["intent"] == "doc_gen"
        assert result["confidence"] == 0.95
        assert result["params"]["file_path"] == "handler.go"

    @patch("src.graph.nodes.ChatOpenAI")
    def test_handles_invalid_json_gracefully(self, mock_chat_cls):
        from src.graph.nodes import intent_recognize

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content="这不是 JSON")
        mock_chat_cls.return_value = mock_llm

        state = {
            "messages": [HumanMessage(content="你好")],
            "intent": "",
            "confidence": 0.0,
            "params": {},
        }

        result = intent_recognize(state)

        assert result["intent"] == "unknown"
        assert result["confidence"] == 0.0


class TestDocGen:
    """文档生成节点测试。"""

    @patch("src.graph.nodes.ChatOpenAI")
    def test_returns_messages_with_ai_response(self, mock_chat_cls):
        from src.graph.nodes import doc_gen

        mock_llm = MagicMock()
        mock_llm_with_tools = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm_with_tools

        ai_msg = AIMessage(content="已为您生成文档。")
        mock_llm_with_tools.invoke.return_value = ai_msg
        mock_chat_cls.return_value = mock_llm

        state = {
            "messages": [HumanMessage(content="请为 ./handler 生成文档")],
            "intent": "doc_gen",
            "confidence": 0.95,
            "params": {"directory_path": "./handler"},
        }

        result = doc_gen(state)

        assert "messages" in result
        assert result["messages"] == [ai_msg]

    @patch("src.graph.nodes.ChatOpenAI")
    def test_binds_tools_to_llm(self, mock_chat_cls):
        from src.graph.nodes import doc_gen

        mock_llm = MagicMock()
        mock_llm_with_tools = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm_with_tools.invoke.return_value = AIMessage(content="done")
        mock_chat_cls.return_value = mock_llm

        state = {
            "messages": [HumanMessage(content="生成文档")],
            "intent": "doc_gen",
            "confidence": 0.95,
            "params": {"directory_path": "./handler"},
        }

        doc_gen(state)

        mock_llm.bind_tools.assert_called_once()
        tools_arg = mock_llm.bind_tools.call_args[0][0]
        tool_names = [t.name for t in tools_arg]
        assert "scan_directory" in tool_names
        assert "read_file" in tool_names
        assert "save_document" in tool_names
        assert "read_document" in tool_names
        assert "list_documents" in tool_names

    @patch("src.graph.nodes.ChatOpenAI")
    def test_prepends_system_prompt_to_messages(self, mock_chat_cls):
        from src.graph.nodes import doc_gen

        mock_llm = MagicMock()
        mock_llm_with_tools = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm_with_tools.invoke.return_value = AIMessage(content="done")
        mock_chat_cls.return_value = mock_llm

        human_msg = HumanMessage(content="生成文档")
        state = {
            "messages": [human_msg],
            "intent": "doc_gen",
            "confidence": 0.95,
            "params": {"directory_path": "./handler"},
        }

        doc_gen(state)

        invoke_args = mock_llm_with_tools.invoke.call_args[0][0]
        assert invoke_args[0].type == "system"
        assert invoke_args[-1] == human_msg


class TestRouteByIntent:
    """意图路由函数测试。"""

    def test_routes_to_doc_gen_for_doc_gen_intent(self):
        from src.graph.nodes import route_by_intent

        state = {"intent": "doc_gen", "confidence": 0.9, "params": {}, "messages": []}
        assert route_by_intent(state) == "doc_gen"

    def test_routes_to_end_for_unknown_intent(self):
        from src.graph.nodes import route_by_intent
        from langgraph.graph import END

        state = {"intent": "unknown", "confidence": 0.3, "params": {}, "messages": []}
        assert route_by_intent(state) == END

    def test_routes_to_end_for_empty_intent(self):
        from src.graph.nodes import route_by_intent
        from langgraph.graph import END

        state = {"intent": "", "confidence": 0.0, "params": {}, "messages": []}
        assert route_by_intent(state) == END


class TestRouteDocGen:
    """doc_gen 路由函数测试。"""

    def test_routes_to_tools_when_tool_calls_present(self):
        from src.graph.nodes import route_doc_gen

        ai_msg = AIMessage(content="", tool_calls=[{"name": "scan_directory", "args": {"directory_path": "./handler"}, "id": "1"}])
        state = {"messages": [ai_msg], "intent": "doc_gen", "confidence": 0.9, "params": {}}
        assert route_doc_gen(state) == "tools"

    def test_routes_to_end_when_no_tool_calls(self):
        from src.graph.nodes import route_doc_gen
        from langgraph.graph import END

        ai_msg = AIMessage(content="文档生成完毕。")
        state = {"messages": [ai_msg], "intent": "doc_gen", "confidence": 0.9, "params": {}}
        assert route_doc_gen(state) == END
