# Chat Intent Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `chat` intent to doc-flow that handles general conversation with soft guidance toward documentation features.

**Architecture:** New `chat` async node in the LangGraph StateGraph, routed via `route_by_intent` when intent is `"chat"`. No tools bound — pure LLM dialogue using full message history. Chat prompt guides users toward doc_gen/doc_qa features.

**Tech Stack:** LangGraph, LangChain (ChatOpenAI), Chainlit, pytest + pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-03-12-chat-intent-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/prompts/system/chat.md` | Create | Chat system prompt with role + guidance strategy |
| `src/prompts/user/chat.md` | Create | Chat user prompt template (`{user_input}`) |
| `src/prompts/system/intent.md` | Modify | Add `chat` intent description |
| `src/graph/nodes.py` | Modify | Add `chat` node function, update `INTENT_LIST`, extend `route_by_intent` |
| `src/graph/graph.py` | Modify | Add `chat` node + `chat → END` edge, extend conditional edges |
| `app.py` | Modify | Add `"chat"` to streaming filter, update fallback message |
| `tests/graph/test_nodes.py` | Modify | Add `TestChat` class, extend `TestRouteByIntent` |
| `tests/graph/test_graph.py` | Modify | Add chat node membership check |
| `tests/test_app.py` | Modify | Add chat streaming test, update fallback assertion |

---

## Chunk 1: Prompts and Intent Recognition

### Task 1: Create chat prompt templates

**Files:**
- Create: `src/prompts/system/chat.md`
- Create: `src/prompts/user/chat.md`

- [ ] **Step 1: Create the chat system prompt**

Create `src/prompts/system/chat.md`:

```markdown
你是 doc-flow，一个专注于 Go 代码文档的 AI 助手。当前你在与用户进行自由对话。

## 你的能力

你可以聊任何话题，友好、有帮助、专业。

## 引导策略

你还拥有两项核心能力：
- 为 Go 源码文件生成 API 文档（用户只需告诉你文件路径）
- 回答已有文档相关的问题

在对话中，当话题自然涉及到代码、文档、API 等内容时，可以适时提及这些能力。不需要每条回复都提，只在话题相关或自然衔接时柔和引出即可。

## 约束

- 回答使用中文
- 保持对话自然流畅，不要生硬地推销功能
```

- [ ] **Step 2: Create the chat user prompt**

Create `src/prompts/user/chat.md`:

```
用户输入：{user_input}
```

- [ ] **Step 3: Verify prompt loading works**

Run: `uv run python -c "from src.prompts import load_prompt; p = load_prompt('chat'); print(p.format_messages(user_input='你好'))"`
Expected: Prints list with SystemMessage and HumanMessage, no errors.

- [ ] **Step 4: Commit**

```bash
git add src/prompts/system/chat.md src/prompts/user/chat.md
git commit -m "feat: add chat prompt templates

System prompt defines role as general conversation assistant with
soft guidance toward doc generation and QA features."
```

### Task 2: Update intent recognition prompt

**Files:**
- Modify: `src/prompts/system/intent.md`

- [ ] **Step 1: Add chat intent to the intent prompt**

In `src/prompts/system/intent.md`, change the intent list section from:

```
可用意图：
- doc_gen：用户要求为某个文件或模块生成 API 文档
- doc_qa：用户基于已有文档提问（查询接口参数、用法、错误码等）
```

to:

```
可用意图：
- doc_gen：用户要求为某个文件或模块生成 API 文档
- doc_qa：用户基于已有文档提问（查询接口参数、用法、错误码等）
- chat：用户的输入不属于以上两种意图，是一般性对话、闲聊、问候、技术讨论或其他内容
```

- [ ] **Step 2: Commit**

```bash
git add src/prompts/system/intent.md
git commit -m "feat: add chat intent to intent recognition prompt

