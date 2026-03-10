# AGENT_WORK_DIR Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `AGENT_WORK_DIR` env var so all tools resolve paths relative to a configurable working directory; fix `doc_storage.py` to use `settings.docs_output_dir` instead of hardcoded `DOCS_BASE_DIR`.

**Architecture:** Settings singleton gains `agent_work_dir: str = "."`. Each tool prepends `Path(settings.agent_work_dir)` to user-supplied paths. `doc_storage.py` switches from hardcoded `DOCS_BASE_DIR` to `settings.docs_output_dir`. Tests deleted first, reimplemented after code changes.

**Tech Stack:** Python 3.11, pydantic-settings, LangChain @tool, pytest, uv

---

### Task 1: Delete old tool tests

**Files:**
- Delete: `tests/tools/test_code_scanner_logging.py`
- Delete: `tests/tools/test_doc_storage_logging.py`
- Delete: `tests/tools/test_file_reader_logging.py`
- Delete: `tests/tools/test_git_ops_logging.py`

**Step 1: Delete the 4 test files**

```bash
rm tests/tools/test_code_scanner_logging.py tests/tools/test_doc_storage_logging.py tests/tools/test_file_reader_logging.py tests/tools/test_git_ops_logging.py
```

**Step 2: Verify remaining tests still pass**

Run: `uv run pytest tests/ -v`
Expected: All remaining tests PASS (config, logs, prompts, graph tests unaffected)

**Step 3: Commit**

```bash
git add -u tests/tools/
git commit -m "test: remove old tool tests before AGENT_WORK_DIR refactor"
```

---

### Task 2: Add `agent_work_dir` to Settings

**Files:**
- Modify: `src/config/settings.py:63-78` (Settings class)
- Modify: `.env.example`
- Test: `tests/config/test_settings.py`

**Step 1: Write the failing test**

Add to `tests/config/test_settings.py`, inside `class TestSettings`:

```python
def test_agent_work_dir_default(self, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.delenv("AGENT_WORK_DIR", raising=False)

    s = Settings(_env_file=None)
    assert s.agent_work_dir == "."

def test_agent_work_dir_from_env(self, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("AGENT_WORK_DIR", "/home/user/go-project")

    s = Settings(_env_file=None)
    assert s.agent_work_dir == "/home/user/go-project"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/config/test_settings.py::TestSettings::test_agent_work_dir_default -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'agent_work_dir'`

**Step 3: Write minimal implementation**

In `src/config/settings.py`, add `agent_work_dir` field to `Settings` class, right above `docs_output_dir`:

```python
class Settings(BaseSettings):
    # ... existing docstring and model_config ...

    agent_work_dir: str = "."
    docs_output_dir: str = "./docs"
    # ... rest unchanged ...
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/config/test_settings.py::TestSettings -v`
Expected: PASS

**Step 5: Update .env.example**

Add after `LLM_MODEL` line and before `DOCS_OUTPUT_DIR`:

```
# Agent 工作目录（Go 项目根目录）
AGENT_WORK_DIR=.
```

**Step 6: Commit**

```bash
git add src/config/settings.py .env.example tests/config/test_settings.py
git commit -m "feat(config): add AGENT_WORK_DIR setting"
```

---

### Task 3: Update `code_scanner.py` to use `agent_work_dir`

**Files:**
- Modify: `src/tools/code_scanner.py:1-7,23`
- Test: `tests/tools/test_code_scanner.py` (new)

**Step 1: Write the failing test**

Create `tests/tools/test_code_scanner.py`:

```python
"""code_scanner 工具测试。"""

import json

import pytest

from src.config import settings
from src.tools.code_scanner import scan_directory


class TestScanDirectory:
    def test_scans_under_agent_work_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        go_dir = tmp_path / "handler"
        go_dir.mkdir()
        (go_dir / "main.go").write_text("package handler")
        (go_dir / "main_test.go").write_text("package handler")

        result = json.loads(scan_directory.invoke({"directory_path": "handler"}))
        assert result["success"] is True
        assert "1" in result["message"]

    def test_fails_when_dir_not_in_work_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        result = json.loads(scan_directory.invoke({"directory_path": "no_such_dir"}))
        assert result["success"] is False

    def test_fails_when_path_is_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        (tmp_path / "a_file.txt").write_text("hello")

        result = json.loads(scan_directory.invoke({"directory_path": "a_file.txt"}))
        assert result["success"] is False

    def test_returns_no_go_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        (tmp_path / "subdir").mkdir()

        result = json.loads(scan_directory.invoke({"directory_path": "subdir"}))
        assert result["success"] is True
        assert "未发现" in result["message"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_code_scanner.py::TestScanDirectory::test_scans_under_agent_work_dir -v`
Expected: FAIL (path `handler` resolved relative to CWD, not `tmp_path`)

