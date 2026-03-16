# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

doc-flow is an AI-powered documentation system for Go source code. The Chainlit chat UI (`app.py`) provides doc Q&A and general chat via a LangGraph StateGraph. API doc generation is handled exclusively by the `src/generator` CLI module.

## Commands

```bash
uv sync                              # Install dependencies
uv run langgraph dev                 # Run LangGraph dev server (uses langgraph.json → src/graph/graph.py:build_graph)
uv run chainlit run app.py -w        # Run Chainlit chat UI (hot reload)
uv run python -m src.generator --project <name>   # Batch generate docs for a project
uv run python -m src.generator --all               # Batch generate docs for all projects
uv run pytest                        # Run all tests
uv run pytest tests/generator/test_runner.py       # Run a single test file
uv run pytest tests/generator/test_runner.py::TestFilterApis::test_skip_blacklisted  # Run a single test
```

No linter or formatter is configured. Tests use `asyncio_mode = "auto"` (pytest-asyncio).

## Architecture

**Module dependency flow:**
```
src/config (settings singleton via pydantic-settings, .env loading, get_node_llm factory)
    └─> src/logs (JSON logging with daily file rotation)
        └─> src/tools (LangChain @tool functions for Go code scanning/reading/doc storage/git diff)

src/prompts (ChatPromptTemplate loader from .md files, independent of tools)

src/graph (LangGraph StateGraph: depends on config, logs, prompts, and tools)

src/generator (batch doc generation CLI: depends on config, tools, prompts)
    ├─> config.py     — Pydantic models for .docflow.yaml project configuration
    ├─> discovery.py   — Go source scanning + module resolution via fnmatch
    ├─> index.py       — INDEX.md file management (regex-based Markdown table parser)
    ├─> graph.py       — Independent StateGraph with gen_doc ReAct loop (uses batch_doc_gen prompt)
    ├─> runner.py      — Orchestrator: discover → filter → generate → update index
    └─> __main__.py    — CLI entry point (argparse: --project/--all, --api, --force, --dry-run)
```

**Graph orchestration (`src/graph`):**
```
START -> intent_recognize -> [route_by_intent] -+-> doc_qa -> [route_doc_qa] -> qa_tools -> doc_qa (ReAct loop)
                                                |                     |
                                                |                     +-> END
                                                |
                                                +-> chat -> END
                                                |
                                                +-> END (unknown intent fallback)
```
- `State(TypedDict)` holds `messages` (with `add_messages` reducer) and `intent`.
- `intent_recognize`, `doc_qa`, and `chat` are all **async** functions that accept `RunnableConfig` as a second parameter and forward it to LLM calls. This is required for Chainlit's `LangchainCallbackHandler` and to avoid callback threading issues.
- `intent_recognize` loads the `"intent"` prompt, calls `ChatOpenAI`, parses JSON response to extract `intent`. Uses `state["messages"][-1].content` (last message).
- `doc_qa` loads the `"doc_qa"` prompt, binds `QA_TOOLS` (2 tools: `read_document`, `list_documents`) to `ChatOpenAI`. Uses `_get_last_human_message()` for the user input variable.
- `chat` loads the `"chat"` prompt, calls `ChatOpenAI` **without** binding tools (pure LLM conversation). Uses full message history for multi-turn context. System prompt guides users toward doc_qa features and directs doc generation requests to the CLI tool.
- `route_by_intent` routes to `"doc_qa"`, `"chat"`, or `END`. `route_doc_qa` routes to `"qa_tools"` ToolNode
- `git_diff` tool exists but is intentionally excluded from `QA_TOOLS` (future feature).

**Key patterns:**

- **Singleton config**: `from src.config import settings` — instantiated at import time. Sub-configs use `env_prefix` (e.g., `LLM_`, `LANGSMITH_`, `LOG_`). `LLM_API_KEY` is required. Per-node LLM overrides use `NodeLLMSettings` with prefixes `INTENT_LLM_`, `DOC_GEN_LLM_`, `DOC_QA_LLM_`, `CHAT_LLM_` — each field (`model`, `base_url`, `api_key`) falls back to global `LLM_*` when unset. The `get_node_llm(node_name)` factory in `src/config/llm.py` resolves the per-node → global fallback chain and returns a `ChatOpenAI` instance.
- **`AGENT_WORK_DIR` path resolution**: `code_scanner`, `file_reader`, `find_function`, and `git_diff` tools resolve all file/directory paths relative to `settings.agent_work_dir` (defaults to `.`). This sandboxes tool access to the configured working directory.
- **Tool constraints**: `file_reader` truncates files over 100KB (`MAX_FILE_SIZE_KB = 100`). `doc_storage` enforces module names matching `^[a-z][a-z0-9_]*(/[a-z][a-z0-9_]*)*$` (supports slash-separated paths like `access/order`). `git_diff` uses a 30s subprocess timeout and reads `.last_commit` to track the last doc generation point. `find_function` searches Go function definitions by regex-matching `func <name>(` patterns. Returns all matches as a list (each with file path, line number, content). Auto-escapes regex special characters. Falls back to latin-1 encoding on `UnicodeDecodeError`.
- **JSON envelope responses**: All tools return via `ok(message, payload)` / `fail(error, message)` from `src/tools/utils.py` — consistent `{success, message, payload, error}` JSON strings.
- **LangChain @tool decorator**: Every function in `src/tools/` is a LangChain tool with docstrings serving as LLM tool descriptions.
- **Prompt templates**: Stored as `.md` files under `src/prompts/system/` and `src/prompts/user/`, loaded by name via `load_prompt("intent")`, `load_prompt("doc_qa")`, `load_prompt("chat")`, or `load_prompt("batch_doc_gen")`. At least one of system/user must exist for a given name. The `batch_doc_gen` prompt uses explicit template variables (`{project}`, `{module}`, `{function_name}`, `{source_file}`, `{source_line}`) instead of relying on tool-based pre-check.
- **Structured JSON logging**: Custom `JSONFormatter` producing `{time, level, module, message, error}`. `TimedRotatingFileHandler` with 7-day retention to `logs/app.log`.


## Environment

- Python 3.11 (`.python-version`)
- Package manager: `uv`
- Copy `.env.example` to `.env` and set `LLM_API_KEY` at minimum
- Prompts, tool docstrings, and error messages are in Chinese (Simplified), except the `batch_doc_gen` system prompt which is in English
