# project_explore Node Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `project_explore` ReAct node that intelligently explores a project's structure and outputs a `task.md` summary listing all services, their types, and handler file paths.

**Architecture:** New ReAct loop (`project_explore ←→ explore_tools`) added to the existing graph alongside `doc_gen`. Uses LLM + 7 tools (5 existing + 2 new) to autonomously explore a project. Outputs to `DOCS_SPACE_DIR/{project}/task.md` via `write_file`.

**Tech Stack:** LangGraph StateGraph, LangChain ToolNode, ChatOpenAI, pathlib

---

### Task 1: Add `list_directory` tool

**Files:**
- Modify: `src/tools/file.py` (append new tool)
- Test: `tests/tools/test_file.py`

- [ ] **Step 1: Create test file with failing tests**

```python
# tests/tools/test_file.py
"""Tests for list_directory and find_files tools in src.tools.file."""

import json
from unittest.mock import patch

import pytest


@pytest.fixture()
def code_dir(tmp_path):
    """Create a temporary code_space_dir and patch settings."""
    with patch("src.tools.file.settings") as mock_settings:
        mock_settings.code_space_dir = str(tmp_path)
        mock_settings.docs_space_dir = str(tmp_path / "docs")
        yield tmp_path


class TestListDirectory:
    def test_lists_files_and_dirs(self, code_dir):
        """list_directory returns files and dirs with correct types."""
        from src.tools.file import list_directory

        (code_dir / "proj").mkdir()
        (code_dir / "proj" / "main.go").write_text("package main", encoding="utf-8")
        (code_dir / "proj" / "cmd").mkdir()

        result = json.loads(list_directory.invoke({"path": "proj"}))

        assert result["success"] is True
        entries = result["payload"]
        names = {e["name"] for e in entries}
        assert "main.go" in names
        assert "cmd" in names

        file_entry = next(e for e in entries if e["name"] == "main.go")
        assert file_entry["type"] == "file"
        assert "size" in file_entry

        dir_entry = next(e for e in entries if e["name"] == "cmd")
        assert dir_entry["type"] == "dir"

    def test_excludes_noise_dirs(self, code_dir):
        """list_directory excludes .git, node_modules, vendor, __pycache__."""
        from src.tools.file import list_directory

        proj = code_dir / "proj"
        proj.mkdir()
        (proj / ".git").mkdir()
        (proj / "node_modules").mkdir()
        (proj / "vendor").mkdir()
        (proj / "__pycache__").mkdir()
        (proj / "src").mkdir()

        result = json.loads(list_directory.invoke({"path": "proj"}))

        assert result["success"] is True
        names = {e["name"] for e in result["payload"]}
        assert ".git" not in names
        assert "node_modules" not in names
        assert "vendor" not in names
        assert "__pycache__" not in names
        assert "src" in names

    def test_nonexistent_path(self, code_dir):
        """list_directory returns fail for nonexistent path."""
        from src.tools.file import list_directory

        result = json.loads(list_directory.invoke({"path": "nonexistent"}))

        assert result["success"] is False
        assert "不存在" in result["error"]

    def test_max_depth_two(self, code_dir):
        """list_directory with max_depth=2 includes subdirectory contents."""
        from src.tools.file import list_directory

        proj = code_dir / "proj"
        (proj / "cmd").mkdir(parents=True)
        (proj / "cmd" / "main.go").write_text("package main", encoding="utf-8")

        result = json.loads(list_directory.invoke({"path": "proj", "max_depth": 2}))

        assert result["success"] is True
        entries = result["payload"]
        cmd_entry = next(e for e in entries if e["name"] == "cmd")
        assert "children" in cmd_entry
        child_names = {c["name"] for c in cmd_entry["children"]}
        assert "main.go" in child_names

    def test_empty_directory(self, code_dir):
        """list_directory returns empty list for empty dir."""
        from src.tools.file import list_directory

        (code_dir / "empty").mkdir()

        result = json.loads(list_directory.invoke({"path": "empty"}))

        assert result["success"] is True
        assert result["payload"] == []

    def test_truncates_large_directory(self, code_dir):
        """list_directory truncates when entries exceed 200."""
        from src.tools.file import list_directory

        proj = code_dir / "proj"
        proj.mkdir()
        for i in range(210):
            (proj / f"file_{i:03d}.go").write_text("package main", encoding="utf-8")

        result = json.loads(list_directory.invoke({"path": "proj"}))

        assert result["success"] is True
        assert len(result["payload"]) == 200
        assert "截断" in result["message"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/tools/test_file.py -v`
