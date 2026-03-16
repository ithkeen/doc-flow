# Remove doc_gen Node Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the `doc_gen` node from the LangGraph StateGraph so API docs become read-only in the Chainlit chat UI, managed exclusively by the `src/generator` CLI module.

**Architecture:** Delete `doc_gen` node, its dedicated `tools` ToolNode, related edges, routing logic, prompt files, and unused State fields (`params`, `confidence`). Update intent prompt, chat prompt, app.py UI messages, module docstrings, and CLAUDE.md. Preserve `doc_gen_llm` config and all tool source files (still used by `generator` and `doc_qa`).

**Tech Stack:** Python, LangGraph, LangChain, Chainlit

**Spec:** `docs/superpowers/specs/2026-03-16-remove-doc-gen-node.md`

---

## Chunk 1: Core Graph and Nodes Changes

### Task 1: Remove doc_gen from nodes.py

**Files:**
- Modify: `src/graph/nodes.py`

- [ ] **Step 1: Remove INTENT_LIST constant**

Delete line 35:
```python
INTENT_LIST = "doc_gen, doc_qa, chat"
```

- [ ] **Step 2: Remove doc_gen-only tool imports**

Delete lines 73-76:
```python
from src.tools.code_scanner import scan_directory
from src.tools.file_reader import read_file
from src.tools.doc_storage import save_document, read_document, list_documents
from src.tools.code_search import find_function
```

Replace with only the imports needed by `QA_TOOLS`:
```python
from src.tools.doc_storage import read_document, list_documents
```

- [ ] **Step 3: Remove TOOLS list**

Delete line 78:
```python
TOOLS = [scan_directory, read_file, save_document, read_document, list_documents, find_function]
```

- [ ] **Step 4: Remove doc_gen function**

Delete lines 112-130:
```python
async def doc_gen(state: State, config: RunnableConfig) -> dict:
    """文档生成节点。

    使用 doc_gen 提示词和绑定工具的 LLM 生成文档。
    与 ToolNode 形成 ReAct 循环。
    """
    prompt = load_prompt("doc_gen")
    file_path = state["params"].get("file_path", "")

    system_messages = prompt.format_messages(file_path=file_path)

    llm = get_node_llm("doc_gen")
    llm_with_tools = llm.bind_tools(TOOLS)

    all_messages = system_messages + state["messages"]
    response = await llm_with_tools.ainvoke(all_messages, config=config)

    logger.info("文档生成节点调用完成")
    return {"messages": [response]}
```

- [ ] **Step 5: Remove route_doc_gen function**

Delete lines 164-169:
```python
def route_doc_gen(state: State) -> str:
    """根据 LLM 是否发起工具调用决定下一步。"""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END
```

- [ ] **Step 6: Remove doc_gen branch from route_by_intent**

In `route_by_intent` (line 153-161), delete lines 155-156:
```python
    if state["intent"] == "doc_gen":
        return "doc_gen"
```

- [ ] **Step 7: Remove params and confidence from State**

Change State definition (lines 26-32) from:
```python
class State(TypedDict):
    """图的共享状态。"""

    messages: Annotated[list, add_messages]
    intent: str
    confidence: float
    params: dict
```

To:
```python
class State(TypedDict):
    """图的共享状态。"""

    messages: Annotated[list, add_messages]
    intent: str
```

- [ ] **Step 8: Update intent_recognize docstring**

Change the docstring (line 41) from:
```python
    分析用户输入，判断意图类别，返回 intent / confidence / params。
```
To:
```python
    分析用户输入，判断意图类别，返回 intent。
```

- [ ] **Step 9: Simplify intent_recognize return value**

In `intent_recognize` function (lines 38-70), change the try/except block and return from:
```python
    try:
        parsed = json.loads(raw)
        intent = parsed.get("intent", "unknown")
        confidence = float(parsed.get("confidence", 0.0))
        params = parsed.get("params", {})
    except (json.JSONDecodeError, ValueError):
        logger.warning("意图识别结果解析失败，原始内容：%s", response.content)
        intent = "unknown"
        confidence = 0.0
        params = {}

    logger.info("意图识别完成：intent=%s, confidence=%.2f", intent, confidence)
    return {"intent": intent, "confidence": confidence, "params": params}
```

