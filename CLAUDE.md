# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

doc-flow is an AI-powered documentation generator that analyzes Go source code and produces structured Markdown API docs. It uses a LangGraph StateGraph with a ReAct agent loop: intent recognition routes to doc generation, which calls tools in a loop until complete. Entry point `app.py` serves the Chainlit chat UI; `main.py` is not yet wired up.

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
START -> intent_recognize -> [route_by_intent] -> doc_gen -> [route_doc_gen] -> tools (ToolNode)
                                    |                              |                |
                                    v                              v                |
                                   END                            END               |
                                                                                    |
                                                          doc_gen <-----------------+
                                                          (ReAct loop continues)
```
- `State(TypedDict)` holds `messages` (with `add_messages` reducer), `intent`, `confidence`, `params`.
- `intent_recognize` loads the `"intent"` prompt, calls `ChatOpenAI`, parses JSON response into `intent`/`confidence`/`params`.
- `doc_gen` loads the `"doc_gen"` prompt, binds 5 tools to `ChatOpenAI` (all tools except `git_diff`), returns AI message.
- `route_by_intent` sends to `doc_gen` if intent matches, else `END`. `route_doc_gen` sends to `tools` if tool calls present, else `END`.
- `git_diff` tool exists but is intentionally excluded from the graph's `TOOLS` list (future feature).

**Key patterns:**

- **Singleton config**: `from src.config import settings` — instantiated at import time. Sub-configs use `env_prefix` (e.g., `LLM_`, `LANGSMITH_`, `LOG_`). `LLM_API_KEY` is required.
- **`AGENT_WORK_DIR` path resolution**: `code_scanner`, `file_reader`, and `git_diff` tools resolve all file/directory paths relative to `settings.agent_work_dir` (defaults to `.`). This sandboxes tool access to the configured working directory.
- **JSON envelope responses**: All tools return via `ok(message, payload)` / `fail(error, message)` from `src/tools/utils.py` — consistent `{success, message, payload, error}` JSON strings.
- **LangChain @tool decorator**: Every function in `src/tools/` is a LangChain tool with docstrings serving as LLM tool descriptions.
- **Prompt templates**: Stored as `.md` files under `src/prompts/system/` and `src/prompts/user/`, loaded by name via `load_prompt("intent")` or `load_prompt("doc_gen")`.
- **Structured JSON logging**: Custom `JSONFormatter` producing `{time, level, module, message, error}`. `TimedRotatingFileHandler` with 7-day retention to `logs/app.log`.

**Testing conventions:**
- Tests mirror `src/` structure under `tests/`
- Use `monkeypatch` for env vars, `tmp_path` for filesystem isolation
- Logging tests use a `_reset_logging` autouse fixture to prevent handler accumulation
- Tools are invoked via `.invoke({"param": "value"})` (LangChain tool invocation API)
- Graph node tests use `@patch("src.graph.nodes.ChatOpenAI")` to mock LLM calls — no real API calls in tests
- Config singleton tests that need a fresh instance use `monkeypatch.delitem(sys.modules, "src.config")` to force re-import
- TDD workflow: write failing test first, implement, verify green, commit

## Environment

- Python 3.11 (`.python-version`)
- Package manager: `uv`
- Copy `.env.example` to `.env` and set `LLM_API_KEY` at minimum
- Prompts, tool docstrings, and error messages are in Chinese (Simplified)
- Design plans and specs live under `docs/plans/` and `docs/superpowers/`
