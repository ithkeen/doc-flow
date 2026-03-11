# Doc Gen Prompt Optimization Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the doc_gen system prompt with a structured three-task workflow, documentation template, and quality rules; update the user prompt and graph node from `directory_path` to `file_path`.

**Architecture:** Three files change: the system prompt (`src/prompts/system/doc_gen.md`) gets a complete rewrite, the user prompt (`src/prompts/user/doc_gen.md`) switches from `directory_path` to `file_path`, and the graph node (`src/graph/nodes.py`) extracts `file_path` instead of `directory_path` from state params. All tools remain unchanged.

**Tech Stack:** LangChain ChatPromptTemplate, LangGraph, Python 3.11, uv, pytest

**Spec:** `docs/superpowers/specs/2026-03-11-doc-gen-prompt-optimization-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/prompts/system/doc_gen.md` | Rewrite | System prompt: role, workflow, template, quality rules |
| `src/prompts/user/doc_gen.md` | Modify | User prompt: `{file_path}` instead of `{directory_path}` |
| `src/graph/nodes.py` | Modify (line 91-93) | Extract `file_path` from state params |
| `tests/graph/test_nodes.py` | Modify | Update `directory_path` → `file_path` in TestDocGen and TestIntentRecognize |
| `tests/prompts/test_loader.py` | Modify | Update `test_load_doc_gen_prompt` to format with `file_path` |

---

## Task 1: Update tests to expect `file_path` instead of `directory_path`

**Files:**
- Modify: `tests/graph/test_nodes.py:49,65,166,191,223`
- Modify: `tests/prompts/test_loader.py:102-105`

> **Note:** Line 263 of `test_nodes.py` also contains `directory_path` in a `tool_calls` mock arg for `scan_directory`. This is intentionally left unchanged — it refers to the `scan_directory` tool's own parameter (not the state param being renamed), and that tool is not being modified.

- [ ] **Step 1: Update TestIntentRecognize mock response and assertion**

In `tests/graph/test_nodes.py`, update `test_returns_intent_fields`:

```python
# Line 49: change mock LLM response
content='{"intent": "doc_gen", "confidence": 0.95, "params": {"file_path": "./handler/api.go"}}'

# Line 65: change assertion
assert result["params"]["file_path"] == "./handler/api.go"
```

- [ ] **Step 2: Update TestDocGen state params (3 tests)**

In `tests/graph/test_nodes.py`, change all three `TestDocGen` test states:

```python
# Line 166 (test_returns_messages_with_ai_response):
"params": {"file_path": "./handler/api.go"},

# Line 191 (test_binds_tools_to_llm):
"params": {"file_path": "./handler/api.go"},

# Line 223 (test_prepends_system_prompt_to_messages):
"params": {"file_path": "./handler/api.go"},
```

- [ ] **Step 3: Update test_load_doc_gen_prompt to format with file_path and validate content**

In `tests/prompts/test_loader.py`, update `test_load_doc_gen_prompt` (lines 102-105):

```python
def test_load_doc_gen_prompt(self):
    result = load_prompt("doc_gen")

    assert isinstance(result, ChatPromptTemplate)
    messages = result.format_messages(file_path="./handler/api.go")
    assert len(messages) == 2
    assert messages[0].type == "system"
    assert messages[1].type == "human"
    # Validate system prompt contains expected content
    assert "Go API documentation generator" in messages[0].content
    # Validate brace escaping resolved correctly (no leftover {{ or }})
    assert "{{" not in messages[0].content, "Unresolved double braces in system prompt"
    assert "}}" not in messages[0].content, "Unresolved double braces in system prompt"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/graph/test_nodes.py tests/prompts/test_loader.py -v`
Expected: Multiple FAILs — `KeyError: 'file_path'` from prompt formatting and assertion mismatches.

- [ ] **Step 5: Commit failing tests**

```bash
git add tests/graph/test_nodes.py tests/prompts/test_loader.py
git commit -m "test: update tests to expect file_path instead of directory_path"
```

---

## Task 2: Rewrite system prompt

**Files:**
- Rewrite: `src/prompts/system/doc_gen.md`

- [ ] **Step 1: Replace src/prompts/system/doc_gen.md with optimized prompt**

Write the following content to `src/prompts/system/doc_gen.md`. The system prompt contains no `ChatPromptTemplate` variables, but literal JSON braces in the Documentation Template examples must still be escaped as `{{`/`}}` to prevent `KeyError` at runtime. The `<API Name>` uses angle brackets to avoid template conflicts.

