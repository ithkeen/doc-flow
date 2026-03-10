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
