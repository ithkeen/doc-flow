# Graph 模块实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 graph 模块，使用 LangGraph 框架编排意图识别和文档生成的 agent 工作流。

**Architecture:** 采用多意图路由方案。意图识别节点作为入口，根据结果条件路由到 doc_gen 节点或 END。doc_gen 节点与内置 ToolNode 形成 ReAct 循环。提示词通过 `load_prompt()` 在节点内格式化，不写入 state。

**Tech Stack:** LangGraph, LangChain, langchain-openai, pydantic-settings, pytest

---

### Task 1: 添加依赖

**Files:**
- Modify: `pyproject.toml:7-9`

**Step 1: 添加 langgraph 和 langchain-openai 依赖**

```bash
uv add langgraph langchain-openai
```

**Step 2: 验证依赖安装成功**

Run: `uv run python -c "from langgraph.graph import StateGraph; from langchain_openai import ChatOpenAI; print('ok')"`
Expected: `ok`

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add langgraph and langchain-openai dependencies"
```

---

### Task 2: State 定义与模块初始化

**Files:**
- Create: `src/graph/__init__.py`
- Create: `src/graph/nodes.py`
- Create: `tests/graph/__init__.py`
- Create: `tests/graph/test_nodes.py`

**Step 1: 写失败测试 — State 类型结构**

```python
# tests/graph/__init__.py
（空文件）
```

```python
# tests/graph/test_nodes.py
"""graph 节点单元测试。"""

import pytest
from typing import get_type_hints, Annotated


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
```

**Step 2: 运行测试确认失败**

Run: `uv run pytest tests/graph/test_nodes.py::TestStateDefinition -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.graph'`

**Step 3: 实现 State 定义**

```python
# src/graph/__init__.py
"""图编排模块。

使用 LangGraph 构建 agent 工作流，编排意图识别与文档生成。

Usage::

    from src.graph import build_graph

    graph = build_graph()
    result = graph.invoke({"messages": [("human", "请为 ./handler 生成文档")]})
"""

__all__: list[str] = []
```

```python
# src/graph/nodes.py
"""图节点与状态定义。

定义 State 类型、节点函数和路由函数。
"""

from __future__ import annotations

from typing import Annotated

from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class State(TypedDict):
    """图的共享状态。"""

    messages: Annotated[list, add_messages]
    intent: str
    confidence: float
    params: dict
```

**Step 4: 运行测试确认通过**

Run: `uv run pytest tests/graph/test_nodes.py::TestStateDefinition -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add src/graph/__init__.py src/graph/nodes.py tests/graph/__init__.py tests/graph/test_nodes.py
git commit -m "feat(graph): add State definition and module scaffold"
```

---

### Task 3: intent_recognize 节点

**Files:**
- Modify: `src/graph/nodes.py`
- Modify: `tests/graph/test_nodes.py`

**Step 1: 写失败测试 — intent_recognize 节点**

在 `tests/graph/test_nodes.py` 末尾追加：

```python
from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage


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
        # 应包含 system 和 human 两条消息（来自 intent 提示词模板）
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
```

**Step 2: 运行测试确认失败**

Run: `uv run pytest tests/graph/test_nodes.py::TestIntentRecognize -v`
Expected: FAIL — `ImportError: cannot import name 'intent_recognize'`

**Step 3: 实现 intent_recognize 节点**

在 `src/graph/nodes.py` 中追加：

```python
import json

from langchain_openai import ChatOpenAI

from src.config import settings
from src.logs import get_logger
from src.prompts import load_prompt

logger = get_logger(__name__)

# 当前支持的意图列表
INTENT_LIST = "doc_gen"


def intent_recognize(state: State) -> dict:
    """意图识别节点。

    分析用户输入，判断意图类别，返回 intent / confidence / params。
    """
    prompt = load_prompt("intent")
    user_input = state["messages"][-1].content

    messages = prompt.format_messages(
        intent_list=INTENT_LIST,
        user_input=user_input,
    )

    llm = ChatOpenAI(
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
        model=settings.llm.model,
    )
    response = llm.invoke(messages)

    try:
        parsed = json.loads(response.content)
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

**Step 4: 运行测试确认通过**

Run: `uv run pytest tests/graph/test_nodes.py::TestIntentRecognize -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add src/graph/nodes.py tests/graph/test_nodes.py
git commit -m "feat(graph): add intent_recognize node"
```

---

### Task 4: doc_gen 节点

**Files:**
- Modify: `src/graph/nodes.py`
- Modify: `tests/graph/test_nodes.py`

**Step 1: 写失败测试 — doc_gen 节点**

在 `tests/graph/test_nodes.py` 末尾追加：

```python
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
        # 第一条应是 system 消息（来自 doc_gen 提示词）
        assert invoke_args[0].type == "system"
        # 最后一条应是用户消息
        assert invoke_args[-1] == human_msg
```

**Step 2: 运行测试确认失败**

Run: `uv run pytest tests/graph/test_nodes.py::TestDocGen -v`
Expected: FAIL — `ImportError: cannot import name 'doc_gen'`

**Step 3: 实现 doc_gen 节点**

在 `src/graph/nodes.py` 中追加：

```python
from src.tools.code_scanner import scan_directory
from src.tools.file_reader import read_file
from src.tools.doc_storage import save_document, read_document, list_documents

TOOLS = [scan_directory, read_file, save_document, read_document, list_documents]


