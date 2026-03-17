# API Matcher Tool Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `src/tools/api_matcher.py` — a LangChain tool that matches API names in a file using a user-provided regex pattern.

**Architecture:** Single-file tool module following the existing `ok()`/`fail()` JSON Envelope pattern used by `code_search.py` and `file.py`. The tool takes a file path (relative to `code_space_dir`) and a regex pattern with a capture group, scans the file line-by-line, and returns the first captured API name.

**Tech Stack:** Python 3.11+, `re` (stdlib), `pathlib` (stdlib), `langchain_core.tools`, project utilities (`src.tools.utils`, `src.config`, `src.logs`)

---

### Task 0: Test infrastructure — env var stubs for Settings

`Settings()` is instantiated at module import time (`from src.config import settings`). Without a `.env` file or env vars, this raises `ValidationError`. We need dummy env vars so tool modules can be imported in tests.

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add env var stubs to `tests/conftest.py`**

```python
# tests/conftest.py
"""Shared test fixtures."""

import os

import pytest

# Dummy env vars required by src.config.settings.Settings() so that tool
# modules can be imported in the test environment without a real .env file.
_DUMMY_ENV = {
    "CODE_SPACE_DIR": "/tmp/test-code",
    "DOCS_SPACE_DIR": "/tmp/test-docs",
    "LOG_LEVEL": "DEBUG",
    "LOG_DIR": "/tmp/test-logs",
    "LOG_BACKUP_COUNT": "1",
    "LANGSMITH_TRACING": "false",
    "LANGSMITH_API_KEY": "test-key",
    "LANGSMITH_PROJECT": "test",
    "LANGSMITH_ENDPOINT": "https://localhost",
    "LLM_BASE_URL": "https://localhost",
    "LLM_API_KEY": "test-key",
    "LLM_DEFAULT_MODEL": "test-model",
    "LLM_DOC_GEN_MODEL": "test-model",
    "LLM_CHAT_MODEL": "test-model",
}


@pytest.fixture(autouse=True)
def _stub_env(monkeypatch):
    """Inject dummy env vars so Settings() can be constructed in tests."""
    for key, val in _DUMMY_ENV.items():
        monkeypatch.setenv(key, val)
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `cd /Users/ithkeen/CodeSpace/agent-project/doc-flow && python -m pytest tests/ -v --ignore=tests/generator`
Expected: PASS (existing tests unaffected)

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add dummy env var stubs to conftest for Settings()"
```

---

### Task 1: Test — happy path match

**Files:**
- Create: `tests/tools/__init__.py`
- Create: `tests/tools/test_api_matcher.py`

- [ ] **Step 1: Create test directory and `__init__.py`**

```python
# tests/tools/__init__.py
# (empty file)
```

- [ ] **Step 2: Write the failing test for happy path**

```python
# tests/tools/test_api_matcher.py
"""Tests for src.tools.api_matcher."""

import json
from unittest.mock import patch

import pytest


@pytest.fixture()
def code_dir(tmp_path):
    """Create a temporary code_space_dir and patch settings."""
    with patch("src.tools.api_matcher.settings") as mock_settings:
        mock_settings.code_space_dir = str(tmp_path)
        yield tmp_path


def test_match_api_name_happy_path(code_dir):
    """Normal match: file contains http.HandlerFunc(DeleteResource)."""
    from src.tools.api_matcher import match_api_name

    go_file = code_dir / "router.go"
    go_file.write_text(
        'package main\n\nimport "net/http"\n\n'
        "func init() {\n"
        "    http.HandlerFunc(DeleteResource)\n"
        "}\n",
        encoding="utf-8",
    )

    result_str = match_api_name.invoke(
        {
            "file_path": "router.go",
            "pattern": r"http\.HandlerFunc\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)",
        }
    )
    result = json.loads(result_str)

    assert result["success"] is True
    assert result["payload"]["api_name"] == "DeleteResource"
    assert result["payload"]["file"] == "router.go"
    assert result["payload"]["line"] == 6
    assert "DeleteResource" in result["payload"]["content"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/ithkeen/CodeSpace/agent-project/doc-flow && python -m pytest tests/tools/test_api_matcher.py::test_match_api_name_happy_path -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.tools.api_matcher'`

