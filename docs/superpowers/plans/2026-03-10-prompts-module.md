# Prompts Module Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a prompt template loader that reads `.md` files from `system/` and `user/` directories and returns LangChain `ChatPromptTemplate` objects.

**Architecture:** A single `load_prompt(name)` factory function reads template files from `src/prompts/system/{name}.md` and `src/prompts/user/{name}.md`, assembles them into a `ChatPromptTemplate.from_messages()`. Both templates are optional, but at least one must exist.

**Tech Stack:** Python 3.11, langchain_core (ChatPromptTemplate), pytest

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/prompts/__init__.py` | 导出 `load_prompt` |
| Create | `src/prompts/loader.py` | `load_prompt()` 工厂函数 |
| Create | `src/prompts/system/intent.md` | 意图识别系统提示词模板 |
| Create | `src/prompts/system/doc_gen.md` | 文档生成系统提示词模板 |
| Create | `src/prompts/user/intent.md` | 意图识别用户提示词模板 |
| Create | `src/prompts/user/doc_gen.md` | 文档生成用户提示词模板（占位，ReAct 场景可选） |
| Create | `tests/prompts/__init__.py` | 测试包 init |
| Create | `tests/prompts/test_loader.py` | `load_prompt` 单元测试 |

---

## Chunk 1: loader.py and tests

### Task 1: load_prompt — 加载 system + user 双模板

**Files:**
- Create: `tests/prompts/__init__.py`
- Create: `tests/prompts/test_loader.py`
- Create: `src/prompts/__init__.py` (空文件，使包可导入)
- Create: `src/prompts/loader.py`

- [ ] **Step 1: Write the failing test**

Create `tests/prompts/__init__.py` (empty file) and `tests/prompts/test_loader.py`:

```python
"""load_prompt 单元测试。"""

from pathlib import Path

import pytest
from langchain_core.prompts import ChatPromptTemplate

from src.prompts.loader import load_prompt


@pytest.fixture()
def prompts_dir(tmp_path):
    """创建临时提示词目录结构。"""
    system_dir = tmp_path / "system"
    user_dir = tmp_path / "user"
    system_dir.mkdir()
    user_dir.mkdir()
    return tmp_path


class TestLoadPromptBothTemplates:
    """system + user 模板同时存在。"""

    def test_returns_chat_prompt_template(self, prompts_dir):
        (prompts_dir / "system" / "test_node.md").write_text("你是助手。", encoding="utf-8")
        (prompts_dir / "user" / "test_node.md").write_text("用户输入：{input}", encoding="utf-8")

        result = load_prompt("test_node", prompts_dir=prompts_dir)

        assert isinstance(result, ChatPromptTemplate)

    def test_contains_system_and_human_messages(self, prompts_dir):
        (prompts_dir / "system" / "test_node.md").write_text("你是助手。", encoding="utf-8")
        (prompts_dir / "user" / "test_node.md").write_text("用户输入：{input}", encoding="utf-8")

        result = load_prompt("test_node", prompts_dir=prompts_dir)
        messages = result.format_messages(input="你好")

        assert len(messages) == 2
        assert messages[0].type == "system"
        assert messages[0].content == "你是助手。"
        assert messages[1].type == "human"
        assert messages[1].content == "用户输入：你好"

    def test_strips_whitespace_from_template(self, prompts_dir):
        (prompts_dir / "system" / "test_node.md").write_text("\n  你是助手。\n\n", encoding="utf-8")
        (prompts_dir / "user" / "test_node.md").write_text("\n用户输入：{input}\n", encoding="utf-8")

        result = load_prompt("test_node", prompts_dir=prompts_dir)
        messages = result.format_messages(input="你好")

        assert messages[0].content == "你是助手。"
        assert messages[1].content == "用户输入：你好"
```

- [ ] **Step 2: Create empty `src/prompts/__init__.py` to make package importable**

Create `src/prompts/__init__.py` as an empty file.

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/ithkeen/CodeSpace/agent-project/doc-flow && python -m pytest tests/prompts/test_loader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.prompts.loader'`

- [ ] **Step 4: Write minimal implementation**

Create `src/prompts/loader.py`:

```python
"""提示词模板加载器。

从 system/ 和 user/ 子目录读取 .md 模板文件，
组装为 LangChain ChatPromptTemplate。
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate

_DEFAULT_PROMPTS_DIR = Path(__file__).resolve().parent


def load_prompt(
    name: str,
    *,
    prompts_dir: Path = _DEFAULT_PROMPTS_DIR,
) -> ChatPromptTemplate:
    """按节点名称加载提示词，返回 ChatPromptTemplate。

    从 prompts_dir/system/{name}.md 和 prompts_dir/user/{name}.md
    读取模板内容。两者均为可选，但至少需要存在一个。

    Args:
        name: 提示词名称，对应模板文件名（不含扩展名）。
        prompts_dir: 提示词根目录，默认为本模块所在目录。

    Returns:
        组装好的 ChatPromptTemplate。

    Raises:
        FileNotFoundError: system 和 user 模板均不存在时抛出。
    """
    system_path = prompts_dir / "system" / f"{name}.md"
    user_path = prompts_dir / "user" / f"{name}.md"

    messages: list[tuple[str, str]] = []

    if system_path.exists():
        messages.append(("system", system_path.read_text(encoding="utf-8").strip()))
    if user_path.exists():
        messages.append(("human", user_path.read_text(encoding="utf-8").strip()))

    if not messages:
        raise FileNotFoundError(
            f"提示词模板不存在: 至少需要 system/{name}.md 或 user/{name}.md 其中之一"
        )

    return ChatPromptTemplate.from_messages(messages)
```

注意：添加了 `prompts_dir` 关键字参数，默认指向模块自身目录，测试时可注入 `tmp_path`。

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/ithkeen/CodeSpace/agent-project/doc-flow && python -m pytest tests/prompts/test_loader.py::TestLoadPromptBothTemplates -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add tests/prompts/__init__.py tests/prompts/test_loader.py src/prompts/__init__.py src/prompts/loader.py
git commit -m "feat(prompts): add load_prompt with system+user template loading"
```

---

### Task 2: load_prompt — 可选模板场景

**Files:**
- Modify: `tests/prompts/test_loader.py`

- [ ] **Step 1: Write tests for optional template scenarios**

Append to `tests/prompts/test_loader.py`:

```python
class TestLoadPromptSystemOnly:
    """仅 system 模板存在。"""

    def test_returns_system_message_only(self, prompts_dir):
        (prompts_dir / "system" / "react_node.md").write_text("你是 ReAct agent。", encoding="utf-8")

        result = load_prompt("react_node", prompts_dir=prompts_dir)
        messages = result.format_messages()

        assert len(messages) == 1
        assert messages[0].type == "system"
        assert messages[0].content == "你是 ReAct agent。"


class TestLoadPromptUserOnly:
    """仅 user 模板存在。"""

    def test_returns_human_message_only(self, prompts_dir):
        (prompts_dir / "user" / "simple_node.md").write_text("请处理：{task}", encoding="utf-8")

        result = load_prompt("simple_node", prompts_dir=prompts_dir)
        messages = result.format_messages(task="分析代码")

        assert len(messages) == 1
        assert messages[0].type == "human"
        assert messages[0].content == "请处理：分析代码"


class TestLoadPromptNotFound:
    """system 和 user 模板均不存在。"""

    def test_raises_file_not_found_error(self, prompts_dir):
        with pytest.raises(FileNotFoundError, match="提示词模板不存在"):
            load_prompt("nonexistent", prompts_dir=prompts_dir)
```

- [ ] **Step 2: Run tests to confirm existing implementation already covers these scenarios**

Run: `cd /Users/ithkeen/CodeSpace/agent-project/doc-flow && python -m pytest tests/prompts/test_loader.py -v`
Expected: 6 passed（3 个已有 + 3 个新增，实现在 Task 1 中已覆盖这些场景）

- [ ] **Step 3: Commit**

```bash
git add tests/prompts/test_loader.py
git commit -m "test(prompts): add tests for system-only, user-only, and not-found scenarios"
```

---

### Task 3: 创建初始模板文件

**Files:**
- Create: `src/prompts/system/intent.md`
- Create: `src/prompts/system/doc_gen.md`
- Create: `src/prompts/user/intent.md`
- Create: `src/prompts/user/doc_gen.md`

- [ ] **Step 1: Write integration test for bundled templates**

Append to `tests/prompts/test_loader.py`:

```python
class TestLoadBundledTemplates:
    """验证项目自带的模板文件可正常加载。"""

    def test_load_intent_prompt(self):
        result = load_prompt("intent")

        assert isinstance(result, ChatPromptTemplate)
        messages = result.format_messages(intent_list="1. 生成文档", user_input="帮我生成文档")
        assert len(messages) == 2
        assert messages[0].type == "system"
        assert messages[1].type == "human"

    def test_load_doc_gen_prompt(self):
        result = load_prompt("doc_gen")

        assert isinstance(result, ChatPromptTemplate)