LLM now classifies unmatched inputs as chat instead of unknown."
```

### Task 3: Add route_by_intent chat route (TDD)

**Files:**
- Modify: `tests/graph/test_nodes.py`
- Modify: `src/graph/nodes.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/graph/test_nodes.py`, inside the existing `TestRouteByIntent` class, after `test_routes_to_doc_qa_for_doc_qa_intent`:

```python
def test_routes_to_chat_for_chat_intent(self):
    from src.graph.nodes import route_by_intent

    state = {"intent": "chat", "confidence": 0.8, "params": {}, "messages": []}
    assert route_by_intent(state) == "chat"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/graph/test_nodes.py::TestRouteByIntent::test_routes_to_chat_for_chat_intent -v`
Expected: FAIL — `assert '__end__' == 'chat'` (current code falls through to END)

- [ ] **Step 3: Update route_by_intent in nodes.py**

In `src/graph/nodes.py`, change `route_by_intent` (lines 144–150) from:

```python
def route_by_intent(state: State) -> str:
    """根据意图识别结果路由到对应节点。"""
    if state["intent"] == "doc_gen":
        return "doc_gen"
    if state["intent"] == "doc_qa":
        return "doc_qa"
    return END
```

to:

```python
def route_by_intent(state: State) -> str:
    """根据意图识别结果路由到对应节点。"""
    if state["intent"] == "doc_gen":
        return "doc_gen"
    if state["intent"] == "doc_qa":
        return "doc_qa"
    if state["intent"] == "chat":
        return "chat"
    return END
```

Also update `INTENT_LIST` (line 35) from:

```python
INTENT_LIST = "doc_gen, doc_qa"
```

to:

```python
INTENT_LIST = "doc_gen, doc_qa, chat"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/graph/test_nodes.py::TestRouteByIntent -v`
Expected: All 4 tests PASS (including the new `test_routes_to_chat_for_chat_intent`)

- [ ] **Step 5: Commit**

```bash
git add tests/graph/test_nodes.py src/graph/nodes.py
git commit -m "feat: add chat route to route_by_intent

Route intent='chat' to the chat node. Update INTENT_LIST constant."
```

---

## Chunk 2: Chat Node Implementation (TDD)

### Task 4: Add chat node (TDD)

**Files:**
- Modify: `tests/graph/test_nodes.py`
- Modify: `src/graph/nodes.py`

- [ ] **Step 1: Write the failing tests**

Add a new `TestChat` class to the end of `tests/graph/test_nodes.py`:

```python
class TestChat:
    """聊天节点测试。"""

    @pytest.mark.asyncio
    @patch("src.graph.nodes.ChatOpenAI")
    async def test_returns_messages_with_ai_response(self, mock_chat_cls):
        from src.graph.nodes import chat

        mock_llm = MagicMock()
        ai_msg = AIMessage(content="你好！有什么可以帮你的吗？")
        mock_llm.ainvoke = AsyncMock(return_value=ai_msg)
        mock_chat_cls.return_value = mock_llm

        state = {
            "messages": [HumanMessage(content="你好")],
            "intent": "chat",
            "confidence": 0.8,
            "params": {},
        }

        result = await chat(state, RunnableConfig())

        assert "messages" in result
        assert result["messages"] == [ai_msg]

    @pytest.mark.asyncio
    @patch("src.graph.nodes.load_prompt")
    @patch("src.graph.nodes.ChatOpenAI")
    async def test_loads_chat_prompt(self, mock_chat_cls, mock_load_prompt):
        from src.graph.nodes import chat

        mock_load_prompt.return_value.format_messages.return_value = []
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="done"))
        mock_chat_cls.return_value = mock_llm

        state = {
            "messages": [HumanMessage(content="你好")],
            "intent": "chat",
            "confidence": 0.8,
            "params": {},
        }

        await chat(state, RunnableConfig())

        mock_load_prompt.assert_called_once_with("chat")

    @pytest.mark.asyncio
    @patch("src.graph.nodes.ChatOpenAI")
    async def test_does_not_bind_tools(self, mock_chat_cls):
        from src.graph.nodes import chat

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=AIMessage(content="done")
        )
        mock_chat_cls.return_value = mock_llm

        state = {
            "messages": [HumanMessage(content="你好")],
            "intent": "chat",
            "confidence": 0.8,
            "params": {},
        }

        await chat(state, RunnableConfig())

        mock_llm.bind_tools.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.graph.nodes.ChatOpenAI")
    async def test_prepends_system_prompt_to_messages(self, mock_chat_cls):
        from src.graph.nodes import chat

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=AIMessage(content="done")
        )
        mock_chat_cls.return_value = mock_llm

        human_msg = HumanMessage(content="聊聊天吧")
        state = {
            "messages": [human_msg],
            "intent": "chat",
            "confidence": 0.8,
            "params": {},
        }

        await chat(state, RunnableConfig())

        invoke_args = mock_llm.ainvoke.call_args[0][0]
        assert invoke_args[0].type == "system"
        assert invoke_args[-1] == human_msg

    @pytest.mark.asyncio
    @patch("src.graph.nodes.ChatOpenAI")
    async def test_passes_message_history(self, mock_chat_cls):
        """多轮对话时，chat 节点应传入完整对话历史。"""
        from src.graph.nodes import chat

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=AIMessage(content="done")
        )
        mock_chat_cls.return_value = mock_llm

        state = {
            "messages": [
                HumanMessage(content="第一轮"),
                AIMessage(content="第一轮回答"),
                HumanMessage(content="第二轮"),
            ],
            "intent": "chat",
            "confidence": 0.8,
            "params": {},
        }

        await chat(state, RunnableConfig())

        invoke_args = mock_llm.ainvoke.call_args[0][0]
        # system prompt + user prompt + 3 messages from history = 5 total
        assert len(invoke_args) == 5
        assert invoke_args[0].type == "system"
        # The 3 conversation messages should be in the list
        contents = [m.content for m in invoke_args[2:]]
        assert "第一轮" in contents
        assert "第一轮回答" in contents
        assert "第二轮" in contents

    @pytest.mark.asyncio
    @patch("src.graph.nodes.ChatOpenAI")
    async def test_passes_config_to_ainvoke(self, mock_chat_cls):
        from src.graph.nodes import chat

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=AIMessage(content="done")
        )
        mock_chat_cls.return_value = mock_llm

        state = {
            "messages": [HumanMessage(content="你好")],
            "intent": "chat",
            "confidence": 0.8,
            "params": {},
        }

        config = RunnableConfig(configurable={"thread_id": "test-123"})
        await chat(state, config)

        call_kwargs = mock_llm.ainvoke.call_args
        assert call_kwargs[1]["config"] == config
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/graph/test_nodes.py::TestChat -v`
Expected: FAIL — `ImportError: cannot import name 'chat' from 'src.graph.nodes'`

- [ ] **Step 3: Implement the chat node**

In `src/graph/nodes.py`, add the `chat` function after the `doc_gen` function (after line 141) and before `route_by_intent`:

```python
async def chat(state: State, config: RunnableConfig) -> dict:
    """聊天节点。

    使用 chat 提示词与 LLM 进行自由对话，不绑定工具。
    通过 system prompt 柔和引导用户使用文档功能。
    """
    prompt = load_prompt("chat")
    user_input = _get_last_human_message(state["messages"])

    system_messages = prompt.format_messages(user_input=user_input)

    llm = ChatOpenAI(
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
        model=settings.llm.model,
    )

    all_messages = system_messages + state["messages"]
    response = await llm.ainvoke(all_messages, config=config)

    logger.info("聊天节点调用完成")
    return {"messages": [response]}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/graph/test_nodes.py::TestChat -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Run all node tests for regression**