---

### Task 2: Implement — minimal `match_api_name` tool

**Files:**
- Create: `src/tools/api_matcher.py`

- [ ] **Step 1: Write the implementation**

```python
"""API 名称匹配工具模块。

在 code_space_dir 下指定文件中，通过正则表达式的捕获组快速匹配 API 名称。
file_path 参数为相对于 code_space_dir 的路径，工具内部自动拼接为绝对路径。
"""

import re
from pathlib import Path

from langchain_core.tools import tool

from src.config import settings
from src.logs import get_logger
from src.tools.utils import fail, ok

logger = get_logger(__name__)


@tool
def match_api_name(file_path: str, pattern: str) -> str:
    """在 code_space_dir 下指定文件中，使用正则表达式匹配 API 名称。

    传入一个正则表达式（必须包含至少一个捕获组），工具会逐行扫描文件，
    返回第一个匹配的捕获组内容作为 API 名称。
    若正则包含多个捕获组，仅使用第一个捕获组（group(1)）。

    Args:
        file_path: 相对于 code_space_dir 的文件路径，如 "ubill-access-api/router.go"
        pattern: 正则表达式字符串，必须包含至少一个捕获组，第一个捕获组即为 API 名称

    Returns:
        JSON Envelope 格式的响应字符串：
        - 成功: {"success": true, "message": "...", "payload": {...}, "error": null}
        - 失败: {"success": false, "message": "...", "payload": null, "error": "..."}
    """
    try:
        return _match(file_path, pattern)
    except Exception as exc:
        logger.error("匹配过程发生意外错误: %s", exc, exc_info=True)
        return fail(f"匹配过程发生意外错误: {exc}")


def _match(file_path: str, pattern: str) -> str:
    """Internal implementation, wrapped by the tool function's catch-all."""

    # 1. Validate file_path
    if not file_path or not file_path.strip():
        return fail("文件路径不能为空")

    # 2. Validate pattern
    if not pattern or not pattern.strip():
        return fail("匹配模式不能为空")

    # 3. Compile regex
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        logger.error("无效的正则表达式: %s — %s", pattern, exc)
        return fail(f"无效的正则表达式: {exc}")

    # 4. Verify at least one capture group
    if compiled.groups < 1:
        logger.error("正则表达式缺少捕获组: %s", pattern)
        return fail("正则表达式必须包含至少一个捕获组")

    # 5. Build absolute path
    target = Path(settings.code_space_dir) / file_path

    # 6. Validate file exists and is a file
    if not target.exists():
        logger.error("文件不存在: %s", file_path)
        return fail(f"文件不存在: {file_path}")

    if not target.is_file():
        logger.error("%s 是目录，不是文件", file_path)
        return fail(f"{file_path} 是目录，不是文件")

    # 7. Read file content (UTF-8, fallback Latin-1)
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        logger.warning("文件编码回退: %s 非 UTF-8，使用 latin-1 重新读取", file_path)
        try:
            content = target.read_text(encoding="latin-1")
        except Exception as exc:
            logger.error("文件读取失败: %s — %s", file_path, exc)
            return fail(f"文件读取失败: {exc}")

    # 8. Line-by-line search — return first match
    for line_num, line in enumerate(content.splitlines(), 1):
        m = compiled.search(line)
        if m:
            api_name = m.group(1)
            logger.info("匹配到 API: %s（文件: %s, 第 %d 行）", api_name, file_path, line_num)
            return ok(
                message=f"匹配到 API: {api_name}（文件: {file_path}, 第 {line_num} 行）",
                payload={
                    "api_name": api_name,
                    "file": file_path,
                    "line": line_num,
                    "content": line.strip(),
                },
            )

    # 9. No match
    logger.info("文件 %s 中未匹配到符合模式的 API", file_path)
    return fail("文件中未匹配到符合模式的 API")
```

- [ ] **Step 2: Run the happy-path test to verify it passes**

