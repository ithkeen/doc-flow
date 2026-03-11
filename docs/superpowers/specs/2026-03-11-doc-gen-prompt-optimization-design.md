# Doc Gen Prompt Optimization Design

**Date:** 2026-03-11
**Status:** Approved
**Scope:** `src/prompts/system/doc_gen.md`

## Problem Statement

The current `doc_gen.md` system prompt has several issues:

1. **Redundant tool listing** — 5 tools are manually described in the prompt, but LangChain `bind_tools` already injects tool schemas and docstrings automatically. This wastes tokens.
2. **Shallow workflow** — The 6-step linear flow (scan → read → analyze → generate → check → save) lacks a planning phase and provides no guidance on tracing dependencies across files.
3. **Vague output format** — Only 3 lines describe the expected output ("接口名称、请求方法、路径、参数说明、返回值说明"), leading to inconsistent document quality.
4. **No quality constraints** — No rules for handling missing comments, no table format enforcement, no error code coverage requirements.

## Design Decisions

| Decision | Chosen | Rationale |
|----------|--------|-----------|
| Tool descriptions in prompt | Remove | `bind_tools` handles this; avoids duplication and token waste |
| Workflow model | Three-task: Deep Reading → Generate → Save | User specifies files directly; LLM needs to trace dependencies, not scan directories |
| Document type | HTTP API documentation (non-RESTful) | User's Go codebase exposes HTTP APIs, not RESTful endpoints |
| Document template | Structured Markdown with mandatory tables | Ensures consistent output format across all generated docs |
| Request examples | curl format | More practical for API consumers than Go code snippets |
| Document language | Mixed: English headers/labels, Chinese descriptions | Matches team conventions |
| Function Signature section | Excluded | Not needed for API-level documentation |
| HTTP Method/Path fields | Excluded | Not a RESTful API; these distinctions add noise |

## Optimized Prompt

### Role Definition

```
You are a professional Go API documentation generator.

Your responsibilities:
- Analyze Go source code to extract API interface information
- Generate structured, consistently formatted Markdown API documentation
- Organize documentation by module and ensure completeness and accuracy

Constraints:
- Only document exported functions (capitalized names); skip unexported functions
- If source code lacks comments, infer the function's purpose from its signature and implementation, and mark it as "[Inferred from code]"
- Never fabricate parameters, return values, or behaviors that do not exist in the code
```

### Three-Task Workflow

```
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
- Confirm the module name with the user if not already clear
- Use `save_document` to store the generated Markdown file
```

### Documentation Template

```
## Documentation Template

Every generated document MUST follow this structure:

# {API Name}

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
  -d '{
    "field": "value"
  }'
```

## Response Example

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "field": "value"
    }
}
```
```

### Quality Rules

```
## Quality Rules

- All parameter and response tables MUST use Markdown table format
- Type names must match the exact Go types from source code (e.g., `int64`, `[]string`, not `number`, `array`)
- Error codes section must cover every error return path found in the code; do not omit any
- Request examples must use curl format with realistic field values derived from actual struct definitions
- Response examples must reflect the actual response struct; do not use generic placeholders
- If a struct field has validation tags (e.g., `binding:"required"`, `validate:"max=100"`), document the validation rules in the Description column
- For nested structs, flatten into dot notation in tables (e.g., `data.user.name`) or use a sub-table
- Generate documentation content in a mix of English (headers, labels) and Chinese (descriptions)
```

## Changes Summary

| Aspect | Before | After |
|--------|--------|-------|
| Role definition | Single sentence | Clear responsibilities + 3 constraints (no fabrication, exported-only, inferred marking) |
| Tool listing | 5 tools manually listed | Removed (bind_tools handles injection) |
| Workflow | 6-step linear: scan → read → analyze → generate → check → save | 3-task: Deep Reading → Generate → Save |
| Reading strategy | "Read files one by one" | Dependency-tracing deep read with explicit completion criteria |
| Document format | 3 vague lines | Full structured template with 6 sections and mandatory table format |
| Quality control | None | 8 explicit rules |
| Language | Chinese only | Mixed English/Chinese |

## Implementation

Only one file needs to change: `src/prompts/system/doc_gen.md`. No code changes required — the prompt is loaded by `load_prompt("doc_gen")` and the graph nodes remain unchanged.

The `user/doc_gen.md` template (`请为以下目录生成接口文档：{directory_path}`) should also be reviewed since the workflow now expects user-specified files rather than directory scanning. This is out of scope for this design but noted as a follow-up.