**Step 3: Write minimal implementation**

In `src/tools/code_scanner.py`, add import and change path resolution:

```python
from src.config import settings
```

Change line 23 from:
```python
dir_path = Path(directory_path)
```
to:
```python
dir_path = Path(settings.agent_work_dir) / directory_path
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/tools/test_code_scanner.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/tools/code_scanner.py tests/tools/test_code_scanner.py
git commit -m "feat(tools): code_scanner resolves paths under AGENT_WORK_DIR"
```

---

### Task 4: Update `file_reader.py` to use `agent_work_dir`

**Files:**
- Modify: `src/tools/file_reader.py:1-8,26`
- Test: `tests/tools/test_file_reader.py` (new)

**Step 1: Write the failing test**

Create `tests/tools/test_file_reader.py`:

```python
"""file_reader 工具测试。"""

import json

import pytest

from src.config import settings
from src.tools.file_reader import read_file


class TestReadFile:
    def test_reads_file_under_agent_work_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        (tmp_path / "main.go").write_text("package main", encoding="utf-8")

        result = json.loads(read_file.invoke({"file_path": "main.go"}))
        assert result["success"] is True
        assert result["payload"] == "package main"

    def test_fails_when_file_not_exists(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        result = json.loads(read_file.invoke({"file_path": "ghost.go"}))
        assert result["success"] is False

    def test_fails_when_path_is_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        (tmp_path / "subdir").mkdir()

        result = json.loads(read_file.invoke({"file_path": "subdir"}))
        assert result["success"] is False

    def test_encoding_fallback_latin1(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        bad_file = tmp_path / "bad.go"
        bad_file.write_bytes(b"\x80\x81\x82 content")

        result = json.loads(read_file.invoke({"file_path": "bad.go"}))
        assert result["success"] is True

    def test_truncates_large_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        big_file = tmp_path / "big.go"
        big_file.write_text("x" * (200 * 1024), encoding="utf-8")

        result = json.loads(read_file.invoke({"file_path": "big.go"}))
        assert result["success"] is True
        assert "截取" in result["message"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_file_reader.py::TestReadFile::test_reads_file_under_agent_work_dir -v`
Expected: FAIL

**Step 3: Write minimal implementation**

In `src/tools/file_reader.py`, add import and change path resolution:

```python
from src.config import settings
```

Change line 26 from:
```python
path = Path(file_path)
```
to:
```python
path = Path(settings.agent_work_dir) / file_path
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/tools/test_file_reader.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/tools/file_reader.py tests/tools/test_file_reader.py
git commit -m "feat(tools): file_reader resolves paths under AGENT_WORK_DIR"
```

---

### Task 5: Update `git_ops.py` to use `agent_work_dir`

**Files:**
- Modify: `src/tools/git_ops.py:1-9,26,45`
- Test: `tests/tools/test_git_ops.py` (new)

**Step 1: Write the failing test**

Create `tests/tools/test_git_ops.py`:

```python
"""git_ops 工具测试。"""

import json
import subprocess

import pytest

from src.config import settings
from src.tools.git_ops import git_diff


class TestGitDiff:
    def test_fails_when_not_a_repo(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        result = json.loads(git_diff.invoke({"repo_path": "."}))
        assert result["success"] is False

    def test_fails_when_no_last_commit(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        (tmp_path / ".git").mkdir()

        result = json.loads(git_diff.invoke({"repo_path": "."}))
        assert result["success"] is False

    def test_fails_when_last_commit_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        (tmp_path / ".git").mkdir()
        (tmp_path / ".last_commit").write_text("")

        result = json.loads(git_diff.invoke({"repo_path": "."}))
        assert result["success"] is False

    def test_successful_diff(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, capture_output=True)
        (tmp_path / "a.go").write_text("package main")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

        first = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True
        ).stdout.strip()

        (tmp_path / "b.go").write_text("package main")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add b"], cwd=tmp_path, capture_output=True)

        (tmp_path / ".last_commit").write_text(first)

        result = json.loads(git_diff.invoke({"repo_path": "."}))
        assert result["success"] is True
        assert "1" in result["message"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_git_ops.py::TestGitDiff::test_fails_when_not_a_repo -v`
Expected: FAIL

**Step 3: Write minimal implementation**

In `src/tools/git_ops.py`, add import and change path resolution:

```python
from src.config import settings
```

Change line 26 from:
```python
repo = Path(repo_path)
```
to:
```python
repo = Path(settings.agent_work_dir) / repo_path
```

Change line 45 (`cwd=repo_path`) to:
```python
cwd=str(repo),
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/tools/test_git_ops.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/tools/git_ops.py tests/tools/test_git_ops.py
git commit -m "feat(tools): git_ops resolves paths under AGENT_WORK_DIR"
```

