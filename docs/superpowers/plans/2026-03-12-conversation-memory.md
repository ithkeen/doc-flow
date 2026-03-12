# Conversation Memory Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add session-level multi-turn conversation memory using LangGraph MemorySaver checkpointer so the agent remembers prior dialogue within the same chat session.

**Architecture:** Inject `MemorySaver` checkpointer into `build_graph()` via a new parameter, manage `thread_id` per Chainlit session using `cl.user_session`, and fix `doc_qa` to read the last `HumanMessage` instead of `messages[0]`.

**Tech Stack:** LangGraph MemorySaver (already in `langgraph` package), Chainlit `cl.user_session`, `uuid4`

**Spec:** `docs/superpowers/specs/2026-03-12-conversation-memory-design.md`

---

## Chunk 1: `_get_last_human_message` helper and `doc_qa` node fix

### Task 1: Add `_get_last_human_message` helper to `nodes.py`

**Files:**
- Modify: `src/graph/nodes.py:1-6` (add import)
- Modify: `src/graph/nodes.py:82-84` (add helper before `doc_qa`)
- Test: `tests/graph/test_nodes.py`

- [ ] **Step 1: Write failing tests for `_get_last_human_message`**

Add a new test class at the end of `tests/graph/test_nodes.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/graph/test_nodes.py::TestGetLastHumanMessage -v`
Expected: FAIL with `ImportError: cannot import name '_get_last_human_message'`

- [ ] **Step 3: Implement `_get_last_human_message` in `nodes.py`**

Add import at the top of `src/graph/nodes.py` (after the existing `langchain_core` import on line 12):

```python
from langchain_core.messages import HumanMessage
```

Add the helper function before the `doc_qa` function (between `QA_TOOLS` definition at line 82 and `doc_qa` at line 85):

```python
def _get_last_human_message(messages: list) -> str:
    """返回消息列表中最后一条 HumanMessage 的内容。"""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content
    return ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/graph/test_nodes.py::TestGetLastHumanMessage -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/graph/nodes.py tests/graph/test_nodes.py
git commit -m "feat(graph): add _get_last_human_message helper for multi-turn support"
```

---

### Task 2: Update `doc_qa` to use `_get_last_human_message`

**Files:**
- Modify: `src/graph/nodes.py:92` (change `state["messages"][0].content` to `_get_last_human_message(...)`)
- Test: `tests/graph/test_nodes.py`

- [ ] **Step 1: Write failing test for `doc_qa` with multi-message state**

Add to the existing `TestDocQa` class in `tests/graph/test_nodes.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/graph/test_nodes.py::TestDocQa::test_uses_last_human_message_in_multi_turn -v`
Expected: FAIL — the current code uses `state["messages"][0].content` which returns "第一轮问题"

- [ ] **Step 3: Update `doc_qa` in `nodes.py`**

Change line 92 in `src/graph/nodes.py` from:

```python
    user_input = state["messages"][0].content
```

to:

```python
    user_input = _get_last_human_message(state["messages"])
```

- [ ] **Step 4: Run all `doc_qa` tests to verify they pass**

Run: `uv run pytest tests/graph/test_nodes.py::TestDocQa -v`
Expected: All 4 tests PASS (3 existing + 1 new)

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/graph/nodes.py tests/graph/test_nodes.py
git commit -m "feat(graph): update doc_qa to use last HumanMessage for multi-turn"
```

---

## Chunk 2: `build_graph` checkpointer support

### Task 3: Add `checkpointer` parameter to `build_graph()`

**Files:**
- Modify: `src/graph/graph.py:6-9` (add two imports)
- Modify: `src/graph/graph.py:24` (update function signature)
- Modify: `src/graph/graph.py:45` (update compile call)
- Test: `tests/graph/test_graph.py`

- [ ] **Step 1: Add required imports to `tests/graph/test_graph.py`**

Add these imports at the top of `tests/graph/test_graph.py` (after the existing `from langgraph.graph.state import CompiledStateGraph`):

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig
```

- [ ] **Step 2: Write failing tests for `build_graph` with checkpointer**

Add to `tests/graph/test_graph.py`:

