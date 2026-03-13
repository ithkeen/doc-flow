# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

doc-flow is an AI-powered documentation generator that analyzes Go source code and produces structured Markdown API docs. It uses a LangGraph StateGraph with a ReAct agent loop: intent recognition routes to doc generation, doc Q&A, or general chat. Entry point `app.py` (project root) serves the Chainlit chat UI.

## Commands

```bash
uv sync                              # Install dependencies
uv run pytest tests/ -v              # Run all tests
uv run pytest tests/config/ -v       # Run a specific test directory
uv run pytest tests/config/test_settings.py -v  # Run a single test file
uv run pytest tests/config/test_settings.py::TestClassName::test_method -v  # Run a single test
uv run langgraph dev                 # Run LangGraph dev server (uses langgraph.json → src/graph/graph.py:build_graph)
uv run chainlit run app.py -w            # Run Chainlit chat UI (hot reload)
```

No linter or formatter is configured.

## Architecture

**Module dependency flow:**
```
src/config (settings singleton via pydantic-settings, .env loading)
    └─> src/logs (JSON logging with daily file rotation)
        └─> src/tools (LangChain @tool functions for Go code scanning/reading/doc storage/git diff)

src/prompts (ChatPromptTemplate loader from .md files, independent of tools)

src/graph (LangGraph StateGraph: depends on config, logs, prompts, and tools)
```

**Graph orchestration (`src/graph`):**
```
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
```
- `State(TypedDict)` holds `messages` (with `add_messages` reducer), `intent`, `confidence`, `params`.
- `intent_recognize`, `doc_gen`, `doc_qa`, and `chat` are all **async** functions that accept `RunnableConfig` as a second parameter and forward it to LLM calls. This is required for Chainlit's `LangchainCallbackHandler` and to avoid callback threading issues.
- `intent_recognize` loads the `"intent"` prompt, calls `ChatOpenAI`, parses JSON response into `intent`/`confidence`/`params`. Uses `state["messages"][-1].content` (last message).
- `doc_gen` loads the `"doc_gen"` prompt, binds `TOOLS` (6 tools: `scan_directory`, `read_file`, `save_document`, `read_document`, `list_documents`, `find_function`) to `ChatOpenAI`.
- `doc_qa` loads the `"doc_qa"` prompt, binds `QA_TOOLS` (2 tools: `read_document`, `list_documents`) to `ChatOpenAI`. Uses `_get_last_human_message()` for the user input variable.
- `chat` loads the `"chat"` prompt, calls `ChatOpenAI` **without** binding tools (pure LLM conversation). Uses full message history for multi-turn context. System prompt softly guides users toward doc_gen/doc_qa features.
- `route_by_intent` routes to `"doc_gen"`, `"doc_qa"`, `"chat"`, or `END`. `route_doc_gen` and `route_doc_qa` each route to their respective `ToolNode` if tool calls are present, else `END`.
- `git_diff` tool exists but is intentionally excluded from both tool lists (future feature).

**Key patterns:**

- **Singleton config**: `from src.config import settings` — instantiated at import time. Sub-configs use `env_prefix` (e.g., `LLM_`, `LANGSMITH_`, `LOG_`). `LLM_API_KEY` is required.
- **`AGENT_WORK_DIR` path resolution**: `code_scanner`, `file_reader`, `find_function`, and `git_diff` tools resolve all file/directory paths relative to `settings.agent_work_dir` (defaults to `.`). This sandboxes tool access to the configured working directory.
- **Tool constraints**: `file_reader` truncates files over 100KB (`MAX_FILE_SIZE_KB = 100`). `doc_storage` enforces module names matching `^[a-z][a-z0-9_]*$`. `git_diff` uses a 30s subprocess timeout and reads `.last_commit` to track the last doc generation point. `find_function` searches Go function definitions by regex-matching `func <name>(` patterns. Returns only the first match (file path, line number, content). Auto-escapes regex special characters. Falls back to latin-1 encoding on `UnicodeDecodeError`.
- **JSON envelope responses**: All tools return via `ok(message, payload)` / `fail(error, message)` from `src/tools/utils.py` — consistent `{success, message, payload, error}` JSON strings.
- **LangChain @tool decorator**: Every function in `src/tools/` is a LangChain tool with docstrings serving as LLM tool descriptions.
- **Prompt templates**: Stored as `.md` files under `src/prompts/system/` and `src/prompts/user/`, loaded by name via `load_prompt("intent")`, `load_prompt("doc_gen")`, `load_prompt("doc_qa")`, or `load_prompt("chat")`. At least one of system/user must exist for a given name.
- **Structured JSON logging**: Custom `JSONFormatter` producing `{time, level, module, message, error}`. `TimedRotatingFileHandler` with 7-day retention to `logs/app.log`.

**Testing conventions:**
- Tests mirror `src/` structure under `tests/`
- Use `monkeypatch` for env vars, `tmp_path` for filesystem isolation
- Async tests use `pytest-asyncio` with explicit `@pytest.mark.asyncio` decorators
- Logging tests use a `_reset_logging` autouse fixture to prevent handler accumulation
- Tools are invoked via `.invoke({"param": "value"})` (LangChain tool invocation API)
- Graph node tests use `@patch("src.graph.nodes.ChatOpenAI")` to mock LLM calls — no real API calls in tests
- `tests/test_app.py` patches `sys.modules` with a mock `chainlit` module before importing `app` (then `importlib.reload`), because Chainlit decorators execute at import time. Streaming is filtered to `doc_gen`, `doc_qa`, and `chat` nodes.
- Config singleton tests that need a fresh instance use `monkeypatch.delitem(sys.modules, "src.config")` to force re-import
- TDD workflow: write failing test first, implement, verify green, commit

## Environment

- Python 3.11 (`.python-version`)
- Package manager: `uv`
- Copy `.env.example` to `.env` and set `LLM_API_KEY` at minimum
- Prompts, tool docstrings, and error messages are in Chinese (Simplified), except the `doc_gen` system prompt which is in English
- Design plans and specs live under `docs/plans/` and `docs/superpowers/`
