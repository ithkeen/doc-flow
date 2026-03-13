# Per-Node LLM Configuration Design

## Problem

All 4 graph nodes (`intent_recognize`, `doc_gen`, `doc_qa`, `chat`) use the same `ChatOpenAI` instance configured by `settings.llm`. Intent recognition is a simple JSON classification task that does not need a powerful (expensive, slow) model. There is no way to assign different models to different nodes.

## Solution

Add per-node LLM configuration via pydantic-settings `env_prefix`, with fallback to the global `settings.llm` for any unconfigured field. A private factory function in `nodes.py` encapsulates the resolution logic.

## Design

### 1. Configuration Layer (`src/config/settings.py`)

New `NodeLLMSettings` class with all-optional fields:

```python
class NodeLLMSettings(BaseSettings):
    """Node-level LLM config. None fields fall back to global LLMSettings."""
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
```

Four instances in `Settings`, each with a distinct `env_prefix`:

| Attribute        | `env_prefix`    | Example env var              |
|------------------|-----------------|------------------------------|
| `intent_llm`     | `INTENT_LLM_`   | `INTENT_LLM_MODEL=gpt-4o-mini` |
| `doc_gen_llm`    | `DOC_GEN_LLM_`  | `DOC_GEN_LLM_MODEL=gpt-4`   |
| `doc_qa_llm`     | `DOC_QA_LLM_`   | `DOC_QA_LLM_MODEL=gpt-4o-mini` |
| `chat_llm`       | `CHAT_LLM_`     | `CHAT_LLM_MODEL=gpt-4o-mini` |

Each `NodeLLMSettings` is constructed in `Settings.__init__` with the shared `_env_file`, following the existing pattern for `LLMSettings`, `LangSmithSettings`, etc.

### 2. Factory Function (`src/graph/nodes.py`)

Private module-level helper:

```python
_NODE_LLM_ATTR = {
    "intent": "intent_llm",
    "doc_gen": "doc_gen_llm",
    "doc_qa": "doc_qa_llm",
    "chat": "chat_llm",
}

def _get_node_llm(node_name: str) -> ChatOpenAI:
    """Return a ChatOpenAI configured for the given node, falling back to global settings."""
    attr = _NODE_LLM_ATTR.get(node_name)
    node_cfg = getattr(settings, attr, None) if attr else None

    base_url = (node_cfg and node_cfg.base_url) or settings.llm.base_url
    api_key = (node_cfg and node_cfg.api_key) or settings.llm.api_key
    model = (node_cfg and node_cfg.model) or settings.llm.model

    return ChatOpenAI(base_url=base_url, api_key=api_key, model=model)
```

### 3. Node Changes

Replace the 3-line `ChatOpenAI(...)` construction in each of the 4 node functions with:

```python
llm = _get_node_llm("intent")      # in intent_recognize
llm = _get_node_llm("doc_gen")     # in doc_gen
llm = _get_node_llm("doc_qa")     # in doc_qa
llm = _get_node_llm("chat")       # in chat
```

No other changes to node logic.

### 4. `.env.example` Update

Add commented-out examples for node-level overrides:

```bash
# --- Per-node LLM overrides (optional, falls back to LLM_* if unset) ---
# INTENT_LLM_MODEL=gpt-4o-mini
# DOC_GEN_LLM_MODEL=gpt-4
# DOC_QA_LLM_MODEL=gpt-4o-mini
# CHAT_LLM_MODEL=gpt-4o-mini
```

### 5. Testing

Extend existing test files (no new test files):

**`tests/config/test_settings.py`:**
- Default fallback: no node env vars set → `settings.intent_llm.model is None`, factory returns global model
- Node-level override: `INTENT_LLM_MODEL=gpt-4o-mini` → factory returns `gpt-4o-mini`
- Partial override: only `INTENT_LLM_MODEL` set, no `INTENT_LLM_BASE_URL` → base_url falls back to global

**`tests/graph/test_nodes.py`:**
- `_get_node_llm` unit test: mock `settings` with and without node config, verify correct ChatOpenAI params
- Existing node tests remain unchanged (they mock `ChatOpenAI` constructor)

## Files Changed

| File | Change |
|------|--------|
| `src/config/settings.py` | Add `NodeLLMSettings` class; add 4 node LLM attributes to `Settings` |
| `src/graph/nodes.py` | Add `_get_node_llm()` factory; replace 4 x 3-line `ChatOpenAI(...)` with 1-line calls |
| `.env.example` | Add commented-out node-level config examples |
| `tests/config/test_settings.py` | Add fallback and override tests for `NodeLLMSettings` |
| `tests/graph/test_nodes.py` | Add `_get_node_llm` unit tests |

## Why Not LangGraph Middleware

LangGraph's "middleware" refers to either:
1. **LangSmith deployment middleware** — HTTP-level Starlette middleware for headers/auth, not model selection
2. **LangChain node-style hooks** (`before_model`/`after_model`) — designed for `create_agent`'s internal model calls, not for custom `StateGraph` nodes that manually construct `ChatOpenAI`

Neither mechanism provides per-node model routing for hand-built StateGraph nodes. The static config + factory function approach is simpler, explicit, and fully aligned with the existing codebase patterns.
