# find_function Tool Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `find_function` tool that locates Go function definitions by name in one tool call, replacing the current multi-step blind search.

**Architecture:** New `@tool` function in `src/tools/code_search.py` that regex-matches `func <name>(` patterns across `.go` files. Integrated into the `TOOLS` list for `doc_gen` node. Prompt updated with usage guidance and fallback rules.

**Tech Stack:** Python, LangChain `@tool`, regex, pathlib

---

## Chunk 1: find_function Tool

### Task 1: find_function — Core Functionality

**Files:**
- Create: `tests/tools/test_code_search.py`
- Create: `src/tools/code_search.py`

- [ ] **Step 1: Write failing test — find plain function definition**

```python
# tests/tools/test_code_search.py
"""code_search 工具测试。"""

import json

from src.config import settings
from src.tools.code_search import find_function


class TestFindFunction:
    def test_finds_plain_function(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        go_dir = tmp_path / "service"
        go_dir.mkdir()
        (go_dir / "buy.go").write_text(
            "package service\n\nfunc buyResourcePostPaid(ctx context.Context) error {\n\treturn nil\n}\n"
        )

        result = json.loads(find_function.invoke({"function_name": "buyResourcePostPaid", "directory": "service"}))
        assert result["success"] is True
        assert result["payload"]["file"].endswith("service/buy.go")
        assert result["payload"]["line"] == 3
        assert "buyResourcePostPaid" in result["payload"]["content"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_code_search.py::TestFindFunction::test_finds_plain_function -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Write minimal implementation**

```python
# src/tools/code_search.py
"""代码搜索工具模块。

提供在 Go 源码中按函数名精确定位函数定义的能力。
"""

import re
from pathlib import Path

from langchain.tools import tool

from src.config import settings
from src.logs import get_logger
from src.tools.utils import fail, ok

logger = get_logger(__name__)


@tool
def find_function(function_name: str, directory: str = ".") -> str:
    """在指定目录下查找 Go 函数的定义位置。
    仅当你需要定位一个具体的函数或方法的定义所在文件时使用此工具，
    不要用于通用代码搜索。
    传入函数名（不含 func 关键字），工具会自动匹配普通函数和方法定义。

    Args:
        function_name: 要查找的函数名，如 "buyResourcePostPaid"
        directory: 搜索起始目录，默认为 "."

    Returns:
        JSON envelope，payload 包含 file（文件路径）、line（行号）、content（该行内容）。
    """
    dir_path = Path(settings.agent_work_dir) / directory

    if not dir_path.exists():
        logger.error("搜索失败：目录 %s 不存在", directory)
        return fail(f"目录 {directory} 不存在，请确认路径是否正确")

    if not dir_path.is_dir():
        logger.error("搜索失败：%s 不是目录", directory)
        return fail(f"{directory} 不是一个目录")

    escaped_name = re.escape(function_name)
    pattern = re.compile(rf"^func\s+(\(.*?\)\s+)?{escaped_name}\s*\(")

    go_files = sorted(
        f for f in dir_path.rglob("*.go") if not f.name.endswith("_test.go")
    )

    for go_file in go_files:
        try:
            content = go_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = go_file.read_text(encoding="latin-1")
            except Exception:
                continue

        for line_num, line in enumerate(content.splitlines(), 1):
            if pattern.match(line):
                rel_path = str(go_file.relative_to(Path(settings.agent_work_dir)))
                logger.info("找到函数 %s 定义：%s:%d", function_name, rel_path, line_num)
                return ok(
                    "找到函数定义",
                    payload={"file": rel_path, "line": line_num, "content": line.strip()},
                )

    logger.info("未找到函数 %s 的定义", function_name)
    return fail(f"未找到函数 {function_name} 的定义")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/test_code_search.py::TestFindFunction::test_finds_plain_function -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/code_search.py tests/tools/test_code_search.py