```

- [ ] **Step 2: Run test to verify it fails (templates not yet created)**

Run: `cd /Users/ithkeen/CodeSpace/agent-project/doc-flow && python -m pytest tests/prompts/test_loader.py::TestLoadBundledTemplates -v`
Expected: FAIL with `FileNotFoundError: 提示词模板不存在`

- [ ] **Step 3: Create system/intent.md**

```markdown
你是一个智能代码文档生成助手的意图识别模块。

你的任务是分析用户的输入，判断其意图属于以下哪一类：
{intent_list}

请以 JSON 格式输出你的判断结果，包含以下字段：
- intent: 识别出的意图类别
- confidence: 置信度（0-1）
- params: 从用户输入中提取的关键参数
```

- [ ] **Step 4: Create user/intent.md**

```markdown
用户输入：{user_input}
```

- [ ] **Step 5: Create system/doc_gen.md**

```markdown
你是一个专业的代码接口文档生成助手。

你的任务是根据用户的需求，通过调用工具分析代码并生成高质量的接口文档。

你可以使用以下工具：
- scan_directory: 扫描目录下的源代码文件
- read_file: 读取文件内容
- doc_storage: 存储生成的文档

工作流程：
1. 使用 scan_directory 扫描用户指定的目录，获取源代码文件列表
2. 使用 read_file 逐个读取代码文件
3. 分析代码中的接口定义（函数签名、参数、返回值、注释等）
4. 生成结构化的接口文档
5. 使用 doc_storage 存储文档

文档输出格式要求：
- 使用 Markdown 格式
- 包含接口名称、请求方法、路径、参数说明、返回值说明
- 如有示例代码，一并包含
```

- [ ] **Step 6: Create user/doc_gen.md**

```markdown
请为以下目录生成接口文档：{directory_path}
```

- [ ] **Step 7: Run tests to verify bundled templates load correctly**

Run: `cd /Users/ithkeen/CodeSpace/agent-project/doc-flow && python -m pytest tests/prompts/test_loader.py::TestLoadBundledTemplates -v`
Expected: 2 passed

- [ ] **Step 8: Commit**

```bash
git add src/prompts/system/intent.md src/prompts/system/doc_gen.md src/prompts/user/intent.md src/prompts/user/doc_gen.md tests/prompts/test_loader.py
git commit -m "feat(prompts): add initial intent and doc_gen template files"
```

---

### Task 4: 模块导出

**Files:**
- Modify: `src/prompts/__init__.py`

- [ ] **Step 1: Write export test**

Append to `tests/prompts/test_loader.py`:

```python
class TestModuleExport:
    """验证模块导出。"""

    def test_load_prompt_importable_from_package(self):
        from src.prompts import load_prompt as fn

        assert callable(fn)
```

- [ ] **Step 2: Run test to verify it fails (current __init__.py is empty)**

Run: `cd /Users/ithkeen/CodeSpace/agent-project/doc-flow && python -m pytest tests/prompts/test_loader.py::TestModuleExport -v`
Expected: FAIL with `ImportError: cannot import name 'load_prompt' from 'src.prompts'`

- [ ] **Step 3: Update __init__.py with exports**

Replace `src/prompts/__init__.py` content:

```python
"""提示词模块。

从模板文件加载提示词，返回 LangChain ChatPromptTemplate。

Usage::

    from src.prompts import load_prompt

    prompt = load_prompt("intent")
    chain = prompt | llm
    result = chain.invoke({"user_input": "...", "intent_list": "..."})
"""

from src.prompts.loader import load_prompt

__all__ = ["load_prompt"]
```

- [ ] **Step 4: Run all tests to verify everything passes**

Run: `cd /Users/ithkeen/CodeSpace/agent-project/doc-flow && python -m pytest tests/prompts/ -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/prompts/__init__.py tests/prompts/test_loader.py
git commit -m "feat(prompts): add module init with load_prompt export"
```