def doc_gen(state: State) -> dict:
    """文档生成节点。

    使用 doc_gen 提示词和绑定工具的 LLM 生成文档。
    与 ToolNode 形成 ReAct 循环。
    """
    prompt = load_prompt("doc_gen")
    directory_path = state["params"].get("directory_path", "")

    system_messages = prompt.format_messages(directory_path=directory_path)

    llm = ChatOpenAI(
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
        model=settings.llm.model,
    )
    llm_with_tools = llm.bind_tools(TOOLS)

    all_messages = system_messages + state["messages"]
    response = llm_with_tools.invoke(all_messages)

    logger.info("文档生成节点调用完成")
    return {"messages": [response]}
```

**Step 4: 运行测试确认通过**

Run: `uv run pytest tests/graph/test_nodes.py::TestDocGen -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add src/graph/nodes.py tests/graph/test_nodes.py
git commit -m "feat(graph): add doc_gen node with tool binding"
```

---

### Task 5: 路由函数

**Files:**
- Modify: `src/graph/nodes.py`
- Modify: `tests/graph/test_nodes.py`

**Step 1: 写失败测试 — 路由函数**

在 `tests/graph/test_nodes.py` 末尾追加：

```python
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
```

**Step 2: 运行测试确认失败**

Run: `uv run pytest tests/graph/test_nodes.py::TestRouteByIntent tests/graph/test_nodes.py::TestRouteDocGen -v`
Expected: FAIL — `ImportError: cannot import name 'route_by_intent'`

**Step 3: 实现路由函数**

在 `src/graph/nodes.py` 中追加：

```python
from langgraph.graph import END


def route_by_intent(state: State) -> str:
    """根据意图识别结果路由到对应节点。"""
    if state["intent"] == "doc_gen":
        return "doc_gen"
    return END


def route_doc_gen(state: State) -> str:
    """根据 LLM 是否发起工具调用决定下一步。"""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END
```

**Step 4: 运行测试确认通过**

Run: `uv run pytest tests/graph/test_nodes.py::TestRouteByIntent tests/graph/test_nodes.py::TestRouteDocGen -v`
Expected: 5 passed

**Step 5: Commit**

```bash
git add src/graph/nodes.py tests/graph/test_nodes.py
git commit -m "feat(graph): add route_by_intent and route_doc_gen routing functions"
```

---

### Task 6: build_graph 图编排

**Files:**
- Create: `src/graph/graph.py`
- Create: `tests/graph/test_graph.py`
- Modify: `src/graph/__init__.py`

**Step 1: 写失败测试 — build_graph**

```python
# tests/graph/test_graph.py
"""graph 编排单元测试。"""

from unittest.mock import patch

from langgraph.graph.state import CompiledStateGraph


class TestBuildGraph:
    """build_graph 工厂函数测试。"""

    def test_returns_compiled_graph(self):
        from src.graph.graph import build_graph

        graph = build_graph()
        assert isinstance(graph, CompiledStateGraph)

    def test_graph_has_expected_nodes(self):
        from src.graph.graph import build_graph

        graph = build_graph()
        node_names = set(graph.nodes.keys())
        assert "intent_recognize" in node_names
        assert "doc_gen" in node_names
        assert "tools" in node_names


class TestModuleExport:
    """验证模块导出。"""

    def test_build_graph_importable_from_package(self):
        from src.graph import build_graph as fn

        assert callable(fn)
```

**Step 2: 运行测试确认失败**

Run: `uv run pytest tests/graph/test_graph.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.graph.graph'`

**Step 3: 实现 build_graph**

```python
# src/graph/graph.py
"""图编排。

构建并编译 LangGraph StateGraph，串联意图识别、文档生成和工具执行。
"""

from __future__ import annotations

from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode

from src.graph.nodes import (
    TOOLS,
    State,
    doc_gen,
    intent_recognize,
    route_by_intent,
    route_doc_gen,
)


def build_graph() -> StateGraph:
    """构建并编译 agent 工作流图。

    Returns:
        编译后的 CompiledStateGraph，可直接 invoke。
    """
    graph = StateGraph(State)

    graph.add_node("intent_recognize", intent_recognize)
    graph.add_node("doc_gen", doc_gen)
    graph.add_node("tools", ToolNode(tools=TOOLS))

    graph.add_edge(START, "intent_recognize")
    graph.add_conditional_edges("intent_recognize", route_by_intent, ["doc_gen", "__end__"])
    graph.add_conditional_edges("doc_gen", route_doc_gen, ["tools", "__end__"])
    graph.add_edge("tools", "doc_gen")

    return graph.compile()
```

更新 `src/graph/__init__.py`：

```python
"""图编排模块。

使用 LangGraph 构建 agent 工作流，编排意图识别与文档生成。

Usage::

    from src.graph import build_graph

    graph = build_graph()
    result = graph.invoke({"messages": [("human", "请为 ./handler 生成文档")]})
"""

from src.graph.graph import build_graph

__all__ = ["build_graph"]
```

**Step 4: 运行测试确认通过**

Run: `uv run pytest tests/graph/test_graph.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add src/graph/graph.py src/graph/__init__.py tests/graph/test_graph.py
git commit -m "feat(graph): add build_graph with StateGraph orchestration"
```

---

### Task 7: 全量测试验证

**Step 1: 运行全部测试**

Run: `uv run pytest tests/ -v`
Expected: 所有测试通过，无回归

**Step 2: 如有失败，修复后重新运行**

**Step 3: Commit（如有修复）**

```bash
git add -A
git commit -m "fix(graph): resolve test regressions"
```