Expected: FAIL — `list_directory` not defined

- [ ] **Step 3: Implement `list_directory` in `src/tools/file.py`**

Append the following to the end of `src/tools/file.py`:

```python
# ---------------------------------------------------------------------------
# Directory & file search tools (project exploration)
# ---------------------------------------------------------------------------

_NOISE_DIRS = {".git", "node_modules", "vendor", "__pycache__", ".idea", ".vscode"}

MAX_DIR_ENTRIES = 200


@tool
def list_directory(path: str, max_depth: int = 1) -> str:
    """列出 code_space_dir 下指定路径的文件和子目录。

    Args:
        path: 相对于 code_space_dir 的目录路径。
        max_depth: 递归深度，1=仅当前层，2=包含子目录内容，以此类推。

    Returns:
        JSON Envelope 格式的响应字符串，payload 为目录条目列表。
    """
    target = Path(settings.code_space_dir) / path

    if not target.exists():
        return fail(error=f"目录 {path} 不存在")
    if not target.is_dir():
        return fail(error=f"{path} 不是一个目录")

    def _scan(dir_path: Path, depth: int) -> list[dict]:
        entries = []
        try:
            children = sorted(dir_path.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return entries

        for child in children:
            if child.name in _NOISE_DIRS:
                continue
            if child.is_dir():
                entry = {"name": child.name, "type": "dir"}
                if depth < max_depth:
                    entry["children"] = _scan(child, depth + 1)
                entries.append(entry)
            elif child.is_file():
                entries.append({
                    "name": child.name,
                    "type": "file",
                    "size": child.stat().st_size,
                })
        return entries

    entries = _scan(target, 1)

    if len(entries) > MAX_DIR_ENTRIES:
        entries = entries[:MAX_DIR_ENTRIES]
        return ok(
            message=f"目录 {path} 条目过多，已截断为前 {MAX_DIR_ENTRIES} 项",
            payload=entries,
        )

    return ok(message=f"已列出目录 {path}（{len(entries)} 项）", payload=entries)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/tools/test_file.py -v`
