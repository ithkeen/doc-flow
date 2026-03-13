# Per-Node LLM Configuration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow each graph node to use a different LLM model/provider via per-node static configuration with fallback to the global `settings.llm`.

**Architecture:** Add a `NodeLLMSettings` class (all-optional fields, `_env_prefix` passed at construction time) to the config layer. Add a `_get_node_llm()` factory function in `nodes.py` that resolves per-node config with explicit `is not None` fallback to global. Replace all 4 inline `ChatOpenAI(...)` constructions with factory calls.

**Tech Stack:** pydantic-settings v2 (`_env_prefix` runtime parameter), langchain-openai `ChatOpenAI`

**Spec:** `docs/superpowers/specs/2026-03-13-per-node-llm-config-design.md`

---

## Chunk 1: Configuration Layer

### Task 1: Add `NodeLLMSettings` class and wire into `Settings`

**Files:**
- Modify: `src/config/settings.py:1-94`
- Test: `tests/config/test_settings.py`

- [ ] **Step 1: Write failing tests for `NodeLLMSettings` defaults**

Add to `tests/config/test_settings.py`:

```python
from src.config.settings import LLMSettings, LangSmithSettings, NodeLLMSettings, Settings


class TestNodeLLMSettings:
    """节点级 LLM 配置测试。"""

    def test_all_fields_default_to_none(self, monkeypatch):
        """未设置环境变量时，所有字段应为 None。"""
        monkeypatch.delenv("INTENT_LLM_BASE_URL", raising=False)
        monkeypatch.delenv("INTENT_LLM_API_KEY", raising=False)
        monkeypatch.delenv("INTENT_LLM_MODEL", raising=False)

        s = NodeLLMSettings(_env_file=None, _env_prefix="INTENT_LLM_")
        assert s.base_url is None
        assert s.api_key is None
        assert s.model is None

    def test_loads_from_env_with_prefix(self, monkeypatch):
        """设置环境变量时，应正确加载。"""
        monkeypatch.setenv("INTENT_LLM_MODEL", "gpt-4o-mini")
        monkeypatch.setenv("INTENT_LLM_BASE_URL", "https://custom.api/v1")
        monkeypatch.setenv("INTENT_LLM_API_KEY", "intent-key")

        s = NodeLLMSettings(_env_file=None, _env_prefix="INTENT_LLM_")
        assert s.model == "gpt-4o-mini"
        assert s.base_url == "https://custom.api/v1"
        assert s.api_key == "intent-key"

    def test_different_prefixes_load_independently(self, monkeypatch):
        """不同 env_prefix 的实例应独立加载各自的环境变量。"""
        monkeypatch.setenv("INTENT_LLM_MODEL", "gpt-4o-mini")
        monkeypatch.setenv("DOC_GEN_LLM_MODEL", "gpt-4")
        monkeypatch.delenv("CHAT_LLM_MODEL", raising=False)

        intent = NodeLLMSettings(_env_file=None, _env_prefix="INTENT_LLM_")
        doc_gen = NodeLLMSettings(_env_file=None, _env_prefix="DOC_GEN_LLM_")
        chat = NodeLLMSettings(_env_file=None, _env_prefix="CHAT_LLM_")

        assert intent.model == "gpt-4o-mini"
        assert doc_gen.model == "gpt-4"
        assert chat.model is None

    def test_ignores_extra_env_vars(self, monkeypatch):
        """带有匹配前缀但不在字段中的环境变量应被忽略（extra=ignore）。"""
        monkeypatch.setenv("INTENT_LLM_TEMPERATURE", "0.5")

        s = NodeLLMSettings(_env_file=None, _env_prefix="INTENT_LLM_")
        assert not hasattr(s, "temperature")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/config/test_settings.py::TestNodeLLMSettings -v`
Expected: FAIL — `ImportError: cannot import name 'NodeLLMSettings'`

- [ ] **Step 3: Implement `NodeLLMSettings` class**

Add to `src/config/settings.py`, after the `LogSettings` class (line 60) and before the `Settings` class (line 63):

