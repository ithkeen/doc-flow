# Chainlit Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Chainlit chat UI to doc-flow so users can interact with the LangGraph agent via browser.

**Architecture:** Chainlit serves as a thin UI layer over the existing compiled graph. `src/app.py` defines `@cl.on_chat_start` (welcome) and `@cl.on_message` (streams graph output). No graph modifications needed.

**Tech Stack:** Chainlit, LangGraph `astream()` with `stream_mode="messages"`, `cl.LangchainCallbackHandler`

---

### Task 1: Add chainlit dependency

**Files:**
- Modify: `pyproject.toml:7-13`

**Step 1: Add chainlit to dependencies**

In `pyproject.toml`, add `"chainlit"` to the `dependencies` list:

```toml
dependencies = [
    "chainlit",
    "langchain>=1.2.10",
    "langchain-openai>=1.1.11",
    "langgraph>=1.0.10",
    "langgraph-cli[inmem]>=0.4.15",
    "pydantic-settings>=2.7.0",
]
```

**Step 2: Install dependencies**

Run: `uv sync`
Expected: Resolves and installs chainlit + its transitive deps. No errors.

**Step 3: Verify chainlit is importable**

Run: `uv run python -c "import chainlit; print(chainlit.__version__)"`
Expected: Prints a version string (e.g., `2.x.x`), no ImportError.

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add chainlit dependency"
```

---

### Task 2: Write failing tests for on_message core flow

**Files:**
- Create: `tests/test_app.py`

**Step 1: Write the failing test**

Create `tests/test_app.py` with the core streaming flow test. We mock `build_graph` at module level to avoid importing the real graph (which needs env vars). We also mock the `chainlit` module since it's not available in test context without a running server.

```python
"""Chainlit 入口 (src/app.py) 单元测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessageChunk, HumanMessage


@pytest.fixture
def mock_chainlit():
    """Mock chainlit module objects."""
    mock_msg_instance = AsyncMock()
    mock_msg_instance.content = ""
    mock_msg_instance.stream_token = AsyncMock(
        side_effect=lambda token: setattr(
            mock_msg_instance, "content", mock_msg_instance.content + token
        )
    )
    mock_msg_instance.send = AsyncMock()

    mock_msg_cls = MagicMock(return_value=mock_msg_instance)
    mock_cb = MagicMock()

    return mock_msg_cls, mock_msg_instance, mock_cb


class TestOnMessageCoreFlow:
    """on_message 核心流式输出测试。"""

    @pytest.mark.asyncio
    async def test_streams_doc_gen_node_content(self, mock_chainlit):
        """只有 doc_gen 节点的 AI 内容被流式输出。"""
        mock_msg_cls, mock_msg_instance, mock_cb = mock_chainlit

        chunks = [
            (AIMessageChunk(content="文档"), {"langgraph_node": "doc_gen"}),
            (AIMessageChunk(content="生成"), {"langgraph_node": "doc_gen"}),
            (AIMessageChunk(content="完毕"), {"langgraph_node": "doc_gen"}),
        ]

        mock_graph = MagicMock()

        async def fake_astream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        mock_graph.astream = fake_astream

        with patch("src.app.graph", mock_graph), \
             patch("src.app.cl") as patched_cl:
            patched_cl.Message = mock_msg_cls
            patched_cl.LangchainCallbackHandler = MagicMock(return_value=mock_cb)

            from src.app import on_message

            user_msg = MagicMock()
            user_msg.content = "请为 ./handler 生成文档"
            await on_message(user_msg)

        assert mock_msg_instance.content == "文档生成完毕"
        mock_msg_instance.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_intent_recognize_node_content(self, mock_chainlit):
        """intent_recognize 节点的内容不应被流式输出。"""
        mock_msg_cls, mock_msg_instance, mock_cb = mock_chainlit

        chunks = [
            (AIMessageChunk(content="识别中"), {"langgraph_node": "intent_recognize"}),
            (AIMessageChunk(content="文档OK"), {"langgraph_node": "doc_gen"}),
        ]

        mock_graph = MagicMock()

        async def fake_astream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        mock_graph.astream = fake_astream

        with patch("src.app.graph", mock_graph), \
             patch("src.app.cl") as patched_cl:
            patched_cl.Message = mock_msg_cls
            patched_cl.LangchainCallbackHandler = MagicMock(return_value=mock_cb)

            from src.app import on_message

            user_msg = MagicMock()
            user_msg.content = "请为 ./handler 生成文档"
            await on_message(user_msg)

        assert mock_msg_instance.content == "文档OK"

    @pytest.mark.asyncio
    async def test_skips_human_messages(self, mock_chainlit):
        """HumanMessage 不应被流式输出。"""
        mock_msg_cls, mock_msg_instance, mock_cb = mock_chainlit

        chunks = [
            (HumanMessage(content="用户消息"), {"langgraph_node": "doc_gen"}),
            (AIMessageChunk(content="AI回复"), {"langgraph_node": "doc_gen"}),
        ]

        mock_graph = MagicMock()

        async def fake_astream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        mock_graph.astream = fake_astream

        with patch("src.app.graph", mock_graph), \
             patch("src.app.cl") as patched_cl:
            patched_cl.Message = mock_msg_cls
            patched_cl.LangchainCallbackHandler = MagicMock(return_value=mock_cb)

            from src.app import on_message

            user_msg = MagicMock()
            user_msg.content = "请为 ./handler 生成文档"
            await on_message(user_msg)

        assert mock_msg_instance.content == "AI回复"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_app.py -v`
Expected: FAIL — `src/app.py` is empty, `from src.app import on_message` will fail with ImportError.

---

### Task 3: Write failing test for intent mismatch fallback

**Files:**
- Modify: `tests/test_app.py`

**Step 1: Add the failing test**

Append to `tests/test_app.py`:

```python
class TestOnMessageEdgeCases:
    """on_message 边界情况测试。"""

    @pytest.mark.asyncio
    async def test_fallback_message_when_no_doc_gen_output(self, mock_chainlit):
        """intent 不匹配时（graph 直接 END），用户看到提示消息。"""
        mock_msg_cls, mock_msg_instance, mock_cb = mock_chainlit

        mock_graph = MagicMock()

        async def fake_astream(*args, **kwargs):
            return
            yield  # makes this an async generator

        mock_graph.astream = fake_astream

        with patch("src.app.graph", mock_graph), \
             patch("src.app.cl") as patched_cl:
            patched_cl.Message = mock_msg_cls
            patched_cl.LangchainCallbackHandler = MagicMock(return_value=mock_cb)

            from src.app import on_message

            user_msg = MagicMock()
            user_msg.content = "你好"
            await on_message(user_msg)

        assert mock_msg_instance.content != ""
        assert "文档生成" in mock_msg_instance.content
        mock_msg_instance.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_graph_error_gracefully(self, mock_chainlit):
        """graph 抛出异常时，用户看到友好错误提示。"""
        mock_msg_cls, mock_msg_instance, mock_cb = mock_chainlit

        mock_graph = MagicMock()

        async def fake_astream(*args, **kwargs):
            raise RuntimeError("LLM connection failed")
            yield  # makes this an async generator

        mock_graph.astream = fake_astream

        with patch("src.app.graph", mock_graph), \
             patch("src.app.cl") as patched_cl:
            patched_cl.Message = mock_msg_cls
            patched_cl.LangchainCallbackHandler = MagicMock(return_value=mock_cb)

            from src.app import on_message

            user_msg = MagicMock()
            user_msg.content = "请为 ./handler 生成文档"
            await on_message(user_msg)

        assert mock_msg_instance.send.assert_called_once
        # Should contain an error-related message, not a traceback
        assert mock_msg_instance.content != ""
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_app.py::TestOnMessageEdgeCases -v`
Expected: FAIL — same ImportError since `src/app.py` is still empty.

---

### Task 4: Implement src/app.py

**Files:**
- Modify: `src/app.py`

**Step 1: Write the implementation**

```python
"""Chainlit 聊天入口。