git commit -m "feat: add find_function tool with plain function test"
```

### Task 2: find_function — Method Receiver & Edge Cases

**Files:**
- Modify: `tests/tools/test_code_search.py`

- [ ] **Step 1: Write failing tests for remaining cases**

Append to `TestFindFunction` class in `tests/tools/test_code_search.py`:

```python
    def test_finds_method_with_receiver(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        go_dir = tmp_path / "service"
        go_dir.mkdir()
        (go_dir / "svc.go").write_text(
            "package service\n\nfunc (s *Service) ProcessOrder(ctx context.Context) error {\n\treturn nil\n}\n"
        )

        result = json.loads(find_function.invoke({"function_name": "ProcessOrder", "directory": "service"}))
        assert result["success"] is True
        assert result["payload"]["line"] == 3
        assert "ProcessOrder" in result["payload"]["content"]

    def test_returns_fail_when_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        go_dir = tmp_path / "service"
        go_dir.mkdir()
        (go_dir / "empty.go").write_text("package service\n")

        result = json.loads(find_function.invoke({"function_name": "nonExistent", "directory": "service"}))
        assert result["success"] is False
        assert "nonExistent" in result["error"]

    def test_excludes_test_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        go_dir = tmp_path / "service"
        go_dir.mkdir()
        (go_dir / "buy_test.go").write_text(
            "package service\n\nfunc TestBuy(t *testing.T) {\n}\n"
        )

        result = json.loads(find_function.invoke({"function_name": "TestBuy", "directory": "service"}))
        assert result["success"] is False

    def test_fails_when_directory_not_exists(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        result = json.loads(find_function.invoke({"function_name": "Foo", "directory": "no_such_dir"}))
        assert result["success"] is False
        assert "不存在" in result["error"]

    def test_fails_when_path_is_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        (tmp_path / "a_file.txt").write_text("hello")

        result = json.loads(find_function.invoke({"function_name": "Foo", "directory": "a_file.txt"}))
        assert result["success"] is False
        assert "不是一个目录" in result["error"]

    def test_handles_regex_special_chars_in_name(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        go_dir = tmp_path / "service"
        go_dir.mkdir()
        (go_dir / "main.go").write_text("package service\n\nfunc normalFunc() {}\n")

        result = json.loads(find_function.invoke({"function_name": "foo.*bar", "directory": "service"}))
        assert result["success"] is False

    def test_handles_non_utf8_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        go_dir = tmp_path / "service"
        go_dir.mkdir()
        (go_dir / "binary.go").write_bytes(b"package service\n\nfunc Target() {}\n\xff\xfe")

        result = json.loads(find_function.invoke({"function_name": "Target", "directory": "service"}))
        assert result["success"] is True
        assert result["payload"]["line"] == 3
```

- [ ] **Step 2: Run tests to verify they all pass (implementation already handles these cases)**

Run: `uv run pytest tests/tools/test_code_search.py -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add tests/tools/test_code_search.py
git commit -m "test: add edge case tests for find_function"
```

### Task 3: Integrate find_function into Graph

**Files:**
- Modify: `src/graph/nodes.py:77-81` (import and TOOLS list)
- Modify: `tests/graph/test_nodes.py` (add assertion)

- [ ] **Step 1: Write failing test — verify find_function is in TOOLS**

Add to `TestDocGen` class in `tests/graph/test_nodes.py`, inside `test_binds_tools_to_llm`:

After the existing assertions (line 175), add:

```python
        assert "find_function" in tool_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/graph/test_nodes.py::TestDocGen::test_binds_tools_to_llm -v`
Expected: FAIL ("find_function" not in tool_names)

- [ ] **Step 3: Add import and update TOOLS list**

In `src/graph/nodes.py`, change lines 77-81:

```python
from src.tools.code_scanner import scan_directory
from src.tools.file_reader import read_file
from src.tools.doc_storage import save_document, read_document, list_documents
from src.tools.code_search import find_function

TOOLS = [scan_directory, read_file, save_document, read_document, list_documents, find_function]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/graph/test_nodes.py::TestDocGen::test_binds_tools_to_llm -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to ensure no regressions**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/graph/nodes.py tests/graph/test_nodes.py
git commit -m "feat: integrate find_function into doc_gen TOOLS"
```

## Chunk 2: Prompt Update

### Task 4: Update doc_gen Prompt

**Files:**
- Modify: `src/prompts/system/doc_gen.md`

- [ ] **Step 1: Add find_function guidance to Task 1 section**

In `src/prompts/system/doc_gen.md`, in the Task 1 section, after step 4 (`Use scan_directory if needed to locate the file containing the next Unresolved item`), replace step 4 with:

```
4. Use `find_function` to locate the file containing the next Unresolved function or method. Only fall back to `scan_directory` for non-function references (e.g., struct types, constants).
```

- [ ] **Step 2: Add fallback rule after the loop steps**

After step 6 (`Repeat steps 2-5 until Unresolved is empty`), add:

```
**Fallback rule:** If `find_function` returns "未找到", do NOT attempt to locate that function through other means (`scan_directory` + `read_file` guessing). Skip it, and in the generated documentation mark it as: "该函数未找到定义，无法展开分析". Continue processing the next Unresolved reference.
```

- [ ] **Step 3: Commit**

```bash
git add src/prompts/system/doc_gen.md
git commit -m "docs: update doc_gen prompt with find_function guidance and fallback rule"
```

### Task 5: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update CLAUDE.md to reflect new tool**

In the `doc_gen` description section of CLAUDE.md, update the tools list:

Change:
```
`doc_gen` loads the `"doc_gen"` prompt, binds `TOOLS` (5 tools: `scan_directory`, `read_file`, `save_document`, `read_document`, `list_documents`) to `ChatOpenAI`.
```

To:
```
`doc_gen` loads the `"doc_gen"` prompt, binds `TOOLS` (6 tools: `scan_directory`, `read_file`, `save_document`, `read_document`, `list_documents`, `find_function`) to `ChatOpenAI`.
```

Also add to the tool constraints section:
```
- `find_function` searches Go function definitions by regex-matching `func <name>(` patterns. Returns only the first match (file path, line number, content). Auto-escapes regex special characters. Falls back to latin-1 encoding on `UnicodeDecodeError`.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with find_function tool"
```