---

### Task 6: Update `doc_storage.py` to use `settings.docs_output_dir`

**Files:**
- Modify: `src/tools/doc_storage.py:1-11,25-27,116`
- Test: `tests/tools/test_doc_storage.py` (new)

**Step 1: Write the failing test**

Create `tests/tools/test_doc_storage.py`:

```python
"""doc_storage 工具测试。"""

import json

import pytest

from src.config import settings
from src.tools.doc_storage import save_document, read_document, list_documents


class TestSaveDocument:
    def test_saves_to_docs_output_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "docs_output_dir", str(tmp_path / "out"))

        result = json.loads(save_document.invoke({
            "module_name": "user",
            "api_name": "CreateUser",
            "content": "# Create User API",
        }))
        assert result["success"] is True
        assert (tmp_path / "out" / "user" / "CreateUser.md").read_text() == "# Create User API"

    def test_fails_on_empty_api_name(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "docs_output_dir", str(tmp_path / "out"))

        result = json.loads(save_document.invoke({
            "module_name": "user",
            "api_name": "",
            "content": "x",
        }))
        assert result["success"] is False

    def test_fails_on_invalid_module_name(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "docs_output_dir", str(tmp_path / "out"))

        result = json.loads(save_document.invoke({
            "module_name": "BAD!",
            "api_name": "Create",
            "content": "x",
        }))
        assert result["success"] is False

    def test_fails_on_empty_content(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "docs_output_dir", str(tmp_path / "out"))

        result = json.loads(save_document.invoke({
            "module_name": "user",
            "api_name": "Create",
            "content": "",
        }))
        assert result["success"] is False


class TestReadDocument:
    def test_reads_saved_document(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "docs_output_dir", str(tmp_path / "out"))

        doc_dir = tmp_path / "out" / "user"
        doc_dir.mkdir(parents=True)
        (doc_dir / "GetUser.md").write_text("# Get User")

        result = json.loads(read_document.invoke({
            "module_name": "user",
            "api_name": "GetUser",
        }))
        assert result["success"] is True
        assert result["payload"] == "# Get User"

    def test_fails_on_missing_document(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "docs_output_dir", str(tmp_path / "out"))

        result = json.loads(read_document.invoke({
            "module_name": "user",
            "api_name": "NoSuch",
        }))
        assert result["success"] is False


class TestListDocuments:
    def test_lists_module_documents(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "docs_output_dir", str(tmp_path / "out"))

        doc_dir = tmp_path / "out" / "order"
        doc_dir.mkdir(parents=True)
        (doc_dir / "ListOrders.md").write_text("# List Orders")
        (doc_dir / "CreateOrder.md").write_text("# Create Order")

        result = json.loads(list_documents.invoke({"module_name": "order"}))
        assert result["success"] is True
        assert "2" in result["message"]

    def test_lists_all_documents(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "docs_output_dir", str(tmp_path / "out"))

        for mod in ["user", "order"]:
            d = tmp_path / "out" / mod
            d.mkdir(parents=True)
            (d / "Api.md").write_text("# Api")

        result = json.loads(list_documents.invoke({"module_name": None}))
        assert result["success"] is True
        assert "2" in result["message"]

    def test_empty_when_no_docs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "docs_output_dir", str(tmp_path / "out"))

        result = json.loads(list_documents.invoke({"module_name": None}))
        assert result["success"] is True
        assert "没有" in result["message"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_doc_storage.py::TestSaveDocument::test_saves_to_docs_output_dir -v`
Expected: FAIL (still using hardcoded `DOCS_BASE_DIR = "docs"`)

**Step 3: Write minimal implementation**

In `src/tools/doc_storage.py`:

1. Add import:
```python
from src.config import settings
```

2. Remove the module-level constant:
```python
# DELETE this line:
DOCS_BASE_DIR = "docs"
```

3. Change `_get_doc_path` (line 25-27):
```python
def _get_doc_path(module_name: str, api_name: str) -> Path:
    """构建文档文件路径：{docs_output_dir}/{module_name}/{api_name}.md"""
    return Path(settings.docs_output_dir) / module_name / f"{api_name}.md"
```

4. Change `list_documents` (line 116):
```python
base = Path(settings.docs_output_dir)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/tools/test_doc_storage.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/tools/doc_storage.py tests/tools/test_doc_storage.py
git commit -m "feat(tools): doc_storage uses settings.docs_output_dir instead of hardcoded DOCS_BASE_DIR"
```

---

### Task 7: Run full test suite and final commit

**Step 1: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

**Step 2: Verify .env.example is complete**

Run: `cat .env.example`
Expected: Contains `AGENT_WORK_DIR=.`

**Step 3: Final verification commit (if any fixups needed)**

If all green, no commit needed. If fixups were required, commit them.
