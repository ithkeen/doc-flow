"""graph 节点单元测试。"""

import pytest
from typing import get_type_hints, Annotated
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig


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

    @pytest.mark.asyncio
    @patch("src.graph.nodes.ChatOpenAI")
    async def test_returns_intent_fields(self, mock_chat_cls):
        from src.graph.nodes import intent_recognize

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=AIMessage(
                content='{"intent": "doc_gen", "confidence": 0.95, "params": {"file_path": "./handler/api.go"}}'
            )
        )
        mock_chat_cls.return_value = mock_llm

        state = {
            "messages": [HumanMessage(content="请为 ./handler 生成文档")],
            "intent": "",
            "confidence": 0.0,
            "params": {},
        }

        result = await intent_recognize(state, RunnableConfig())

        assert result["intent"] == "doc_gen"
        assert result["confidence"] == 0.95
        assert result["params"]["file_path"] == "./handler/api.go"

    @pytest.mark.asyncio
    @patch("src.graph.nodes.ChatOpenAI")
    async def test_calls_llm_with_intent_prompt(self, mock_chat_cls):
        from src.graph.nodes import intent_recognize

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=AIMessage(
                content='{"intent": "unknown", "confidence": 0.3, "params": {}}'
            )
        )
        mock_chat_cls.return_value = mock_llm

        state = {
            "messages": [HumanMessage(content="你好")],
            "intent": "",
            "confidence": 0.0,
            "params": {},
        }

        await intent_recognize(state, RunnableConfig())

        mock_llm.ainvoke.assert_called_once()
        call_args = mock_llm.ainvoke.call_args[0][0]
        assert len(call_args) == 2
        assert call_args[0].type == "system"
        assert call_args[1].type == "human"

    @pytest.mark.asyncio
    @patch("src.graph.nodes.ChatOpenAI")
    async def test_parses_json_wrapped_in_markdown_code_block(self, mock_chat_cls):
        """LLM 返回 ```json ... ``` 包裹的 JSON 时应正确解析。"""
        from src.graph.nodes import intent_recognize

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=AIMessage(
                content='```json\n{"intent": "doc_gen", "confidence": 0.95, "params": {"file_path": "handler.go"}}\n```'
            )
        )
        mock_chat_cls.return_value = mock_llm

        state = {
            "messages": [HumanMessage(content="请为 handler.go 生成文档")],
            "intent": "",
            "confidence": 0.0,
            "params": {},
        }

        result = await intent_recognize(state, RunnableConfig())

        assert result["intent"] == "doc_gen"
        assert result["confidence"] == 0.95
        assert result["params"]["file_path"] == "handler.go"

    @pytest.mark.asyncio
    @patch("src.graph.nodes.ChatOpenAI")
    async def test_handles_invalid_json_gracefully(self, mock_chat_cls):
        from src.graph.nodes import intent_recognize

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=AIMessage(content="这不是 JSON")
        )
        mock_chat_cls.return_value = mock_llm

        state = {
            "messages": [HumanMessage(content="你好")],
            "intent": "",
            "confidence": 0.0,
            "params": {},
        }

        result = await intent_recognize(state, RunnableConfig())

        assert result["intent"] == "unknown"
        assert result["confidence"] == 0.0