Run: `cd /Users/ithkeen/CodeSpace/agent-project/doc-flow && python -m pytest tests/tools/test_api_matcher.py::test_match_api_name_happy_path -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/tools/api_matcher.py tests/tools/__init__.py tests/tools/test_api_matcher.py
git commit -m "feat: add match_api_name tool with happy-path test"
```

---

### Task 3: Test — error cases

**Files:**
- Modify: `tests/tools/test_api_matcher.py`

- [ ] **Step 1: Write failing tests for all error scenarios**

Append to `tests/tools/test_api_matcher.py`:

```python
def test_empty_file_path(code_dir):
    """Empty file_path returns fail."""
    from src.tools.api_matcher import match_api_name

    result = json.loads(match_api_name.invoke({"file_path": "  ", "pattern": r"(\w+)"}))
    assert result["success"] is False
    assert "文件路径不能为空" in result["error"]


def test_empty_pattern(code_dir):
    """Empty pattern returns fail."""
    from src.tools.api_matcher import match_api_name

    (code_dir / "a.go").write_text("x", encoding="utf-8")
    result = json.loads(match_api_name.invoke({"file_path": "a.go", "pattern": ""}))
    assert result["success"] is False
    assert "匹配模式不能为空" in result["error"]


def test_invalid_regex(code_dir):
    """Invalid regex returns fail."""
    from src.tools.api_matcher import match_api_name

    (code_dir / "a.go").write_text("x", encoding="utf-8")
    result = json.loads(match_api_name.invoke({"file_path": "a.go", "pattern": r"(["}))
    assert result["success"] is False
    assert "无效的正则表达式" in result["error"]


def test_no_capture_group(code_dir):
    """Pattern without capture group returns fail."""
    from src.tools.api_matcher import match_api_name

    (code_dir / "a.go").write_text("hello", encoding="utf-8")
    result = json.loads(match_api_name.invoke({"file_path": "a.go", "pattern": r"hello"}))
    assert result["success"] is False
    assert "捕获组" in result["error"]


def test_file_not_found(code_dir):
    """Non-existent file returns fail."""
    from src.tools.api_matcher import match_api_name

    result = json.loads(
        match_api_name.invoke({"file_path": "no_such.go", "pattern": r"(\w+)"})
    )
    assert result["success"] is False
    assert "文件不存在" in result["error"]


def test_path_is_directory(code_dir):
    """Directory path returns fail."""
    from src.tools.api_matcher import match_api_name

    subdir = code_dir / "subdir"
    subdir.mkdir()
    result = json.loads(match_api_name.invoke({"file_path": "subdir", "pattern": r"(\w+)"}))
    assert result["success"] is False
    assert "目录" in result["error"]


def test_no_match(code_dir):
    """File with no matching content returns fail."""
    from src.tools.api_matcher import match_api_name

    (code_dir / "empty.go").write_text("package main\n", encoding="utf-8")
    result = json.loads(
        match_api_name.invoke(
            {
                "file_path": "empty.go",
                "pattern": r"http\.HandlerFunc\(\s*([a-zA-Z_]\w*)\s*\)",
            }
        )
    )
    assert result["success"] is False
    assert "未匹配到" in result["error"]


def test_multiple_capture_groups_uses_first(code_dir):
    """When pattern has multiple capture groups, only group(1) is used."""
    from src.tools.api_matcher import match_api_name

    (code_dir / "multi.go").write_text(
        "route.Handle(GET, /api/v1, Handler)\n", encoding="utf-8"
    )
    # Two capture groups: (GET) and (Handler)
    result = json.loads(
        match_api_name.invoke(
            {
                "file_path": "multi.go",
                "pattern": r"route\.Handle\((\w+),\s*\S+,\s*(\w+)\)",
            }
        )
    )
    assert result["success"] is True
    assert result["payload"]["api_name"] == "GET"
```

- [ ] **Step 2: Run all tests to verify they pass**

Run: `cd /Users/ithkeen/CodeSpace/agent-project/doc-flow && python -m pytest tests/tools/test_api_matcher.py -v`
Expected: ALL PASS (8 tests)

- [ ] **Step 3: Commit**

```bash
git add tests/tools/test_api_matcher.py
git commit -m "test: add error-case and edge-case tests for match_api_name"
```
