# Doc Gen Pre-check: Target Resolution & Duplicate Detection

## Problem

The current doc generation flow has two usability issues:

1. **Duplicate generation**: When documentation already exists for an API, requesting it again regenerates from scratch instead of detecting the existing docs and asking the user.
2. **High input requirements**: Users must provide full file paths (e.g., `ubill-access-api/ubill-order/logic/BuyResource.go`) instead of just the API/function name (e.g., `BuyResource`).

## Approach

Agent-autonomous, prompt-driven solution. Provide tools and guidance via prompt; let the agent decide when and how to perform checks. No changes to graph nodes or routing logic.

## Changes

### 1. `src/prompts/system/doc_gen.md` — Add Pre-check Phase

Insert a new `### Pre-check: Target Resolution & Duplicate Detection` section before `### Task 1: Recursive Context Building`.

Content:

```markdown
### Pre-check: Target Resolution & Duplicate Detection

Before starting the documentation workflow, perform these checks:

**1. Resolve the target**
- If the user provided a full file path (contains `/` or ends with `.go`), use it directly as the entry file
- If the user provided a function/API name (e.g., `BuyResource`), use `find_function` to locate it first
  - If multiple matches are found, present all matches to the user and ask which one to document
  - If no match is found, inform the user and ask for clarification
  - If exactly one match is found, use it as the entry file

**2. Check for existing documentation**
- Use `list_documents` to check if documentation already exists for this API
- If documentation exists, inform the user and ask how to proceed:
  - View existing documentation
  - Regenerate and overwrite
  - Cancel
- Only proceed to Task 1 if the user confirms generation/regeneration
```

### 2. `src/prompts/user/doc_gen.md` — Flexible Wording

Change from:

```
请为以下文件生成接口文档：{file_path}
```

To:

```
请为以下目标生成接口文档：{file_path}
```

Single word change: `文件` → `目标`. Keeps the `{file_path}` template variable name unchanged to avoid code changes in `nodes.py`.

### 3. `src/tools/code_search.py` — Return All Matches

Current behavior: `find_function` returns only the first match and stops scanning.

New behavior: Collect all matches and return them as an array.

| Scenario | Current | New |
|----------|---------|-----|
| 1 match | `ok("找到函数定义", payload={file, line, content})` | `ok("找到 1 处函数定义", payload=[{file, line, content}])` |
| N matches | Impossible (early return) | `ok("找到 N 处函数定义", payload=[{...}, ...])` |
| 0 matches | `fail("未找到函数 X 的定义")` | No change |

Implementation: Remove the early `return` inside the file loop. Collect all matches into a list, then return after scanning all files.

Update the tool docstring to document that the payload is a list of matches.

### 4. Tests — Update Assertions

Update `tests/tools/test_code_search.py`:
- All existing tests that assert `payload` is a dict must be updated to assert `payload` is a list containing one dict
- Add a new test case for multiple matches (same function name in different files)

## Files Changed

| File | Change |
|------|--------|
| `src/prompts/system/doc_gen.md` | Add Pre-check section (~15 lines) |
| `src/prompts/user/doc_gen.md` | Change 1 word |
| `src/tools/code_search.py` | Return all matches (~10 lines changed) |
| `tests/tools/test_code_search.py` | Update assertions, add multi-match test |

## Files NOT Changed

- `src/graph/nodes.py` — no code changes
- `src/graph/graph.py` — no graph structure changes
- `src/prompts/system/intent.md` — intent extraction is free-form, works as-is
- Other tools — unaffected

## Compatibility

- The `doc_gen` prompt's Fallback rule checks for `find_function` returning `"未找到"`. The failure case is unchanged, so the rule remains valid.
- Success payload changes from object to array. The LLM interprets JSON tool results naturally; no prompt adjustments needed beyond the Pre-check section.
- `doc_gen` node code reads `state["params"].get("file_path", "")` — this works whether the value is a full path or a short name, since the Pre-check prompt instructs the agent to resolve it.