Run: `uv run pytest tests/graph/test_nodes.py -v`
Expected: All tests PASS (existing + new)

- [ ] **Step 6: Commit**

```bash
git add tests/graph/test_nodes.py src/graph/nodes.py
git commit -m "feat: add chat node with TDD

Async chat node loads chat prompt, calls LLM without tools,
passes full message history for multi-turn support."
```

---

## Chunk 3: Graph Integration and Chainlit (TDD)

### Task 5: Add chat node to graph (TDD)

**Files:**
- Modify: `tests/graph/test_graph.py`
- Modify: `src/graph/graph.py`

- [ ] **Step 1: Write the failing test**

Add a new test method to the `TestBuildGraph` class in `tests/graph/test_graph.py`, after `test_graph_has_doc_qa_and_qa_tools_nodes`:

```python
def test_graph_has_chat_node(self):
    from src.graph.graph import build_graph

    graph = build_graph()
    node_names = set(graph.nodes.keys())
    assert "chat" in node_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/graph/test_graph.py::TestBuildGraph::test_graph_has_chat_node -v`
Expected: FAIL — `AssertionError: assert 'chat' in {...}`

- [ ] **Step 3: Update graph.py**

In `src/graph/graph.py`:

**(a)** Update the import (line 14–24) to add `chat`:

```python
from src.graph.nodes import (
    TOOLS,
    QA_TOOLS,
    State,
    chat,
    doc_gen,
    doc_qa,
    intent_recognize,
    route_by_intent,
    route_doc_gen,
    route_doc_qa,
)
```