To:
```python
    try:
        parsed = json.loads(raw)
        intent = parsed.get("intent", "unknown")
    except (json.JSONDecodeError, ValueError):
        logger.warning("意图识别结果解析失败，原始内容：%s", response.content)
        intent = "unknown"

    logger.info("意图识别完成：intent=%s", intent)
    return {"intent": intent}
```

- [ ] **Step 10: Verify nodes.py final state**

The file should export: `State`, `QA_TOOLS`, `intent_recognize`, `doc_qa`, `chat`, `route_by_intent`, `route_doc_qa`, `_get_last_human_message`.

No longer exported: `TOOLS`, `INTENT_LIST`, `doc_gen`, `route_doc_gen`.

### Task 2: Update graph.py

**Files:**
- Modify: `src/graph/graph.py`

- [ ] **Step 1: Update imports from nodes**

Change lines 14-25 from:
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

To:
```python
from src.graph.nodes import (
    QA_TOOLS,
    State,
    chat,
    doc_qa,
    intent_recognize,
    route_by_intent,
    route_doc_qa,
)
```

- [ ] **Step 2: Remove doc_gen node and tools ToolNode**

In `build_graph`, delete lines 37-38:
```python
    graph.add_node("doc_gen", doc_gen)
    graph.add_node("tools", ToolNode(tools=TOOLS))
```

- [ ] **Step 3: Remove doc_gen edges**

Delete lines 44-46 (the conditional edge for intent routing will be modified, not deleted):

Update line 44 from:
```python
    graph.add_conditional_edges("intent_recognize", route_by_intent, ["doc_gen", "doc_qa", "chat", "__end__"])
```
To:
```python
    graph.add_conditional_edges("intent_recognize", route_by_intent, ["doc_qa", "chat", "__end__"])
```

Delete line 45:
```python
    graph.add_conditional_edges("doc_gen", route_doc_gen, ["tools", "__end__"])
```

Delete line 46:
```python
    graph.add_edge("tools", "doc_gen")
```

- [ ] **Step 4: Update graph.py module docstring**

Change line 3 from:
```python
"""图编排。

构建并编译 LangGraph StateGraph，串联意图识别、文档生成、文档问答和工具执行。
"""
```

To:
```python
"""图编排。

构建并编译 LangGraph StateGraph，串联意图识别、文档问答和自由聊天。
"""
```

- [ ] **Step 5: Run tests to verify graph compiles**

Run: `uv run pytest -x -v`
Expected: All existing tests pass. No tests directly test `build_graph()` but import chains may trigger compilation.

- [ ] **Step 6: Commit**

```bash
git add src/graph/nodes.py src/graph/graph.py
git commit -m "refactor: remove doc_gen node and tools ToolNode from graph"
```

---

## Chunk 2: Prompt Files and Intent Changes

### Task 3: Update intent prompt

**Files:**
- Modify: `src/prompts/system/intent.md`

- [ ] **Step 1: Remove doc_gen intent line and fix chat description**

Delete line 6:
```markdown
- doc_gen：用户要求为某个文件或模块生成 API 文档
```

Update line 8 (the `chat` intent description) from:
```markdown
- chat：用户的输入不属于以上两种意图，是一般性对话、闲聊、问候、技术讨论或其他内容
```
To:
```markdown
- chat：用户的输入不属于以上意图，是一般性对话、闲聊、问候、技术讨论或其他内容
```

- [ ] **Step 2: Update doc_qa description to cover the gap**

Update line 7 (now line 6 after deletion). Keep as-is per user request — do NOT modify doc_qa description.

- [ ] **Step 3: Remove confidence and params from JSON output spec**

Change lines 10-13 from:
```markdown
请以 JSON 格式输出你的判断结果，包含以下字段：
- intent: 识别出的意图类别
- confidence: 置信度（0-1）
- params: 从用户输入中提取的关键参数
```