class TestDocGen:
    """文档生成节点测试。"""

    @pytest.mark.asyncio
    @patch("src.graph.nodes.ChatOpenAI")
    async def test_returns_messages_with_ai_response(self, mock_chat_cls):
        from src.graph.nodes import doc_gen

        mock_llm = MagicMock()
        mock_llm_with_tools = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm_with_tools

        ai_msg = AIMessage(content="已为您生成文档。")
        mock_llm_with_tools.ainvoke = AsyncMock(return_value=ai_msg)
        mock_chat_cls.return_value = mock_llm

        state = {
            "messages": [HumanMessage(content="请为 ./handler 生成文档")],
            "intent": "doc_gen",
            "confidence": 0.95,
            "params": {"file_path": "./handler/api.go"},
        }

        result = await doc_gen(state, RunnableConfig())

        assert "messages" in result
        assert result["messages"] == [ai_msg]

    @pytest.mark.asyncio
    @patch("src.graph.nodes.ChatOpenAI")
    async def test_binds_tools_to_llm(self, mock_chat_cls):
        from src.graph.nodes import doc_gen

        mock_llm = MagicMock()
        mock_llm_with_tools = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm_with_tools.ainvoke = AsyncMock(
            return_value=AIMessage(content="done")
        )
        mock_chat_cls.return_value = mock_llm

        state = {
            "messages": [HumanMessage(content="生成文档")],
            "intent": "doc_gen",
            "confidence": 0.95,
            "params": {"file_path": "./handler/api.go"},
        }

        await doc_gen(state, RunnableConfig())

        mock_llm.bind_tools.assert_called_once()
        tools_arg = mock_llm.bind_tools.call_args[0][0]
        tool_names = [t.name for t in tools_arg]
        assert "scan_directory" in tool_names
        assert "read_file" in tool_names
        assert "save_document" in tool_names
        assert "read_document" in tool_names
        assert "list_documents" in tool_names

    @pytest.mark.asyncio
    @patch("src.graph.nodes.ChatOpenAI")
    async def test_prepends_system_prompt_to_messages(self, mock_chat_cls):
        from src.graph.nodes import doc_gen

        mock_llm = MagicMock()
        mock_llm_with_tools = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm_with_tools.ainvoke = AsyncMock(
            return_value=AIMessage(content="done")
        )
        mock_chat_cls.return_value = mock_llm

        human_msg = HumanMessage(content="生成文档")
        state = {
            "messages": [human_msg],
            "intent": "doc_gen",
            "confidence": 0.95,
            "params": {"file_path": "./handler/api.go"},
        }

        await doc_gen(state, RunnableConfig())

        invoke_args = mock_llm_with_tools.ainvoke.call_args[0][0]
        assert invoke_args[0].type == "system"
        assert invoke_args[-1] == human_msg