```python
class NodeLLMSettings(BaseSettings):
    """节点级 LLM 配置。字段为 None 时 fallback 到全局 LLMSettings。"""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        extra="ignore",
    )

    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/config/test_settings.py::TestNodeLLMSettings -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/config/settings.py tests/config/test_settings.py
git commit -m "feat: add NodeLLMSettings class for per-node LLM config"
```

---

### Task 2: Wire `NodeLLMSettings` into `Settings`

**Files:**
- Modify: `src/config/settings.py:63-94`
- Test: `tests/config/test_settings.py`

- [ ] **Step 1: Write failing tests for Settings with node LLM attributes**

Add to `tests/config/test_settings.py`, in the existing `TestSettings` class:

```python
    def test_node_llm_defaults_to_none_fields(self, monkeypatch):
        """未设置节点级环境变量时，Settings 应包含全 None 的 NodeLLMSettings。"""
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.delenv("INTENT_LLM_MODEL", raising=False)

        s = Settings(_env_file=None)
        assert s.intent_llm.model is None
        assert s.intent_llm.base_url is None
        assert s.intent_llm.api_key is None
        assert s.doc_gen_llm.model is None
        assert s.doc_qa_llm.model is None
        assert s.chat_llm.model is None

    def test_node_llm_loads_from_env(self, monkeypatch):
        """设置节点级环境变量时，Settings 应正确加载。"""
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setenv("INTENT_LLM_MODEL", "gpt-4o-mini")
        monkeypatch.setenv("DOC_GEN_LLM_MODEL", "gpt-4")

        s = Settings(_env_file=None)
        assert s.intent_llm.model == "gpt-4o-mini"
        assert s.doc_gen_llm.model == "gpt-4"
        assert s.doc_qa_llm.model is None
        assert s.chat_llm.model is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/config/test_settings.py::TestSettings::test_node_llm_defaults_to_none_fields tests/config/test_settings.py::TestSettings::test_node_llm_loads_from_env -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'intent_llm'`

- [ ] **Step 3: Add node LLM attributes to Settings**

In `src/config/settings.py`, modify the `Settings` class:

1. Add 4 new fields after `log` (line 79):

```python
    intent_llm: NodeLLMSettings = Field(default_factory=NodeLLMSettings)
    doc_gen_llm: NodeLLMSettings = Field(default_factory=NodeLLMSettings)
    doc_qa_llm: NodeLLMSettings = Field(default_factory=NodeLLMSettings)
    chat_llm: NodeLLMSettings = Field(default_factory=NodeLLMSettings)
```

2. Add construction in `__init__`, after the existing `if "log" not in kwargs:` block (after line 91):

```python
        if "intent_llm" not in kwargs:
            kwargs["intent_llm"] = NodeLLMSettings(_env_file=env_file, _env_prefix="INTENT_LLM_")
        if "doc_gen_llm" not in kwargs:
            kwargs["doc_gen_llm"] = NodeLLMSettings(_env_file=env_file, _env_prefix="DOC_GEN_LLM_")
        if "doc_qa_llm" not in kwargs:
            kwargs["doc_qa_llm"] = NodeLLMSettings(_env_file=env_file, _env_prefix="DOC_QA_LLM_")
        if "chat_llm" not in kwargs:
            kwargs["chat_llm"] = NodeLLMSettings(_env_file=env_file, _env_prefix="CHAT_LLM_")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/config/test_settings.py -v`
Expected: ALL PASSED (existing + new tests)

- [ ] **Step 5: Commit**

```bash
git add src/config/settings.py tests/config/test_settings.py
git commit -m "feat: wire NodeLLMSettings into Settings for 4 graph nodes"
```

---

## Chunk 2: Factory Function, Node Refactoring, and `.env.example`

### Task 3: Add `_get_node_llm` factory function

**Files:**
- Modify: `src/graph/nodes.py:1-24`
- Test: `tests/graph/test_nodes.py`

- [ ] **Step 1: Write failing tests for `_get_node_llm`**

Add to `tests/graph/test_nodes.py`:

```python
class TestGetNodeLlm:
    """_get_node_llm 工厂函数测试。"""

    @patch("src.graph.nodes.ChatOpenAI")
    @patch("src.graph.nodes.settings")
    def test_fallback_to_global_when_node_config_all_none(self, mock_settings, mock_chat_cls):
        """节点配置全部为 None 时，应使用全局 settings.llm 的值。"""
        from src.graph.nodes import _get_node_llm

        mock_settings.llm.base_url = "https://global.api/v1"
        mock_settings.llm.api_key = "global-key"
        mock_settings.llm.model = "gpt-4"
        mock_settings.intent_llm.base_url = None
        mock_settings.intent_llm.api_key = None
        mock_settings.intent_llm.model = None

        _get_node_llm("intent")

        mock_chat_cls.assert_called_once_with(
            base_url="https://global.api/v1",
            api_key="global-key",
            model="gpt-4",
        )

    @patch("src.graph.nodes.ChatOpenAI")
    @patch("src.graph.nodes.settings")
    def test_partial_override_uses_node_model_with_global_rest(self, mock_settings, mock_chat_cls):
        """仅设置节点 model 时，base_url 和 api_key 应 fallback 到全局。"""
        from src.graph.nodes import _get_node_llm

        mock_settings.llm.base_url = "https://global.api/v1"
        mock_settings.llm.api_key = "global-key"
        mock_settings.llm.model = "gpt-4"
        mock_settings.intent_llm.base_url = None
        mock_settings.intent_llm.api_key = None
        mock_settings.intent_llm.model = "gpt-4o-mini"

        _get_node_llm("intent")

        mock_chat_cls.assert_called_once_with(
            base_url="https://global.api/v1",
            api_key="global-key",
            model="gpt-4o-mini",
        )

    @patch("src.graph.nodes.ChatOpenAI")
    @patch("src.graph.nodes.settings")
    def test_full_override_uses_all_node_values(self, mock_settings, mock_chat_cls):
        """节点配置全部设置时，应完全使用节点级的值。"""
        from src.graph.nodes import _get_node_llm

        mock_settings.llm.base_url = "https://global.api/v1"
        mock_settings.llm.api_key = "global-key"
        mock_settings.llm.model = "gpt-4"
        mock_settings.doc_gen_llm.base_url = "https://node.api/v1"
        mock_settings.doc_gen_llm.api_key = "node-key"
        mock_settings.doc_gen_llm.model = "gpt-4-turbo"

        _get_node_llm("doc_gen")

        mock_chat_cls.assert_called_once_with(
            base_url="https://node.api/v1",
            api_key="node-key",
            model="gpt-4-turbo",
        )

    @patch("src.graph.nodes.ChatOpenAI")
    @patch("src.graph.nodes.settings")
    def test_unknown_node_name_falls_back_to_global(self, mock_settings, mock_chat_cls):
        """未知节点名应完全 fallback 到全局配置。"""
        from src.graph.nodes import _get_node_llm

        mock_settings.llm.base_url = "https://global.api/v1"
        mock_settings.llm.api_key = "global-key"
        mock_settings.llm.model = "gpt-4"

        _get_node_llm("nonexistent")

        mock_chat_cls.assert_called_once_with(
            base_url="https://global.api/v1",
            api_key="global-key",
            model="gpt-4",
        )

    @pytest.mark.parametrize("node_name,attr_name", [
        ("intent", "intent_llm"),
        ("doc_gen", "doc_gen_llm"),
        ("doc_qa", "doc_qa_llm"),
        ("chat", "chat_llm"),
    ])
    @patch("src.graph.nodes.ChatOpenAI")
    @patch("src.graph.nodes.settings")
    def test_all_node_names_resolve_correct_attr(self, mock_settings, mock_chat_cls, node_name, attr_name):
        """验证所有 4 个节点名都映射到正确的 settings 属性。"""
        from src.graph.nodes import _get_node_llm

        mock_settings.llm.base_url = "https://global.api/v1"
        mock_settings.llm.api_key = "global-key"
        mock_settings.llm.model = "gpt-4"
        node_cfg = getattr(mock_settings, attr_name)
        node_cfg.base_url = None
        node_cfg.api_key = None
        node_cfg.model = "node-specific-model"

        _get_node_llm(node_name)

        mock_chat_cls.assert_called_once_with(
            base_url="https://global.api/v1",
            api_key="global-key",
            model="node-specific-model",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/graph/test_nodes.py::TestGetNodeLlm -v`
