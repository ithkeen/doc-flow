# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

doc-flow is a LangGraph-based chatbot for API documentation Q&A and generation. It uses intent recognition to route user queries to specialized nodes: `doc_qa` (RAG-powered answers about existing docs), `doc_gen` (generate API docs via a ReAct tool loop), or `chat` (general conversation). The target codebase being documented is Go source code.

## Development Commands

```bash
# Run Chainlit UI
chainlit run app.py

# Run all tests
pytest

# Run a single test file
pytest tests/graph/test_doc_qa.py

# Run a single test
pytest tests/graph/test_doc_qa.py::test_doc_qa_retrieves_docs_and_injects_context

# Index docs into Chroma vector store
python scripts/index_docs.py                        # all docs
python scripts/index_docs.py --file proj/mod/Api.md # single file

# LangGraph Studio
langgraph dev
```

## Architecture

### Graph Flow (src/graph/graph.py)

```
START → intent_recognize → route_by_intent → [doc_qa | doc_gen | chat] → END
                                                  │
                                          doc_gen ←→ doc_gen_tools (ReAct loop)
```

- `intent_recognize` parses LLM output as JSON to extract `{"intent": "..."}`, with regex stripping of markdown code fences
- `doc_gen` binds 8 tools to the LLM and loops with `ToolNode` until no more tool calls
- `route_by_intent` and `route_doc_gen` are conditional edge functions (not nodes)

### State

`State` (TypedDict): `messages` (Annotated list with `add_messages` reducer) + `intent` (str). All nodes receive `(state, config)` and return partial state dicts.

### Two Directory Spaces

The system operates on two external directories configured via env vars:
- **`CODE_SPACE_DIR`**: Go source code root — tools `read_file`, `find_function`, `find_struct`, `match_api_name` read from here
- **`DOCS_SPACE_DIR`**: Documentation output root — tools `write_file`, `load_docgen_config` operate here; `scripts/index_docs.py` indexes .md files from here into Chroma

### Tool Response Convention

All tools in `src/tools/` return JSON envelope strings via `ok()`/`fail()` from `src/tools/utils.py`:
```json
{"success": bool, "message": "...", "payload": any, "error": "..."}
```
The DB-backed tools (`save_api_index`, `query_api_index`) use `ToolException` with `handle_tool_error = True` instead.

### RAG Pipeline (src/rag/)

- `get_retriever()` returns a cached Chroma retriever (top-k=3)
- `doc_qa` node gracefully degrades to empty context if retrieval fails
- Embeddings reuse the same `LLM_BASE_URL`/`LLM_API_KEY` with `LLM_EMBED_MODEL`

### Prompt System (src/prompts/)

Prompts are markdown files in `system/{name}.md` and `user/{name}.md`. `load_prompt(name)` reads both (either optional, but at least one required) and returns a `ChatPromptTemplate`. Current prompt names: `intent`, `doc_qa`, `doc_gen`, `chat`.

### Configuration (src/config/)

`settings` is a module-level singleton (`Settings()`) constructed at import time from `.env` via pydantic-settings. Sub-configs use env prefixes: `LLM_*`, `LANGSMITH_*`, `LOG_*`, `DB_*`, `CHROMA_*`. Database config (`DB_*`) is optional; all others are required at startup.

### LLM Factory (src/config/llm.py)

`get_llm(mode)` maps mode strings to model names: `"default"` → `LLM_DEFAULT_MODEL`, `"chat"` → `LLM_CHAT_MODEL`, `"doc_gen"` → `LLM_DOC_GEN_MODEL`. The intent node uses `get_llm("intent")` which falls back to default. All use `ChatOpenAI` with shared `base_url`/`api_key`.

## Testing Patterns

- `asyncio_mode = "auto"` in pyproject.toml — async tests need no decorator
- `tests/conftest.py` has an autouse fixture `_stub_env` that injects dummy env vars for all tests, so `Settings()` can construct without a real `.env`
- `mysql.connector` must be mocked before importing tool modules that depend on it (see `test_doc_qa.py` for the `sys.modules` mock pattern)
- Tests mock `get_llm`, `get_retriever`, and other dependencies via `unittest.mock.patch`

## Environment

Requires `.env` file — copy from `.env.example`. Python 3.11+. Uses `uv` (pyproject.toml with dependency-groups).
