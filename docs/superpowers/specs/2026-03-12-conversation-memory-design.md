# Conversation Memory Design

## Overview

Add session-level multi-turn conversation memory to doc-flow, enabling the agent to remember prior dialogue within the same chat session. When the browser is closed or the session ends, memory is discarded.

## Requirements

- **Scope**: Current session only (in-memory, no persistence)
- **Coverage**: All graph nodes (intent_recognize, doc_gen, doc_qa) see full conversation history
- **Environments**: Both Chainlit UI and LangGraph Dev Server
- **History management**: No truncation or summarization; full history passed to LLM

## Approach: LangGraph MemorySaver Checkpointer

Use LangGraph's built-in `MemorySaver` (from `langgraph.checkpoint.memory`). The checkpointer stores state snapshots keyed by `thread_id`. Each graph invocation with the same `thread_id` resumes from the previous state, with new messages appended via the existing `add_messages` reducer.

This is the standard LangGraph pattern for conversation memory. Future upgrade to persistent storage (SQLite/PostgreSQL) requires only swapping the checkpointer implementation — no other code changes.

## Design

### 1. Graph Layer (`src/graph/graph.py`)

`build_graph()` accepts an optional `checkpointer` parameter:

```python
from langgraph.checkpoint.memory import MemorySaver

def build_graph(checkpointer=None) -> CompiledStateGraph:
    graph = StateGraph(State)
    # ... node and edge definitions unchanged ...
    return graph.compile(checkpointer=checkpointer)
```

- Default `None` preserves backward compatibility (single-turn, no memory)
- Caller decides what checkpointer to inject
- `State` definition unchanged — `messages` already uses `add_messages` reducer

### 2. Node Message Reading Adaptation (`src/graph/nodes.py`)

**`intent_recognize`** — No change needed. Uses `state["messages"][-1].content`. With checkpointer, the new HumanMessage is appended to the end of the restored history, so `[-1]` still yields the latest user message.

**`doc_gen`** — No change needed. Constructs `system_messages + state["messages"]` and passes to LLM. Multi-turn history is naturally included.

**`doc_qa`** — **Requires change**. Currently reads `state["messages"][0].content` to get user input. In multi-turn mode, `[0]` is the first-ever message, not the current one.

Fix: extract the last `HumanMessage` from the message list:

```python
from langchain_core.messages import HumanMessage

def _get_last_human_message(messages: list) -> str:
    """Return the content of the last HumanMessage in the list."""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content
    return ""
```

`doc_qa` calls `_get_last_human_message(state["messages"])` instead of `state["messages"][0].content`.

### 3. Chainlit Integration (`app.py`)

```python
from langgraph.checkpoint.memory import MemorySaver
from uuid import uuid4

memory = MemorySaver()
graph = build_graph(checkpointer=memory)

@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("thread_id", str(uuid4()))

@cl.on_message
async def on_message(message: cl.Message):
    thread_id = cl.user_session.get("thread_id")
    cb = cl_callbacks.LangchainCallbackHandler(...)
    config = RunnableConfig(
        callbacks=[cb],
        configurable={"thread_id": thread_id},
    )
    # Input remains: {"messages": [HumanMessage(content=message.content)]}
    # Checkpointer automatically restores history and appends the new message
```

Key behaviors:
- Each new chat session (`on_chat_start`) gets a unique `thread_id`
- Same session's messages share the `thread_id`, enabling multi-turn
- Different chat sessions are fully isolated

### 4. LangGraph Dev Server

No changes to `langgraph.json`. The Dev Server / Studio manages its own checkpointer and thread state. When `build_graph()` is called without a checkpointer (the default), the Dev Server framework handles memory automatically via its built-in `inmem` store.

Users interact with threads via the Studio UI or API, which natively supports `thread_id`.

### 5. Prompt Templates

No changes to any prompt templates under `src/prompts/`. The `{user_input}` variable in `doc_qa` user prompt template is populated from the node code, not from the template itself.

## Testing Strategy

### New/Modified Tests

**`tests/graph/test_graph.py`**:
- Test `build_graph(checkpointer=MemorySaver())` compiles successfully
- Test multi-turn: invoke graph twice with same `thread_id`, verify second invocation sees history from first

**`tests/graph/test_nodes.py`**:
- Test `_get_last_human_message()` helper with various message lists
- Test `doc_qa` node with multi-message state correctly extracts last HumanMessage

**`tests/test_app.py`**:
- Test `on_chat_start` sets a `thread_id` in `cl.user_session`
- Test `on_message` passes `configurable.thread_id` in config

### Unchanged Tests

- `intent_recognize` tests — `[-1]` behavior unchanged
- `doc_gen` tests — already handles full message list
- All tool tests — tools are stateless, unaffected by memory

### TDD Workflow

Per project convention: write failing test first, implement, verify green, commit.

## Files Changed

| File | Change |
|------|--------|
| `src/graph/graph.py` | `build_graph()` accepts `checkpointer` param, passes to `compile()` |
| `src/graph/nodes.py` | Add `_get_last_human_message()`, update `doc_qa` to use it |
| `app.py` | Create `MemorySaver`, generate `thread_id` per session, pass in config |
| `tests/graph/test_graph.py` | Add checkpointer compilation and multi-turn tests |
| `tests/graph/test_nodes.py` | Add `_get_last_human_message` and `doc_qa` multi-message tests |
| `tests/test_app.py` | Add thread_id session and config tests |

## Dependencies

No new package installations needed. `MemorySaver` is included in the `langgraph` package already in `pyproject.toml`.

## Not in Scope

- Persistent storage (SQLite/PostgreSQL) — can be added later by swapping checkpointer
- History truncation or summarization — not needed for typical doc-generation sessions
- Cross-session memory — explicitly excluded per requirements