**(b)** Add the chat node after `qa_tools` (after line 39):

```python
graph.add_node("chat", chat)
```

**(c)** Update the `route_by_intent` conditional edges (line 42) from:

```python
graph.add_conditional_edges("intent_recognize", route_by_intent, ["doc_gen", "doc_qa", "__end__"])
```

to:

```python
graph.add_conditional_edges("intent_recognize", route_by_intent, ["doc_gen", "doc_qa", "chat", "__end__"])
```

**(d)** Add the `chat → END` edge after the `qa_tools → doc_qa` edge (after line 46):

```python
graph.add_edge("chat", END)
```

Note: Import `END` — it's not currently imported. Add to the import at line 8:

```python
from langgraph.graph import START, END, StateGraph
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/graph/test_graph.py::TestBuildGraph::test_graph_has_chat_node -v`
Expected: PASS

- [ ] **Step 5: Run all graph tests for regression**

Run: `uv run pytest tests/graph/test_graph.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add tests/graph/test_graph.py src/graph/graph.py
git commit -m "feat: integrate chat node into graph

Add chat node with chat → END edge. Extend route_by_intent
conditional edges to include chat output."
```

### Task 6: Update Chainlit streaming and fallback (TDD)

**Files:**
- Modify: `tests/test_app.py`
- Modify: `app.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_app.py`:

**(a)** Add a new test to `TestOnMessageCoreFlow` class, after `test_skips_human_messages`:

```python
@pytest.mark.asyncio
async def test_streams_chat_node_content(self, app_module):
    """graph.astream yields AIMessageChunks from chat; content
    must be forwarded via answer.stream_token()."""
    app, mock_cl, mock_graph = app_module

    chunks = [
        (AIMessageChunk(content="你好！"), {"langgraph_node": "chat"}),
        (AIMessageChunk(content="有什么想聊的吗？"), {"langgraph_node": "chat"}),
    ]
    mock_graph.astream = MagicMock(return_value=_astream_from(chunks))

    user_msg = MagicMock()
    user_msg.content = "你好"

    await app.on_message(user_msg)

    answer_obj = mock_cl.Message.return_value
    calls = answer_obj.stream_token.call_args_list
    streamed = [c.args[0] for c in calls]
    assert "你好！" in streamed
    assert "有什么想聊的吗？" in streamed
```

**(b)** Update the existing `test_fallback_message_when_no_doc_gen_output` test in `TestOnMessageEdgeCases`. Add a new assertion line after the existing assertions (after line 207):

```python
assert "聊天" in answer_obj.content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_app.py::TestOnMessageCoreFlow::test_streams_chat_node_content tests/test_app.py::TestOnMessageEdgeCases::test_fallback_message_when_no_doc_gen_output -v`
Expected: Both FAIL — chat content not streamed (filtered out), fallback message doesn't contain "聊天"

- [ ] **Step 3: Update app.py**

**(a)** Update the streaming filter (line 61) from:

```python
and metadata["langgraph_node"] in ("doc_gen", "doc_qa")
```

to:

```python
and metadata["langgraph_node"] in ("doc_gen", "doc_qa", "chat")
```

**(b)** Update the fallback message (line 69) from:

```python
answer.content = "抱歉，我目前支持文档生成和文档问答功能。你可以让我为某个文件生成文档，或者基于已有文档提问。"
```

to:

```python
answer.content = "抱歉，我暂时无法理解你的意思。你可以让我进行文档生成、文档问答，也可以和我自由聊天。"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_app.py::TestOnMessageCoreFlow::test_streams_chat_node_content tests/test_app.py::TestOnMessageEdgeCases::test_fallback_message_when_no_doc_gen_output -v`
Expected: Both PASS

- [ ] **Step 5: Run all app tests for regression**

Run: `uv run pytest tests/test_app.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_app.py app.py
git commit -m "feat: enable chat streaming in Chainlit UI

Add chat node to streaming filter. Update fallback message to
mention chat capability alongside doc generation and QA."
```

### Task 7: Full test suite verification

**Files:** None (verification only)

- [ ] **Step 1: Run the complete test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS with zero failures

- [ ] **Step 2: Verify graph runs with LangGraph dev server (manual smoke test)**

Run: `uv run langgraph dev`
Verify: Server starts without import errors. (Stop with Ctrl+C after confirming startup.)