To:
```markdown
请以 JSON 格式输出你的判断结果，包含以下字段：
- intent: 识别出的意图类别
```

- [ ] **Step 4: Verify final intent.md content**

Expected:
```markdown
你是一个智能代码文档生成助手的意图识别模块。

你的任务是分析用户的输入，判断其意图属于以下哪一类:

可用意图：
- doc_qa：用户基于已有文档提问（查询接口参数、用法、错误码等）
- chat：用户的输入不属于以上意图，是一般性对话、闲聊、问候、技术讨论或其他内容

请以 JSON 格式输出你的判断结果，包含以下字段：
- intent: 识别出的意图类别
```

### Task 4: Update chat prompt

**Files:**
- Modify: `src/prompts/system/chat.md`

- [ ] **Step 1: Update capabilities section**

Change lines 9-11 from:
```markdown
你还拥有两项核心能力：
- 为 Go 源码文件生成 API 文档（用户只需告诉你文件路径）
- 回答已有文档相关的问题
```

To:
```markdown
你还拥有一项核心能力：
- 回答已有文档相关的问题

如果用户要求生成文档，请告知他们使用 CLI 工具：`uv run python -m src.generator`。
```

### Task 5: Delete doc_gen prompt files

**Files:**
- Delete: `src/prompts/system/doc_gen.md`
- Delete: `src/prompts/user/doc_gen.md`

- [ ] **Step 1: Delete prompt files**

```bash
rm src/prompts/system/doc_gen.md src/prompts/user/doc_gen.md
```

- [ ] **Step 2: Commit**

```bash
git add src/prompts/system/intent.md src/prompts/system/chat.md
git add -u src/prompts/system/doc_gen.md src/prompts/user/doc_gen.md
git commit -m "refactor: update prompts and remove doc_gen prompt files"
```

---

## Chunk 3: UI and Documentation Updates

### Task 6: Update app.py

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Update welcome message**

Change line 28 from:
```python
        content="你好！我是 doc-flow，你可以让我为 Go 源码文件生成 API 文档，或者基于已有文档提问。"
```

To:
```python
        content="你好！我是 doc-flow，你可以基于已有文档提问，或者和我自由聊天。"
```

- [ ] **Step 2: Update stream filter**

Change line 61 from:
```python
                and metadata["langgraph_node"] in ("doc_gen", "doc_qa", "chat")
```

To:
```python
                and metadata["langgraph_node"] in ("doc_qa", "chat")
```

- [ ] **Step 3: Update fallback message**

Change line 69 from:
```python
        answer.content = "抱歉，我暂时无法理解你的意思。你可以让我进行文档生成、文档问答，也可以和我自由聊天。"
```

To:
```python
        answer.content = "抱歉，我暂时无法理解你的意思。你可以让我进行文档问答，也可以和我自由聊天。"
```

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "refactor: remove doc_gen references from Chainlit UI"
```

### Task 7: Update src/graph/__init__.py

**Files:**
- Modify: `src/graph/__init__.py`

- [ ] **Step 1: Update module docstring**

Change lines 1-10 from:
```python
"""图编排模块。

使用 LangGraph 构建 agent 工作流，编排意图识别与文档生成。

Usage::

    from src.graph import build_graph

    graph = build_graph()
    result = graph.invoke({"messages": [("human", "请为 ./handler 生成文档")]})
"""
```

To:
```python
"""图编排模块。

使用 LangGraph 构建 agent 工作流，编排意图识别、文档问答与自由聊天。

Usage::

    from src.graph import build_graph

    graph = build_graph()
    result = graph.invoke({"messages": [("human", "handler 模块有哪些接口？")]})
"""
```

- [ ] **Step 2: Commit**

```bash
git add src/graph/__init__.py
git commit -m "docs: update graph module docstring"
```

### Task 8: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update Project Overview**

Change line 7 from:
```markdown
doc-flow is an AI-powered documentation generator that analyzes Go source code and produces structured Markdown API docs. It uses a LangGraph StateGraph with a ReAct agent loop: intent recognition routes to doc generation, doc Q&A, or general chat. Entry point `app.py` (project root) serves the Chainlit chat UI.
```

To:
```markdown
doc-flow is an AI-powered documentation system for Go source code. The Chainlit chat UI (`app.py`) provides doc Q&A and general chat via a LangGraph StateGraph. API doc generation is handled exclusively by the `src/generator` CLI module.
```

- [ ] **Step 2: Update Graph orchestration diagram**

Change lines 46-57 from:
```
**Graph orchestration (`src/graph`):**
\```
START -> intent_recognize -> [route_by_intent] -+-> doc_gen -> [route_doc_gen] -> tools -> doc_gen (ReAct loop)
                                                |                     |
                                                |                     +-> END
                                                |
                                                +-> doc_qa -> [route_doc_qa] -> qa_tools -> doc_qa (ReAct loop)
                                                |                     |
                                                |                     +-> END
                                                |
                                                +-> chat -> END
                                                |
                                                +-> END (unknown intent fallback)
\```
```

