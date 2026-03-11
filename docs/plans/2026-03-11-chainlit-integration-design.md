# Chainlit Integration Design

## Overview

Integrate Chainlit as a chat UI for the existing LangGraph StateGraph, enabling users to interact with doc-flow through a browser-based chat interface with streaming output and visible tool call steps.

## Decision Record

- **Single-turn conversation**: No checkpointer needed. Each message is an independent request.
- **Streaming with auto steps**: Use `stream_mode="messages"` + `cl.LangchainCallbackHandler` (方案 A).
- **Entry file**: `src/app.py` (currently empty).
- **No graph modifications**: Chainlit is a pure UI layer on top of the existing graph.

## Architecture

```
Browser  <──WebSocket──>  Chainlit Server (src/app.py)
                                │
                          @cl.on_message
                                │
                          graph.astream()
                          stream_mode="messages"
                                │
                     ┌──────────┴──────────┐
                     │                     │
               doc_gen tokens         tool calls
               (stream_token)    (LangchainCallbackHandler
                                  auto-rendered as Steps)
```

Components:
- `src/app.py` — Chainlit entry point with `@cl.on_chat_start` and `@cl.on_message`
- `build_graph()` — Reused as-is, called once at module level
- `cl.LangchainCallbackHandler` — Auto-captures intermediate tool call steps
- Launch command: `chainlit run src/app.py -w`

## Core Logic (`src/app.py`)

```python
import chainlit as cl
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from src.graph import build_graph

graph = build_graph()

@cl.on_chat_start
async def on_chat_start():
    await cl.Message(
        content="你好！我是 doc-flow，请告诉我你想为哪个 Go 项目目录生成文档。"
    ).send()

@cl.on_message
async def on_message(message: cl.Message):
    cb = cl.LangchainCallbackHandler(
        to_ignore=["ChannelRead", "RunnableLambda", "ChannelWrite",
                    "__start__", "_execute"]
    )
    config = RunnableConfig(callbacks=[cb])
    answer = cl.Message(content="")

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

    if not answer.content:
        answer.content = "抱歉，我目前只支持文档生成功能。请告诉我你想为哪个目录生成文档。"
    await answer.send()
```

Key behaviors:
- `metadata["langgraph_node"] == "doc_gen"` filters to only stream doc generation output
- `intent_recognize` output is not shown to users
- `LangchainCallbackHandler` renders tool calls (scan_directory, read_file, etc.) as collapsible Steps
- Empty response fallback handles intent mismatch (graph goes to END without doc_gen)

## Dependencies

Add to `pyproject.toml`:
- `chainlit` — chat UI framework

Not needed:
- No ASGI server (Chainlit includes one)
- No checkpointer (single-turn)
- No changes to `langgraph.json` (independent entry point)

## Configuration

- Chainlit auto-generates `.chainlit/config.toml` on first run (optional customization)
- CLAUDE.md updated with `chainlit run src/app.py -w` command

## Testing Strategy

Test file: `tests/test_app.py`

1. **Core flow**: Mock `graph.astream()` with preset `(message, metadata)` sequences, verify only `doc_gen` node content is streamed
2. **Intent mismatch**: Mock empty stream (graph hits END), verify fallback message
3. **Error handling**: Mock graph raising exception, verify friendly error message

Not tested (already covered elsewhere):
- Graph logic (`tests/graph/`)
- Chainlit framework internals