通过 `chainlit run src/app.py` 启动，提供浏览器聊天界面。
"""

import chainlit as cl
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from src.graph import build_graph
from src.logs import get_logger

logger = get_logger(__name__)

graph = build_graph()


@cl.on_chat_start
async def on_chat_start():
    """新会话开始时发送欢迎消息。"""
    await cl.Message(
        content="你好！我是 doc-flow，请告诉我你想为哪个 Go 项目目录生成文档。"
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    """处理用户消息，流式输出 graph 结果。"""
    cb = cl.LangchainCallbackHandler(
        to_ignore=[
            "ChannelRead",
            "RunnableLambda",
            "ChannelWrite",
            "__start__",
            "_execute",
        ]
    )
    config = RunnableConfig(callbacks=[cb])
    answer = cl.Message(content="")

    try:
        async for msg, metadata in graph.astream(
            {"messages": [HumanMessage(content=message.content)]},
            stream_mode="messages",
            config=config,
        ):
            if (
                msg.content
                and not isinstance(msg, HumanMessage)
                and metadata["langgraph_node"] == "doc_gen"
            ):
                await answer.stream_token(msg.content)
    except Exception:
        logger.exception("graph 执行出错")
        answer.content = "抱歉，处理过程中出现错误，请稍后重试。"

    if not answer.content:
        answer.content = "抱歉，我目前只支持文档生成功能。请告诉我你想为哪个目录生成文档。"

    await answer.send()
```

**Step 2: Run all tests to verify they pass**

Run: `uv run pytest tests/test_app.py -v`
Expected: All 5 tests PASS.

**Step 3: Commit**

```bash
git add src/app.py tests/test_app.py
git commit -m "feat: implement Chainlit chat UI with streaming graph output"
```

---

### Task 5: Add pytest-asyncio dev dependency

**Files:**
- Modify: `pyproject.toml:15-18`

Note: Task 2-3 tests use `@pytest.mark.asyncio`. The `pytest-asyncio` package is required.

**Step 1: Add pytest-asyncio to dev dependencies**

```toml
[dependency-groups]
dev = [
    "pytest>=9.0.2",
    "pytest-asyncio>=0.25.0",
]
```

**Step 2: Install and verify**

Run: `uv sync && uv run pytest tests/test_app.py -v`
Expected: All 5 tests PASS with no `asyncio` warnings.

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add pytest-asyncio dev dependency"
```

---

### Task 6: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md:9-18` (Commands section)
- Modify: `CLAUDE.md:7` (Project Overview — entry points note)

**Step 1: Add chainlit command to Commands section**

After the `uv run langgraph dev` line, add:

```bash
uv run chainlit run src/app.py -w     # Run Chainlit chat UI (hot reload)
```

**Step 2: Update Project Overview**

Change "Entry points (`src/app.py`, `main.py`) are not yet wired up." to:

"Entry point `src/app.py` serves the Chainlit chat UI; `main.py` is not yet wired up."

**Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add Chainlit run command and update entry point status"
```

---

### Task 7: Smoke test — run Chainlit server

**Step 1: Start the Chainlit server**

Run: `uv run chainlit run src/app.py -w`
Expected: Server starts, prints a URL (e.g., `http://localhost:8000`). No import errors.

**Step 2: Verify in browser**

Open the URL. Expected: Chat UI loads, welcome message "你好！我是 doc-flow..." appears.

**Step 3: (Optional) Send a test message**

Type "请为 ./handler 生成文档" and verify the streaming response + tool call steps appear.

Note: This requires a valid `LLM_API_KEY` in `.env`. If not available, just verify the server starts and the welcome message appears.