To:
```
**Graph orchestration (`src/graph`):**
\```
START -> intent_recognize -> [route_by_intent] -+-> doc_qa -> [route_doc_qa] -> qa_tools -> doc_qa (ReAct loop)
                                                |                     |
                                                |                     +-> END
                                                |
                                                +-> chat -> END
                                                |
                                                +-> END (unknown intent fallback)
\```
```

- [ ] **Step 3: Update State and node descriptions**

Change line 59 from:
```markdown
- `State(TypedDict)` holds `messages` (with `add_messages` reducer), `intent`, `confidence`, `params`.
```
To:
```markdown
- `State(TypedDict)` holds `messages` (with `add_messages` reducer) and `intent`.
```

Change line 60 from:
```markdown
- `intent_recognize`, `doc_gen`, `doc_qa`, and `chat` are all **async** functions that accept `RunnableConfig` as a second parameter and forward it to LLM calls. This is required for Chainlit's `LangchainCallbackHandler` and to avoid callback threading issues.
```
To:
```markdown
- `intent_recognize`, `doc_qa`, and `chat` are all **async** functions that accept `RunnableConfig` as a second parameter and forward it to LLM calls. This is required for Chainlit's `LangchainCallbackHandler` and to avoid callback threading issues.
```

Change line 61 from:
```markdown
- `intent_recognize` loads the `"intent"` prompt, calls `ChatOpenAI`, parses JSON response into `intent`/`confidence`/`params`. Uses `state["messages"][-1].content` (last message).
```
To:
```markdown
- `intent_recognize` loads the `"intent"` prompt, calls `ChatOpenAI`, parses JSON response to extract `intent`. Uses `state["messages"][-1].content` (last message).
```

Delete line 62 entirely (the `doc_gen` node description):
```markdown
- `doc_gen` loads the `"doc_gen"` prompt, binds `TOOLS` (6 tools: `scan_directory`, `read_file`, `save_document`, `read_document`, `list_documents`, `find_function`) to `ChatOpenAI`. The `doc_gen` system prompt includes a Pre-check phase that resolves short function names via `find_function` and checks for existing docs via `list_documents` before starting the 4-task workflow.
```

Change line 64 from:
```markdown
- `chat` loads the `"chat"` prompt, calls `ChatOpenAI` **without** binding tools (pure LLM conversation). Uses full message history for multi-turn context. System prompt softly guides users toward doc_gen/doc_qa features.
```
To:
```markdown
- `chat` loads the `"chat"` prompt, calls `ChatOpenAI` **without** binding tools (pure LLM conversation). Uses full message history for multi-turn context. System prompt guides users toward doc_qa features and directs doc generation requests to the CLI tool.
```