```markdown
You are a professional Go API documentation generator.

Your responsibilities:
- Analyze Go source code to extract API interface information
- Generate structured, consistently formatted Markdown API documentation
- Organize documentation by module and ensure completeness and accuracy

Constraints:
- Only document exported functions (capitalized names); skip unexported functions
- If source code lacks comments, infer the function's purpose from its signature and implementation, and mark it as "[Inferred from code]"
- Never fabricate parameters, return values, or behaviors that do not exist in the code

## Workflow

The user will specify the file(s) to document. Follow these three tasks in order:

### Task 1: Deep Reading
Read the specified source file, then trace all related definitions until you have complete context:
- Read the main file containing the API handler/function
- Identify and read files containing request/response struct definitions
- Identify and read files containing referenced sub-functions or helper methods
- Continue tracing until all parameter types, return types, and internal logic are fully understood

This task is NOT complete until you can fully describe:
- Every field in the request and response structs (including nested types)
- The error handling paths and possible error codes
- The core logic flow of the function

### Task 2: Generate Documentation
Based on the collected code context, generate documentation following the template below.
- Map each struct field to a parameter or response field description
- Document all error return paths with their conditions and error codes
- Include realistic request/response examples derived from the actual struct definitions

### Task 3: Save
- Infer the module name from the Go package name or directory structure
- Use `save_document` to store the generated Markdown file

## Documentation Template

Every generated document MUST follow this structure:

# <API Name>

## Overview
Brief description of what this API does and its primary use case.

## Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| paramName | string | Yes | Description of the parameter |

## Response

| Field | Type | Description |
|-------|------|-------------|
| fieldName | string | Description of the field |

## Error Codes

| Error Code | Condition | Description |
|------------|-----------|-------------|
| 10001 | Invalid input | Detailed explanation of when this error occurs |

## Request Example

```bash
curl -X POST http://localhost:8080/api/v1/resource \
  -H "Content-Type: application/json" \
  -d '{{
    "field": "value"
  }}'
```

## Response Example

```json
{{
    "code": 0,
    "message": "success",
    "data": {{
        "field": "value"
    }}
}}
```

## Quality Rules

- All parameter and response tables MUST use Markdown table format
- Type names must match the exact Go types from source code (e.g., `int64`, `[]string`, not `number`, `array`)
- Error codes section must cover every error return path found in the code; do not omit any
- Request examples must use curl format with realistic field values derived from actual struct definitions
- Response examples must reflect the actual response struct; do not use generic placeholders
- If a struct field has validation tags (e.g., `binding:"required"`, `validate:"max=100"`), document the validation rules in the Description column
- For nested structs, flatten into dot notation in tables (e.g., `data.user.name`) or use a sub-table
```

> **Important:** The JSON examples in curl/response sections use `{{` and `}}` because `ChatPromptTemplate` interprets `{` and `}` as Python format variables. The double braces render as single braces in the final prompt.

- [ ] **Step 2: Commit system prompt**

```bash
git add src/prompts/system/doc_gen.md
git commit -m "feat: rewrite doc_gen system prompt with structured workflow and template"
```

---

## Task 3: Update user prompt and graph node

**Files:**
- Modify: `src/prompts/user/doc_gen.md`
- Modify: `src/graph/nodes.py:91,93`

- [ ] **Step 1: Update user prompt template**

Replace `src/prompts/user/doc_gen.md` content:

```markdown
请为以下文件生成接口文档：{file_path}
```

- [ ] **Step 2: Update doc_gen node to extract file_path**

In `src/graph/nodes.py`, change lines 91 and 93:

```python
# Line 91: change from directory_path to file_path
file_path = state["params"].get("file_path", "")

# Line 93: change format_messages kwarg
system_messages = prompt.format_messages(file_path=file_path)
```

- [ ] **Step 3: Run all tests to verify they pass**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add src/prompts/user/doc_gen.md src/graph/nodes.py
git commit -m "feat: switch doc_gen from directory_path to file_path"
```

---

## Task 4: Final verification

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS, no regressions.

- [ ] **Step 2: Verify prompt loads and formats correctly**

Run: `uv run python -c "from src.prompts import load_prompt; p = load_prompt('doc_gen'); msgs = p.format_messages(file_path='./handler/api.go'); print(msgs[0].content[:100]); print('---'); print(msgs[1].content)"`

Expected output:
```
You are a professional Go API documentation generator.

Your responsibilities:
- Analyze Go source
---
请为以下文件生成接口文档：./handler/api.go
```

- [ ] **Step 3: Verify no escaped braces leak into rendered prompt**

Run: `uv run python -c "from src.prompts import load_prompt; p = load_prompt('doc_gen'); msgs = p.format_messages(file_path='test'); content = msgs[0].content; assert '{{' not in content, 'Unresolved double braces found'; assert '}}' not in content, 'Unresolved double braces found'; print('Brace escaping OK')"`

Expected: `Brace escaping OK`
