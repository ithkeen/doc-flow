# Batch Doc Gen — Standalone doc_gen_dispatcher

## Context

`doc_gen_dispatcher` currently only runs as part of the `project_explore` flow, reading `task.md` from the last AI message's `tool_calls`. When LLM rate limits are hit mid-generation, the process stops and cannot be resumed without re-running the full `project_explore` flow.

The goal is to allow `doc_gen_dispatcher` to run standalone, triggered by user intent, reading a task file directly.

## Intent Recognition

- **`intent_recognize`** (src/graph/nodes.py) parses `{"intent": "..."}` from LLM JSON output.
- Extend the prompt (`system/intent.md`) to also recognize `batch_doc_gen` intent.
- Extract task file path from user message using regex (e.g., `"根据 ... 生成文档"` or `"based on ... generate docs"`).
- Set `intent = "batch_doc_gen"` and store `task_file_path` in `config["configurable"]["task_file_path"]`.

## Routing

- **`route_by_intent`** — add branch: `batch_doc_gen` → `doc_gen_dispatcher`.
- Existing `project_explore` flow continues to work unchanged.

## doc_gen_dispatcher — Dual Mode

**Mode A — Graph flow (existing):**
`doc_gen_dispatcher` reads `task_file_path` from `state["messages"]` (searching for `write_file` tool calls of `task.md`).

**Mode B — Standalone (new):**
Read `task_file_path` from `config["configurable"]["task_file_path"]` instead of scanning messages.

Detection logic: if `config["configurable"]["task_file_path"]` is set and non-empty, use it; otherwise fall back to message scanning.

**Task file format:** Markdown table (same as `task.md`). `_read_task_file(project_name)` already parses this; the project name is extracted from the task file path.

## Data Flow

```
用户: "根据 proj/task.md 生成文档"
  → intent_recognize: intent="batch_doc_gen", task_file_path="proj/task.md"
  → route_by_intent: batch_doc_gen → doc_gen_dispatcher
  → doc_gen_dispatcher: reads task_file_path from config, parses .md, dispatches
  → synthesize_overview → END
```

## Changes

| File | Change |
|------|--------|
| `src/prompts/system/intent.md` | Add `batch_doc_gen` intent recognition with task file path extraction |
| `src/graph/nodes.py` | `doc_gen_dispatcher`: check `config["configurable"]["task_file_path"]` first; `route_by_intent`: add `batch_doc_gen` branch |

## Verification

- Add test: `route_by_intent` with `intent="batch_doc_gen"` returns `"doc_gen_dispatcher"`
- Add test: `doc_gen_dispatcher` with `task_file_path` in config reads it directly without message scanning