```python
class TestBuildGraphWithCheckpointer:
    """build_graph 传入 checkpointer 参数测试。"""

    def test_accepts_checkpointer_parameter(self):
        from langgraph.checkpoint.memory import MemorySaver
        from src.graph.graph import build_graph

        memory = MemorySaver()
        graph = build_graph(checkpointer=memory)
        assert isinstance(graph, CompiledStateGraph)

    def test_default_none_checkpointer_still_works(self):
        from src.graph.graph import build_graph

        graph = build_graph()
        assert isinstance(graph, CompiledStateGraph)

    @pytest.mark.asyncio
    @patch("src.graph.nodes.ChatOpenAI")
    async def test_multi_turn_preserves_history(self, mock_chat_cls):
        """同一 thread_id 第二次调用时，状态应包含第一次的消息历史。"""
        from langgraph.checkpoint.memory import MemorySaver
        from src.graph.graph import build_graph

        # Mock LLM: intent_recognize returns doc_qa, doc_qa returns simple answer
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=AIMessage(
                content='{"intent": "doc_qa", "confidence": 0.9, "params": {}}'
            )
        )
        mock_llm_with_tools = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm_with_tools.ainvoke = AsyncMock(
            return_value=AIMessage(content="回答")
        )
        mock_chat_cls.return_value = mock_llm

        memory = MemorySaver()
        graph = build_graph(checkpointer=memory)
        config = RunnableConfig(configurable={"thread_id": "test-thread"})

        # Turn 1
        await graph.ainvoke(
            {"messages": [HumanMessage(content="第一轮")]}, config=config
        )
        # Turn 2
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="第二轮")]}, config=config
        )

        # The messages list should contain messages from both turns
        contents = [m.content for m in result["messages"]]
        assert "第一轮" in contents
        assert "第二轮" in contents
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/graph/test_graph.py::TestBuildGraphWithCheckpointer -v`
Expected: FAIL with `TypeError: build_graph() got an unexpected keyword argument 'checkpointer'`

- [ ] **Step 4: Update `build_graph` in `graph.py`**

Three changes to `src/graph/graph.py`:

**Change 1:** Add these two imports to the existing import section (after line 9, before the `from src.graph.nodes` import block). Keep all existing imports:

```python
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
```

**Change 2:** Change the function definition (line 24) from:

```python
def build_graph() -> StateGraph:
```

to:

```python
def build_graph(checkpointer: BaseCheckpointSaver | None = None) -> CompiledStateGraph:
```

Note: The return type annotation is also corrected from `StateGraph` to `CompiledStateGraph` — the old annotation was wrong since `compile()` returns `CompiledStateGraph`.

**Change 3:** Change the compile call (line 45) from:

```python
    return graph.compile()
```

to:

```python
    return graph.compile(checkpointer=checkpointer)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/graph/test_graph.py -v`
Expected: All tests PASS (3 existing + 3 new)

- [ ] **Step 6: Commit**

```bash
git add src/graph/graph.py tests/graph/test_graph.py
git commit -m "feat(graph): add checkpointer parameter to build_graph for multi-turn memory"
```

---

## Chunk 3: Chainlit integration

### Task 4: Add `thread_id` session management and `MemorySaver` to `app.py`

**Files:**
- Modify: `app.py:1-15` (add imports, create MemorySaver, pass to build_graph)
- Modify: `app.py:18-23` (update on_chat_start to set thread_id)
- Modify: `app.py:26-38` (update on_message to pass configurable)
- Test: `tests/test_app.py`

- [ ] **Step 1: Update `app_module` fixture to support `cl.user_session`**

In `tests/test_app.py`, update the `app_module` fixture. Add the following lines in the `mock_cl` setup section (after `mock_cl.on_message = lambda fn: fn`, before `# -- mock graph --`):

```python
    # cl.user_session: simple dict-backed mock
    _session_store = {}
    mock_cl.user_session = MagicMock()
    mock_cl.user_session.set = MagicMock(side_effect=lambda k, v: _session_store.__setitem__(k, v))
    mock_cl.user_session.get = MagicMock(side_effect=lambda k: _session_store.get(k))
```

- [ ] **Step 2: Write failing test for `on_chat_start` setting thread_id**

Add a new test class after the existing test classes:

```python
class TestOnChatStart:
    """on_chat_start 会话初始化测试。"""

    @pytest.mark.asyncio
    async def test_sets_thread_id_in_session(self, app_module):
        """on_chat_start 应在 cl.user_session 中设置 thread_id。"""
        app, mock_cl, mock_graph = app_module

        await app.on_chat_start()

        # Verify cl.user_session.set was called with "thread_id" and a string value
        set_calls = [c for c in mock_cl.user_session.set.call_args_list if c.args[0] == "thread_id"]
        assert len(set_calls) == 1
        thread_id = set_calls[0].args[1]
        assert isinstance(thread_id, str)
        assert len(thread_id) > 0
```

- [ ] **Step 3: Write failing test for `on_message` passing configurable thread_id**

Add to the test file:

```python
class TestOnMessageThreadId:
    """on_message 传递 thread_id 测试。"""

    @pytest.mark.asyncio
    async def test_passes_thread_id_in_config(self, app_module):
        """on_message 应在 config.configurable 中传入 thread_id。"""
        app, mock_cl, mock_graph = app_module

        # Simulate on_chat_start to set thread_id
        await app.on_chat_start()

        mock_graph.astream = MagicMock(return_value=_astream_from([]))

        user_msg = MagicMock()
        user_msg.content = "请为 ./handler 生成文档"

        await app.on_message(user_msg)

        # Inspect the config passed to graph.astream
        astream_call = mock_graph.astream.call_args
        config = astream_call.kwargs.get("config") or astream_call[1].get("config")
        assert "configurable" in config
        assert "thread_id" in config["configurable"]
        assert isinstance(config["configurable"]["thread_id"], str)
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/test_app.py::TestOnChatStart -v`
Expected: FAIL — current `on_chat_start` doesn't set thread_id

Run: `uv run pytest tests/test_app.py::TestOnMessageThreadId -v`
Expected: FAIL — current `on_message` doesn't pass configurable

- [ ] **Step 5: Update `app.py`**

Replace the full `app.py` content:

```python
"""Chainlit 聊天入口。

通过 `chainlit run app.py` 启动，提供浏览器聊天界面。
"""

from uuid import uuid4

import chainlit as cl
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver

from src.graph import build_graph
from src.logs import get_logger

logger = get_logger(__name__)

# Module-level: persists across requests within the Chainlit process
memory = MemorySaver()
graph = build_graph(checkpointer=memory)


@cl.on_chat_start
async def on_chat_start():
    """新会话开始时生成 thread_id 并发送欢迎消息。"""
    cl.user_session.set("thread_id", str(uuid4()))
    await cl.Message(
        content="你好！我是 doc-flow，你可以让我为 Go 源码文件生成 API 文档，或者基于已有文档提问。"
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    """处理用户消息，流式输出 graph 结果。"""
    thread_id = cl.user_session.get("thread_id")

    cb = cl.LangchainCallbackHandler(
        to_ignore=[
            "ChannelRead",
            "RunnableLambda",
            "ChannelWrite",
            "__start__",
            "_execute",
        ]
    )
    config = RunnableConfig(
        callbacks=[cb],
        configurable={"thread_id": thread_id},
    )
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
                and metadata["langgraph_node"] in ("doc_gen", "doc_qa")
            ):
                await answer.stream_token(msg.content)
    except Exception:
        logger.exception("graph 执行出错")
        answer.content = "抱歉，处理过程中出现错误，请稍后重试。"

    if not answer.content:
        answer.content = "抱歉，我目前支持文档生成和文档问答功能。你可以让我为某个文件生成文档，或者基于已有文档提问。"

    await answer.send()
```

Note: the existing `patch("src.graph.build_graph", return_value=mock_graph)` in the test fixture already handles the new `MemorySaver` import in `app.py` because it replaces the entire `build_graph` call. No additional mocking is needed.

- [ ] **Step 6: Run all app tests to verify they pass**

Run: `uv run pytest tests/test_app.py -v`
Expected: All tests PASS (existing + 2 new)

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat(app): add MemorySaver and thread_id for multi-turn conversation memory"
```

---

## Chunk 4: Integration verification and cleanup

### Task 5: Full integration verification

**Files:**
- Read-only verification, no new files

- [ ] **Step 1: Run full test suite one final time**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS, zero failures

- [ ] **Step 2: Verify no import cycles or runtime errors**

Run: `uv run python -c "from src.graph import build_graph; from langgraph.checkpoint.memory import MemorySaver; g = build_graph(checkpointer=MemorySaver()); print('OK')"`
Expected: Prints `OK`

- [ ] **Step 3: Verify Chainlit app can be imported without errors**

Run:
```bash
uv run python -c "
import sys
from unittest.mock import MagicMock
mock_cl = MagicMock()
mock_cl.on_chat_start = lambda fn: fn
mock_cl.on_message = lambda fn: fn
sys.modules['chainlit'] = mock_cl
from app import graph
print('OK')
"
```
Expected: Prints `OK` (basic import check — full runtime test requires `chainlit run`)

- [ ] **Step 4: Review all changed files for consistency**

Verify:
- `src/graph/graph.py`: `build_graph(checkpointer=None)`, type-annotated with `BaseCheckpointSaver | None`, return type is `CompiledStateGraph`
- `src/graph/nodes.py`: `_get_last_human_message()` exists, `doc_qa` uses it
- `app.py`: `MemorySaver()` at module level, `thread_id` in `on_chat_start`, `configurable` in `on_message`
- All tests pass and cover the new functionality