class TestDocQa:
    """文档问答节点测试。"""

    @pytest.mark.asyncio
    @patch("src.graph.nodes.ChatOpenAI")
    async def test_returns_messages_with_ai_response(self, mock_chat_cls):
        from src.graph.nodes import doc_qa

        mock_llm = MagicMock()
        mock_llm_with_tools = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm_with_tools

        ai_msg = AIMessage(content="CreateUser 接口需要 username 和 email 两个参数。")
        mock_llm_with_tools.ainvoke = AsyncMock(return_value=ai_msg)
        mock_chat_cls.return_value = mock_llm

        state = {
            "messages": [HumanMessage(content="CreateUser 的请求参数有哪些？")],
            "intent": "doc_qa",
            "confidence": 0.9,
            "params": {},
        }

        result = await doc_qa(state, RunnableConfig())

        assert "messages" in result
        assert result["messages"] == [ai_msg]

    @pytest.mark.asyncio
    @patch("src.graph.nodes.ChatOpenAI")
    async def test_binds_qa_tools_to_llm(self, mock_chat_cls):
        from src.graph.nodes import doc_qa

        mock_llm = MagicMock()
        mock_llm_with_tools = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm_with_tools.ainvoke = AsyncMock(
            return_value=AIMessage(content="done")
        )
        mock_chat_cls.return_value = mock_llm

        state = {
            "messages": [HumanMessage(content="CreateUser 怎么用？")],
            "intent": "doc_qa",
            "confidence": 0.9,
            "params": {},
        }

        await doc_qa(state, RunnableConfig())

        mock_llm.bind_tools.assert_called_once()
        tools_arg = mock_llm.bind_tools.call_args[0][0]
        tool_names = [t.name for t in tools_arg]
        assert "read_document" in tool_names
        assert "list_documents" in tool_names
        assert len(tool_names) == 2

    @pytest.mark.asyncio
    @patch("src.graph.nodes.ChatOpenAI")
    async def test_prepends_system_prompt_to_messages(self, mock_chat_cls):
        from src.graph.nodes import doc_qa

        mock_llm = MagicMock()
        mock_llm_with_tools = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm_with_tools.ainvoke = AsyncMock(
            return_value=AIMessage(content="done")
        )
        mock_chat_cls.return_value = mock_llm

        human_msg = HumanMessage(content="CreateUser 的参数有哪些？")
        state = {
            "messages": [human_msg],
            "intent": "doc_qa",
            "confidence": 0.9,
            "params": {},
        }

        await doc_qa(state, RunnableConfig())

        invoke_args = mock_llm_with_tools.ainvoke.call_args[0][0]
        assert invoke_args[0].type == "system"
        assert invoke_args[-1] == human_msg

    @pytest.mark.asyncio
    @patch("src.graph.nodes.ChatOpenAI")
    async def test_uses_last_human_message_in_multi_turn(self, mock_chat_cls):
        """多轮对话时，doc_qa 应使用最后一条 HumanMessage，而非 messages[0]。"""
        from src.graph.nodes import doc_qa

        mock_llm = MagicMock()
        mock_llm_with_tools = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm_with_tools.ainvoke = AsyncMock(
            return_value=AIMessage(content="done")
        )
        mock_chat_cls.return_value = mock_llm

        state = {
            "messages": [
                HumanMessage(content="第一轮问题"),
                AIMessage(content="第一轮回答"),
                HumanMessage(content="第二轮问题"),
            ],
            "intent": "doc_qa",
            "confidence": 0.9,
            "params": {},
        }

        await doc_qa(state, RunnableConfig())

        invoke_args = mock_llm_with_tools.ainvoke.call_args[0][0]
        # system prompt 中的 user_input 应包含"第二轮问题"而非"第一轮问题"
        system_and_user_prompt = invoke_args[0:2]  # system + user prompt messages
        user_prompt_content = system_and_user_prompt[1].content
        assert "第二轮问题" in user_prompt_content
        assert "第一轮问题" not in user_prompt_content


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

    def test_routes_to_doc_qa_for_doc_qa_intent(self):
        from src.graph.nodes import route_by_intent

        state = {"intent": "doc_qa", "confidence": 0.9, "params": {}, "messages": []}
        assert route_by_intent(state) == "doc_qa"


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


class TestRouteDocQa:
    """doc_qa 路由函数测试。"""

    def test_routes_to_qa_tools_when_tool_calls_present(self):
        from src.graph.nodes import route_doc_qa

        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "read_document", "args": {"module_name": "user", "api_name": "CreateUser"}, "id": "1"}],
        )
        state = {"messages": [ai_msg], "intent": "doc_qa", "confidence": 0.9, "params": {}}
        assert route_doc_qa(state) == "qa_tools"

    def test_routes_to_end_when_no_tool_calls(self):
        from src.graph.nodes import route_doc_qa
        from langgraph.graph import END

        ai_msg = AIMessage(content="根据文档，CreateUser 接口需要以下参数...")
        state = {"messages": [ai_msg], "intent": "doc_qa", "confidence": 0.9, "params": {}}
        assert route_doc_qa(state) == END


class TestGetLastHumanMessage:
    """_get_last_human_message 辅助函数测试。"""

    def test_returns_last_human_message_from_mixed_list(self):
        from src.graph.nodes import _get_last_human_message

        messages = [
            HumanMessage(content="第一条"),
            AIMessage(content="AI 回复"),
            HumanMessage(content="第二条"),
        ]
        assert _get_last_human_message(messages) == "第二条"

    def test_returns_empty_string_for_empty_list(self):
        from src.graph.nodes import _get_last_human_message

        assert _get_last_human_message([]) == ""

    def test_returns_empty_string_when_no_human_message(self):
        from src.graph.nodes import _get_last_human_message

        messages = [AIMessage(content="AI only")]
        assert _get_last_human_message(messages) == ""

    def test_returns_content_for_single_human_message(self):
        from src.graph.nodes import _get_last_human_message

        messages = [HumanMessage(content="唯一一条")]
        assert _get_last_human_message(messages) == "唯一一条"
