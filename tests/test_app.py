"""Chainlit app (src/app.py) 单元测试。

module-level side effects (import chainlit, build_graph()) are handled
by injecting mocks into sys.modules before importing src.app.
"""

import sys
import importlib
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage


# ---------------------------------------------------------------------------
# Fixture: patch chainlit + build_graph, then import (or reload) src.app
# ---------------------------------------------------------------------------

@pytest.fixture()
def app_module():
    """Import src.app with chainlit and build_graph mocked out.

    Returns (module, mock_cl, mock_graph) so each test can configure
    mock_graph.astream and inspect mock_cl.Message interactions.
    """
    # -- mock chainlit module --------------------------------------------------
    mock_cl = MagicMock()

    # cl.Message() must return an object with async .stream_token() and .send()
    mock_answer = MagicMock()
    mock_answer.content = ""
    mock_answer.stream_token = AsyncMock(
        side_effect=lambda token: setattr(mock_answer, "content", mock_answer.content + token)
    )
    mock_answer.send = AsyncMock()
    mock_cl.Message = MagicMock(return_value=mock_answer)

    # cl.LangchainCallbackHandler returns a plain mock (not called in asserts)
    mock_cl.LangchainCallbackHandler = MagicMock(return_value=MagicMock())

    # Decorators: @cl.on_chat_start / @cl.on_message should just return the fn
    mock_cl.on_chat_start = lambda fn: fn
    mock_cl.on_message = lambda fn: fn

    # -- mock graph ------------------------------------------------------------
    mock_graph = MagicMock()
    mock_graph.astream = AsyncMock()  # default: returns empty async iterator

    # -- inject mocks and import -----------------------------------------------
    with patch.dict(sys.modules, {"chainlit": mock_cl}):
        with patch("src.graph.build_graph", return_value=mock_graph):
            # Remove cached module so reload picks up the mocks
            sys.modules.pop("src.app", None)
            import src.app
            importlib.reload(src.app)
            yield src.app, mock_cl, mock_graph

    # cleanup: remove patched module so it doesn't leak between test files
    sys.modules.pop("src.app", None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _astream_from(items):
    """Turn a list of (message, metadata) tuples into an async generator."""
    for item in items:
        yield item


# ===========================================================================
# TestOnMessageCoreFlow
# ===========================================================================

class TestOnMessageCoreFlow:
    """on_message 正常流程测试。"""

    @pytest.mark.asyncio
    async def test_streams_doc_gen_node_content(self, app_module):
        """graph.astream yields 3 AIMessageChunks from doc_gen; all content
        must be forwarded via answer.stream_token()."""
        app, mock_cl, mock_graph = app_module

        chunks = [
            (AIMessageChunk(content="第一段"), {"langgraph_node": "doc_gen"}),
            (AIMessageChunk(content="第二段"), {"langgraph_node": "doc_gen"}),
            (AIMessageChunk(content="第三段"), {"langgraph_node": "doc_gen"}),
        ]
        mock_graph.astream = MagicMock(return_value=_astream_from(chunks))

        user_msg = MagicMock()
        user_msg.content = "请为 ./handler 生成文档"

        await app.on_message(user_msg)

        # Grab the cl.Message instance created inside on_message
        answer_obj = mock_cl.Message.return_value
        # stream_token should have been called 3 times with the chunk contents
        calls = answer_obj.stream_token.call_args_list
        streamed = [c.args[0] for c in calls]
        assert "第一段" in streamed
        assert "第二段" in streamed
        assert "第三段" in streamed

    @pytest.mark.asyncio
    async def test_skips_intent_recognize_node_content(self, app_module):
        """Chunks from intent_recognize should NOT be streamed to the user;
        only doc_gen chunks should appear."""
        app, mock_cl, mock_graph = app_module

        chunks = [
            (AIMessageChunk(content="意图识别中"), {"langgraph_node": "intent_recognize"}),
            (AIMessageChunk(content="文档内容"), {"langgraph_node": "doc_gen"}),
        ]
        mock_graph.astream = MagicMock(return_value=_astream_from(chunks))

        user_msg = MagicMock()
        user_msg.content = "请为 ./handler 生成文档"

        await app.on_message(user_msg)

        answer_obj = mock_cl.Message.return_value
        calls = answer_obj.stream_token.call_args_list
        streamed = [c.args[0] for c in calls]
        assert "文档内容" in streamed
        assert "意图识别中" not in streamed

    @pytest.mark.asyncio
    async def test_skips_human_messages(self, app_module):
        """HumanMessage from doc_gen node should be skipped; only AI content
        should be streamed."""
        app, mock_cl, mock_graph = app_module

        chunks = [
            (HumanMessage(content="用户输入"), {"langgraph_node": "doc_gen"}),
            (AIMessageChunk(content="AI回答"), {"langgraph_node": "doc_gen"}),
        ]
        mock_graph.astream = MagicMock(return_value=_astream_from(chunks))

        user_msg = MagicMock()
        user_msg.content = "请为 ./handler 生成文档"

        await app.on_message(user_msg)

        answer_obj = mock_cl.Message.return_value
        calls = answer_obj.stream_token.call_args_list
        streamed = [c.args[0] for c in calls]
        assert "AI回答" in streamed
        assert "用户输入" not in streamed


# ===========================================================================
# TestOnMessageEdgeCases
# ===========================================================================

class TestOnMessageEdgeCases:
    """on_message 边界情况测试。"""

    @pytest.mark.asyncio
    async def test_fallback_message_when_no_doc_gen_output(self, app_module):
        """When astream produces no doc_gen content (e.g. intent mismatch),
        the user should receive a fallback message mentioning '文档生成'."""
        app, mock_cl, mock_graph = app_module

        # Empty stream — no chunks at all
        mock_graph.astream = MagicMock(return_value=_astream_from([]))

        user_msg = MagicMock()
        user_msg.content = "你好"

        await app.on_message(user_msg)

        answer_obj = mock_cl.Message.return_value
        answer_obj.send.assert_awaited_once()
        # The fallback message should mention doc generation capability
        assert "文档生成" in answer_obj.content or "文档" in answer_obj.content

    @pytest.mark.asyncio
    async def test_handles_graph_error_gracefully(self, app_module):
        """When graph.astream raises, the user should receive a friendly
        error message — not an unhandled traceback."""
        app, mock_cl, mock_graph = app_module

        def _boom(*args, **kwargs):
            raise RuntimeError("模拟错误")

        mock_graph.astream = MagicMock(side_effect=_boom)

        user_msg = MagicMock()
        user_msg.content = "请生成文档"

        # Should NOT raise
        await app.on_message(user_msg)

        answer_obj = mock_cl.Message.return_value
        answer_obj.send.assert_awaited_once()
        # Must be the error-path message, not the fallback message
        assert "错误" in answer_obj.content
        assert "稍后重试" in answer_obj.content