Expected: FAIL — `ImportError: cannot import name '_get_node_llm'`

- [ ] **Step 3: Implement `_get_node_llm` factory function**

Add to `src/graph/nodes.py`, after the `logger = get_logger(__name__)` line (line 23) and before the `State` class (line 26):

```python
_NODE_LLM_ATTR = {
    "intent": "intent_llm",
    "doc_gen": "doc_gen_llm",
    "doc_qa": "doc_qa_llm",
    "chat": "chat_llm",
}


def _get_node_llm(node_name: str) -> ChatOpenAI:
    """根据节点名称返回对应配置的 ChatOpenAI 实例，未配置字段 fallback 到全局。"""
    attr = _NODE_LLM_ATTR.get(node_name)
    node_cfg = getattr(settings, attr, None) if attr else None

    base_url = node_cfg.base_url if (node_cfg and node_cfg.base_url is not None) else settings.llm.base_url
    api_key = node_cfg.api_key if (node_cfg and node_cfg.api_key is not None) else settings.llm.api_key
    model = node_cfg.model if (node_cfg and node_cfg.model is not None) else settings.llm.model

    return ChatOpenAI(base_url=base_url, api_key=api_key, model=model)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/graph/test_nodes.py::TestGetNodeLlm -v`
Expected: 8 PASSED (4 individual tests + 4 parametrized)

- [ ] **Step 5: Commit**

```bash
git add src/graph/nodes.py tests/graph/test_nodes.py
git commit -m "feat: add _get_node_llm factory with per-node fallback logic"
```

---

### Task 4: Replace inline `ChatOpenAI(...)` in all 4 nodes

**Files:**
- Modify: `src/graph/nodes.py`

> **Note:** Line numbers below refer to the original file before Task 3's insertion. Use the `Replace:` code blocks for pattern matching — they are unambiguous regardless of line shifts.

- [ ] **Step 1: Replace in `intent_recognize`** (lines 50-54)

Replace:
```python
    llm = ChatOpenAI(
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
        model=settings.llm.model,
    )
```
With:
```python
    llm = _get_node_llm("intent")
```

- [ ] **Step 2: Replace in `doc_qa`** (lines 106-110)

Replace:
```python
    llm = ChatOpenAI(
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
        model=settings.llm.model,
    )
```
With:
```python
    llm = _get_node_llm("doc_qa")
```

- [ ] **Step 3: Replace in `doc_gen`** (lines 131-135)

Replace:
```python
    llm = ChatOpenAI(
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
        model=settings.llm.model,
    )
```
With:
```python
    llm = _get_node_llm("doc_gen")
```

- [ ] **Step 4: Replace in `chat`** (lines 156-160)

Replace:
```python
    llm = ChatOpenAI(
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
        model=settings.llm.model,
    )
```
With:
```python
    llm = _get_node_llm("chat")
```

- [ ] **Step 5: Run all tests to verify nothing is broken**

Run: `uv run pytest tests/ -v`
Expected: ALL PASSED — existing node tests still mock `ChatOpenAI` at module level, which captures calls from `_get_node_llm`

- [ ] **Step 6: Commit**

```bash
git add src/graph/nodes.py
git commit -m "refactor: replace inline ChatOpenAI construction with _get_node_llm calls"
```

---

### Task 5: Update `.env.example`

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Add per-node config examples**

Append to `.env.example`, after the `LOG_BACKUP_COUNT=7` line:

```bash

# 节点级 LLM 配置（可选，未设置时 fallback 到上方 LLM_* 配置）
# INTENT_LLM_MODEL=gpt-4o-mini
# DOC_GEN_LLM_MODEL=gpt-4
# DOC_QA_LLM_MODEL=gpt-4o-mini
# CHAT_LLM_MODEL=gpt-4o-mini
# 也支持为单个节点设置不同的 base_url 和 api_key:
# INTENT_LLM_BASE_URL=https://other-provider.api/v1
# INTENT_LLM_API_KEY=other-api-key
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add per-node LLM config examples to .env.example"
```