Expected: All 6 `TestListDirectory` tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/file.py tests/tools/test_file.py
git commit -m "feat: add list_directory tool for project exploration"
```

---

### Task 2: Add `find_files` tool

**Files:**
- Modify: `src/tools/file.py` (append new tool)
- Modify: `tests/tools/test_file.py` (add test class)

- [ ] **Step 1: Add failing tests to `tests/tools/test_file.py`**

Append to `tests/tools/test_file.py`:

```python
class TestFindFiles:
    def test_finds_go_files(self, code_dir):
        """find_files returns matching .go files."""
        from src.tools.file import find_files

        proj = code_dir / "proj"
        (proj / "cmd").mkdir(parents=True)
        (proj / "cmd" / "main.go").write_text("package main", encoding="utf-8")
        (proj / "cmd" / "README.md").write_text("# readme", encoding="utf-8")

        result = json.loads(find_files.invoke({"directory": "proj", "pattern": "**/*.go"}))

        assert result["success"] is True
        assert "proj/cmd/main.go" in result["payload"]
        assert not any(f.endswith(".md") for f in result["payload"])

    def test_finds_by_name(self, code_dir):
        """find_files matches specific filename patterns."""
        from src.tools.file import find_files

        proj = code_dir / "proj"
        (proj / "svc1" / "cmd").mkdir(parents=True)
        (proj / "svc2" / "cmd").mkdir(parents=True)
        (proj / "svc1" / "cmd" / "main.go").write_text("package main", encoding="utf-8")
        (proj / "svc2" / "cmd" / "main.go").write_text("package main", encoding="utf-8")

        result = json.loads(find_files.invoke({"directory": "proj", "pattern": "**/main.go"}))

        assert result["success"] is True
        assert len(result["payload"]) == 2

    def test_excludes_noise_dirs(self, code_dir):
        """find_files excludes .git, vendor, etc."""
        from src.tools.file import find_files

        proj = code_dir / "proj"
        (proj / "src").mkdir(parents=True)
        (proj / "vendor" / "lib").mkdir(parents=True)
        (proj / "src" / "main.go").write_text("package main", encoding="utf-8")
        (proj / "vendor" / "lib" / "dep.go").write_text("package lib", encoding="utf-8")

        result = json.loads(find_files.invoke({"directory": "proj", "pattern": "**/*.go"}))

        assert result["success"] is True
        paths = result["payload"]
        assert any("src/main.go" in p for p in paths)
        assert not any("vendor" in p for p in paths)

    def test_empty_result(self, code_dir):
        """find_files returns empty list when no match."""
        from src.tools.file import find_files

        (code_dir / "proj").mkdir()

        result = json.loads(find_files.invoke({"directory": "proj", "pattern": "**/*.go"}))

        assert result["success"] is True
        assert result["payload"] == []

    def test_nonexistent_directory(self, code_dir):
        """find_files returns fail for nonexistent directory."""
        from src.tools.file import find_files

        result = json.loads(find_files.invoke({"directory": "nonexistent", "pattern": "*.go"}))

        assert result["success"] is False

    def test_truncates_large_result(self, code_dir):
        """find_files truncates results exceeding 100 files."""
        from src.tools.file import find_files

        proj = code_dir / "proj"
        proj.mkdir()
        for i in range(110):
            (proj / f"file_{i:03d}.go").write_text("package main", encoding="utf-8")

        result = json.loads(find_files.invoke({"directory": "proj", "pattern": "*.go"}))

        assert result["success"] is True
        assert len(result["payload"]) == 100
        assert "截断" in result["message"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/tools/test_file.py::TestFindFiles -v`
Expected: FAIL — `find_files` not defined

- [ ] **Step 3: Implement `find_files` in `src/tools/file.py`**

Append to the end of `src/tools/file.py` (after `list_directory`):

```python
MAX_FIND_RESULTS = 100


@tool
def find_files(directory: str, pattern: str) -> str:
    """在 code_space_dir 下指定目录中按 glob 模式搜索文件。

    Args:
        directory: 相对于 code_space_dir 的搜索起始目录。
        pattern: glob 模式，如 "*.go"、"**/main.go"、"**/deploy/*.yaml"。

    Returns:
        JSON Envelope 格式的响应字符串，payload 为匹配文件路径列表（相对于 code_space_dir）。
    """
    base = Path(settings.code_space_dir)
    target = base / directory

    if not target.exists():
        return fail(error=f"目录 {directory} 不存在")
    if not target.is_dir():
        return fail(error=f"{directory} 不是一个目录")

    matches = []
    for path in sorted(target.glob(pattern)):
        if not path.is_file():
            continue
        # Skip noise directories
        parts = path.relative_to(base).parts
        if any(part in _NOISE_DIRS for part in parts):
            continue
        matches.append(str(path.relative_to(base)))

    if len(matches) > MAX_FIND_RESULTS:
        matches = matches[:MAX_FIND_RESULTS]
        return ok(
            message=f"匹配文件过多，已截断为前 {MAX_FIND_RESULTS} 项",
            payload=matches,
        )

    return ok(
        message=f"找到 {len(matches)} 个匹配文件",
        payload=matches,
    )
```

- [ ] **Step 4: Run all file tool tests**

Run: `pytest tests/tools/test_file.py -v`
Expected: All `TestListDirectory` + `TestFindFiles` tests PASS

- [ ] **Step 5: Export new tools from `src/tools/__init__.py`**

Edit `src/tools/__init__.py` — add imports and `__all__` entries:

```python
from src.tools.file import find_files, list_directory, read_file, write_file
```

Add `"find_files"` and `"list_directory"` to `__all__`.

- [ ] **Step 6: Commit**

```bash
git add src/tools/file.py src/tools/__init__.py tests/tools/test_file.py
git commit -m "feat: add find_files tool for project exploration"
```

---

### Task 3: Add `project_explore` prompt templates

**Files:**
- Create: `src/prompts/system/project_explore.md`
- Create: `src/prompts/user/project_explore.md`
- Modify: `src/prompts/system/intent.md`

- [ ] **Step 1: Create system prompt**

Create `src/prompts/system/project_explore.md`:

```markdown
你是一个项目结构分析专家。你的任务是探索给定项目，生成项目结构汇总文档。

## 目标

你有 3 个目标，必须全部达成后立即停止：

1. 这个项目下有几个服务？
2. 每个服务属于什么类型？（API后端服务 / 定时任务 / 消息订阅）
3. 每个服务负责的全部功能（不能遗漏任何一个）

## 探索策略

- 你可以自由使用任何工具，以任何顺序，直到所有目标明确
- 优先读取部署配置文件（通常在 deploy 目录下），快速了解服务数量和类型
- 找到入口文件（如 main.go）确认服务角色
- 对于 API 服务：找到路由注册代码，穷举所有 API 端点及其处理函数文件
- 对于定时任务：找到 cron 调度注册，列出触发规则和处理函数文件
- 对于消息订阅：找到订阅注册代码，列出订阅名称和处理函数文件
- 重点是完整性——不遗漏任何功能点
- 达到目标后立即停止，不做多余探索

## 可用工具

- list_directory: 列出目录下的文件和子目录，支持控制递归深度
- find_files: 按 glob 模式搜索文件（如 `**/main.go`、`**/*.yaml`）
- read_file: 读取文件完整内容
- find_function: 按名称搜索函数定义
- find_struct: 按名称搜索 struct 定义
- load_docgen_config: 加载项目的 .doc_gen.yaml 配置文件
- write_file: 将最终结果写入文件

## 输出

当所有目标达成后，调用 write_file 工具将结果写入 `{项目名称}/task.md`，严格按照以下格式：

```
# {项目名称}

## 项目概览
- 语言: {语言}
- 服务数量: {N}

## 服务列表

### 1. {服务名} ({服务类型})
入口: {项目名称}/{入口文件相对路径}

#### API 列表
| 路由 | 方法 | 处理文件 |
|------|------|---------|
| /api/v1/xxx | POST | {项目名称}/xxx/logic/Xxx.go |

#### 定时任务列表
| 触发规则 | 处理文件 |
|---------|---------|
| 0 3 * * * | {项目名称}/xxx/logic/Xxx.go |

#### 消息订阅列表
| 订阅名称 | 处理文件 |
|---------|---------|
| order.created | {项目名称}/xxx/logic/Xxx.go |
```

## 规则

- 所有文件路径从项目名称开始，如 `ubill-access-api/ubill-order/logic/BuyResource.go`
- 不写说明、描述、注释——只列举事实数据
- 每个服务只输出其对应类型的列表（API 服务只有 API 列表，定时任务只有定时任务列表，以此类推）
- 写入完成后，不需要再做任何操作
```

- [ ] **Step 2: Create user prompt**

Create `src/prompts/user/project_explore.md`:

```markdown
用户输入：{user_input}
```

- [ ] **Step 3: Update intent prompt**

Edit `src/prompts/system/intent.md` — add `project_explore` intent to the list of available intents. The new line goes after the `doc_gen` line:

```
- project_explore：用户想要探索分析一个项目的结构，了解项目有哪些服务、API、定时任务或消息订阅（如"探索 ubill-access-api 项目"、"分析 xxx 项目结构"）
```

- [ ] **Step 4: Verify prompt loading**

Run: `python -c "from src.prompts import load_prompt; p = load_prompt('project_explore'); print('OK:', len(p.messages))"`
Expected: `OK: 2`

- [ ] **Step 5: Commit**

```bash
git add src/prompts/system/project_explore.md src/prompts/user/project_explore.md src/prompts/system/intent.md
git commit -m "feat: add project_explore prompt templates and intent"
```

---

### Task 4: Add `project_explore` node and graph wiring

**Files:**
- Modify: `src/graph/nodes.py`
- Modify: `src/graph/graph.py`
- Test: `tests/graph/test_project_explore.py`

- [ ] **Step 1: Write failing tests**

Create `tests/graph/test_project_explore.py`:

```python
"""Tests for the project_explore node and routing."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

if "mysql" not in sys.modules:
    sys.modules["mysql"] = MagicMock()
    sys.modules["mysql.connector"] = MagicMock()


@pytest.fixture
def mock_state():
    return {
        "messages": [HumanMessage(content="探索 ubill-access-api 项目")],
        "intent": "project_explore",
    }


@pytest.fixture
def mock_config():
    return {"configurable": {}}


async def test_project_explore_binds_tools_and_returns_message(mock_state, mock_config):
    """project_explore binds EXPLORE_TOOLS to the LLM and returns its response."""
    mock_llm = AsyncMock()
    mock_response = AIMessage(content="开始探索项目...")
    mock_llm.ainvoke.return_value = mock_response
    mock_llm.bind_tools.return_value = mock_llm

    with patch("src.graph.nodes.get_llm", return_value=mock_llm):
        from src.graph.nodes import project_explore, EXPLORE_TOOLS
        result = await project_explore(mock_state, mock_config)

    mock_llm.bind_tools.assert_called_once_with(EXPLORE_TOOLS)
    assert result == {"messages": [mock_response]}


async def test_project_explore_uses_correct_prompt(mock_state, mock_config):
    """project_explore loads the 'project_explore' prompt."""
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = AIMessage(content="ok")
    mock_llm.bind_tools.return_value = mock_llm

    with patch("src.graph.nodes.get_llm", return_value=mock_llm), \
         patch("src.graph.nodes.load_prompt") as mock_load:
        mock_prompt = MagicMock()
        mock_prompt.format_messages.return_value = []
        mock_load.return_value = mock_prompt

        from src.graph.nodes import project_explore
        await project_explore(mock_state, mock_config)

    mock_load.assert_called_once_with("project_explore")


class TestRouteProjectExplore:
    def test_routes_to_tools_when_tool_calls_present(self):
        """route_project_explore returns 'explore_tools' when tool_calls present."""
        from src.graph.nodes import route_project_explore

        msg = AIMessage(content="", tool_calls=[{"name": "list_directory", "args": {"path": "proj"}, "id": "1"}])
        state = {"messages": [msg]}

        assert route_project_explore(state) == "explore_tools"

    def test_routes_to_end_when_no_tool_calls(self):
        """route_project_explore returns END when no tool_calls."""
        from src.graph.nodes import route_project_explore
        from langgraph.graph import END

        msg = AIMessage(content="探索完成")
        state = {"messages": [msg]}

        assert route_project_explore(state) == END


class TestRouteByIntent:
    def test_routes_to_project_explore(self):
        """route_by_intent returns 'project_explore' for project_explore intent."""
        from src.graph.nodes import route_by_intent

        state = {"intent": "project_explore"}

        assert route_by_intent(state) == "project_explore"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/graph/test_project_explore.py -v`
Expected: FAIL — `project_explore`, `route_project_explore` not defined, `route_by_intent` doesn't handle `project_explore`

- [ ] **Step 3: Add `project_explore` node and routing to `src/graph/nodes.py`**

Add imports at the top of `src/graph/nodes.py` (alongside existing tool imports):

```python
from src.tools import (
    find_files,
    find_function,
    find_struct,
    list_directory,
    load_docgen_config,
    match_api_name,
    query_api_index,
    read_file,
    save_api_index,
    write_file,
)
```

Add after `DOC_GEN_TOOLS` list definition (after line 83):

```python
EXPLORE_TOOLS = [
    list_directory,
    find_files,
    read_file,
    find_function,
    find_struct,
    load_docgen_config,
    write_file,
]
```

Add `route_by_intent` mapping — change the function body to include `project_explore`:

```python
def route_by_intent(state: State) -> str:
    """根据意图识别结果路由到对应节点。"""
    if state["intent"] == "doc_qa":
        return "doc_qa"
    if state["intent"] == "doc_gen":
        return "doc_gen"
    if state["intent"] == "chat":
        return "chat"
    if state["intent"] == "project_explore":
        return "project_explore"
    return END
```

Add the `project_explore` node function (after `doc_gen`):

```python
async def project_explore(state: State, config: RunnableConfig) -> dict:
    """项目探索节点。

    使用 LLM + 工具以 ReAct 方式探索项目结构，
    发现服务、识别类型、穷举功能点，输出 task.md。
    """
    prompt = load_prompt("project_explore")
    user_input = _get_last_human_message(state["messages"])

    system_messages = prompt.format_messages(user_input=user_input)

    llm = get_llm("project_explore")
    llm_with_tools = llm.bind_tools(EXPLORE_TOOLS)

    all_messages = system_messages + state["messages"]
    response = await llm_with_tools.ainvoke(all_messages, config=config)

    logger.info("项目探索节点调用完成")
    return {"messages": [response]}
```

Add the routing function (after `route_doc_gen`):

```python
def route_project_explore(state: State) -> str:
    """根据 LLM 是否发起工具调用决定下一步。"""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "explore_tools"
    return END
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/graph/test_project_explore.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Wire up the graph in `src/graph/graph.py`**

Update imports in `src/graph/graph.py`:

```python
from src.graph.nodes import (
    DOC_GEN_TOOLS,
    EXPLORE_TOOLS,
    State,
    chat,
    doc_gen,
    doc_qa,
    intent_recognize,
    project_explore,
    route_by_intent,
    route_doc_gen,
    route_project_explore,
)
```

In `build_graph`, add the new nodes and edges after the existing ones (before the `return` statement):

```python
    graph.add_node("project_explore", project_explore)
    graph.add_node("explore_tools", ToolNode(tools=EXPLORE_TOOLS))

    # ...existing conditional edges for intent_recognize — update the list:
    graph.add_conditional_edges(
        "intent_recognize", route_by_intent,
        ["doc_qa", "doc_gen", "chat", "project_explore", "__end__"]
    )

    # project_explore ReAct loop
    graph.add_conditional_edges(
        "project_explore", route_project_explore, ["explore_tools", "__end__"]
    )
    graph.add_edge("explore_tools", "project_explore")
```

- [ ] **Step 6: Run all tests**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/graph/nodes.py src/graph/graph.py tests/graph/test_project_explore.py
git commit -m "feat: add project_explore node with ReAct loop and graph wiring"
```

---

### Task 5: Update `app.py` streaming filter

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add `project_explore` to the streaming filter**

In `app.py`, change the node filter in the streaming loop (line 61):

From:
```python
and metadata["langgraph_node"] in ("doc_qa", "doc_gen", "chat")
```

To:
```python
and metadata["langgraph_node"] in ("doc_qa", "doc_gen", "chat", "project_explore")
```

- [ ] **Step 2: Run all tests to verify nothing is broken**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: stream project_explore output in Chainlit UI"
```

---

### Task 6: Final verification

- [ ] **Step 1: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS, no warnings about missing imports

- [ ] **Step 2: Verify graph compiles without errors**

Run: `python -c "from src.graph import build_graph; g = build_graph(); print('Graph nodes:', list(g.get_graph().nodes.keys()))"`
Expected: Output includes `project_explore` and `explore_tools` alongside existing nodes

- [ ] **Step 3: Verify prompt loads correctly**

Run: `python -c "from src.prompts import load_prompt; p = load_prompt('project_explore'); print('Messages:', len(p.messages)); print('Vars:', p.input_variables)"`
Expected: `Messages: 2`, `Vars: ['user_input']`

- [ ] **Step 4: Commit if any final adjustments were made**

```bash
git add -A
git commit -m "chore: final verification for project_explore feature"
```
