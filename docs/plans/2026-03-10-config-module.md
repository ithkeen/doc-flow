# Config Module Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a centralized, type-safe config module at `src/config/` using Pydantic Settings, with fail-fast validation for required fields like `LLM_API_KEY`.

**Architecture:** Each config group (LLM, LangSmith) is a separate `BaseSettings` subclass with its own `env_prefix`, composed into a root `Settings` class via `default_factory`. The `.env` file path is resolved relative to project root. A singleton `settings` instance is exported from `src/config/__init__.py`.

**Tech Stack:** Python 3.11, pydantic-settings, pytest

---

### Task 1: Add dependencies

**Files:**
- Modify: `pyproject.toml:7-9`

**Step 1: Add pydantic-settings dependency**

Edit `pyproject.toml` dependencies array:

```toml
dependencies = [
    "langchain>=1.2.10",
    "pydantic-settings>=2.7.0",
]
```

**Step 2: Add pytest as dev dependency**

Run: `uv add --dev pytest`
Expected: `pyproject.toml` updated with `[dependency-groups]` dev section

**Step 3: Install dependencies**

Run: `uv sync`
Expected: All dependencies installed, `uv.lock` updated

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add pydantic-settings and pytest dependencies"
```

---

### Task 2: Create `src/config/settings.py`

**Files:**
- Create: `src/config/settings.py`

**Step 1: Write the failing test**

Create `tests/config/__init__.py` (empty) and `tests/__init__.py` (empty) and `tests/config/test_settings.py`:

```python
"""配置模块单元测试。"""

import pytest
from pydantic import ValidationError


class TestLLMSettings:
    """LLM 配置测试。"""

    def test_loads_from_env(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setenv("LLM_MODEL", "gpt-3.5-turbo")
        monkeypatch.setenv("LLM_BASE_URL", "https://custom.api/v1")

        from src.config.settings import LLMSettings

        s = LLMSettings()
        assert s.api_key == "test-key"
        assert s.model == "gpt-3.5-turbo"
        assert s.base_url == "https://custom.api/v1"

    def test_defaults(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")

        from src.config.settings import LLMSettings

        s = LLMSettings()
        assert s.base_url == "https://api.openai.com/v1"
        assert s.model == "gpt-4"

    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)

        from src.config.settings import LLMSettings

        with pytest.raises(ValidationError):
            LLMSettings(_env_file=None)


class TestLangSmithSettings:
    """LangSmith 配置测试。"""

    def test_all_optional(self):
        from src.config.settings import LangSmithSettings

        s = LangSmithSettings(_env_file=None)
        assert s.tracing is True
        assert s.api_key is None
        assert s.project == "doc-flow"
        assert s.endpoint == "https://api.smith.langchain.com"

    def test_loads_from_env(self, monkeypatch):
        monkeypatch.setenv("LANGSMITH_TRACING", "false")
        monkeypatch.setenv("LANGSMITH_API_KEY", "ls-key")

        from src.config.settings import LangSmithSettings

        s = LangSmithSettings()
        assert s.tracing is False
        assert s.api_key == "ls-key"


class TestSettings:
    """Root Settings 测试。"""

    def test_loads_all_groups(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")

        from src.config.settings import Settings

        s = Settings(_env_file=None)
        assert s.llm.api_key == "test-key"
        assert s.docs_output_dir == "./docs"
        assert s.langsmith.tracing is True

    def test_docs_output_dir_from_env(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setenv("DOCS_OUTPUT_DIR", "/custom/docs")

        from src.config.settings import Settings

        s = Settings(_env_file=None)
        assert s.docs_output_dir == "/custom/docs"

    def test_fail_fast_without_llm_key(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)

        from src.config.settings import Settings

        with pytest.raises(ValidationError):
            Settings(_env_file=None)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/config/test_settings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.config'`

**Step 3: Write implementation**

Create `src/config/settings.py`:

```python
"""配置管理模块。

使用 Pydantic Settings 从环境变量和 .env 文件加载配置。
必填配置缺失时启动即报错（fail-fast）。
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env 文件路径：项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class LLMSettings(BaseSettings):
    """LLM API 配置。"""

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=_ENV_FILE,
        extra="ignore",
    )

    base_url: str = "https://api.openai.com/v1"
    api_key: str
    model: str = "gpt-4"


class LangSmithSettings(BaseSettings):
    """LangSmith 配置（可选，用于 tracing 和监控）。"""

    model_config = SettingsConfigDict(
        env_prefix="LANGSMITH_",
        env_file=_ENV_FILE,
        extra="ignore",
    )

    tracing: bool = True
    api_key: str | None = None
    project: str = "doc-flow"
    endpoint: str = "https://api.smith.langchain.com"


class Settings(BaseSettings):
    """应用根配置。

    组合所有子配置组，提供统一的配置访问入口。
    LLM_API_KEY 为必填项，缺失时构造实例会抛出 ValidationError。
    """

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        extra="ignore",
    )

    docs_output_dir: str = "./docs"
    llm: LLMSettings = Field(default_factory=LLMSettings)
    langsmith: LangSmithSettings = Field(default_factory=LangSmithSettings)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/config/test_settings.py -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add src/config/settings.py tests/
git commit -m "feat: add config settings module with LLM and LangSmith groups"
```

---

### Task 3: Create `src/config/__init__.py` (singleton export)

**Files:**
- Create: `src/config/__init__.py`

**Step 1: Write the failing test**

Add to `tests/config/test_settings.py`:

```python
class TestSettingsSingleton:
    """Singleton 导入测试。"""

    def test_import_settings(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "singleton-key")

        from src.config import settings

        assert settings.llm.api_key == "singleton-key"

    def test_same_instance(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "singleton-key")

        from src.config import settings as s1
        from src.config import settings as s2

        assert s1 is s2
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/config/test_settings.py::TestSettingsSingleton -v`
Expected: FAIL — `ImportError: cannot import name 'settings'`

**Step 3: Write implementation**

Create `src/config/__init__.py`:

```python
"""配置模块。

提供全局 settings 单例，应用启动时加载一次，后续 import 即用。

Usage::

    from src.config import settings

    settings.llm.api_key
    settings.llm.model
    settings.docs_output_dir
    settings.langsmith.tracing
"""

from src.config.settings import Settings

settings = Settings()

__all__ = ["settings", "Settings"]
```

**Step 4: Run all tests to verify they pass**

Run: `uv run pytest tests/config/test_settings.py -v`
Expected: All 9 tests PASS

**Step 5: Commit**

```bash
git add src/config/__init__.py
git commit -m "feat: add config singleton export"
```

---

### Task 4: Verify end-to-end with .env file

**Step 1: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

**Step 2: Verify .env loading manually**

Run: `uv run python -c "from src.config import settings; print(f'model={settings.llm.model}, output={settings.docs_output_dir}')"`
Expected: Prints actual values from `.env` file

**Step 3: Final commit (if any changes)**

```bash
git add -A
git commit -m "feat: config module complete"
```