Change line 65 from:
```markdown
- `route_by_intent` routes to `"doc_gen"`, `"doc_qa"`, `"chat"`, or `END`. `route_doc_gen` and `route_doc_qa` each route to their respective `ToolNode` if tool calls are present, else `END`.
```
To:
```markdown
- `route_by_intent` routes to `"doc_qa"`, `"chat"`, or `END`. `route_doc_qa` routes to `"qa_tools"` ToolNode if tool calls are present, else `END`.
```

- [ ] **Step 4: Update git_diff tool description**

Change line 66 from:
```markdown
- `git_diff` tool exists but is intentionally excluded from both tool lists (future feature).
```
To:
```markdown
- `git_diff` tool exists but is intentionally excluded from `QA_TOOLS` (future feature).
```

- [ ] **Step 5: Update Prompt templates description**

Change line 75 from:
```markdown
- **Prompt templates**: Stored as `.md` files under `src/prompts/system/` and `src/prompts/user/`, loaded by name via `load_prompt("intent")`, `load_prompt("doc_gen")`, `load_prompt("doc_qa")`, `load_prompt("chat")`, or `load_prompt("batch_doc_gen")`. At least one of system/user must exist for a given name. The `batch_doc_gen` prompt uses explicit template variables (`{project}`, `{module}`, `{function_name}`, `{source_file}`, `{source_line}`) instead of relying on tool-based pre-check.
```
To:
```markdown
- **Prompt templates**: Stored as `.md` files under `src/prompts/system/` and `src/prompts/user/`, loaded by name via `load_prompt("intent")`, `load_prompt("doc_qa")`, `load_prompt("chat")`, or `load_prompt("batch_doc_gen")`. At least one of system/user must exist for a given name. The `batch_doc_gen` prompt uses explicit template variables (`{project}`, `{module}`, `{function_name}`, `{source_file}`, `{source_line}`) instead of relying on tool-based pre-check.
```

- [ ] **Step 6: Update Environment section**

Change line 84 from:
```markdown
- Prompts, tool docstrings, and error messages are in Chinese (Simplified), except the `doc_gen` and `batch_doc_gen` system prompts which are in English
```
To:
```markdown
- Prompts, tool docstrings, and error messages are in Chinese (Simplified), except the `batch_doc_gen` system prompt which is in English
```

- [ ] **Step 7: Commit**
git commit -m "docs: update CLAUDE.md to reflect doc_gen removal"
```

---

## Chunk 4: Final Verification

### Task 9: Run full test suite and verify

- [ ] **Step 1: Run all tests**

Run: `uv run pytest -x -v`
Expected: All tests pass.

- [ ] **Step 2: Verify no stale references to doc_gen in modified files**

Search for `doc_gen` in the modified files to confirm no leftover references:
```bash
grep -rn "doc_gen" src/graph/graph.py src/graph/nodes.py src/graph/__init__.py app.py src/prompts/system/intent.md src/prompts/system/chat.md CLAUDE.md
```
Expected: Only matches in CLAUDE.md should be `doc_gen_llm` config references and `batch_doc_gen` prompt references. No matches in the other files.

- [ ] **Step 3: Verify confidence and params removed from intent prompt**

```bash
grep -n "confidence\|params" src/prompts/system/intent.md
```
Expected: No matches.

- [ ] **Step 4: Verify doc_gen prompt files are deleted**

```bash
ls src/prompts/system/doc_gen.md src/prompts/user/doc_gen.md 2>&1
```
Expected: "No such file or directory" for both.

- [ ] **Step 5: Verify preserved files still reference doc_gen correctly**

These files SHOULD still reference `doc_gen` (for the generator module):
```bash
grep -rn "doc_gen" src/config/settings.py src/config/llm.py src/generator/graph.py tests/test_llm.py .env.example
```
Expected: Matches in all these files (they use `doc_gen_llm` config which is still needed).

- [ ] **Step 6: Verify CLAUDE.md has no doc_gen graph references**

```bash
grep -n "doc_gen" CLAUDE.md
```
Expected: Only references should be in the `doc_gen_llm` config description (Key patterns section, line ~70) and batch_doc_gen prompt reference. No references to the `doc_gen` graph node.
