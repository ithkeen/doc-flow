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
  - If multiple matches are found, present all matches to the user and ask which one to document. The user's reply will re-enter the graph through intent recognition — they should reply with a specific path or index, which will resolve cleanly in the next Pre-check pass.
  - If no match is found, inform the user and ask for clarification
  - If exactly one match is found, use it as the entry file

Note: The heuristic for distinguishing file paths from function names assumes function names do not contain `/` or `.go`, which is true for valid Go identifiers.

**2. Check for existing documentation**
- Use `list_documents` (without specifying a module name) to get a full listing of all existing documentation
- Search the returned document names for the target API name (best-effort name matching — the saved document name may not exactly match the function name)
- If a likely match is found, inform the user and ask how to proceed:
  - View existing documentation
  - Regenerate and overwrite
  - Cancel
- Only proceed to Task 1 if the user confirms generation/regeneration, or if no existing documentation is found
```

Note: The agent does not know the module name at Pre-check time (it is inferred later in Task 4 from the Go package/directory structure). Calling `list_documents()` without a module lists all modules, allowing the agent to scan all document names. This is a best-effort heuristic — if the document was saved under a different name than the function, the agent may not detect the duplicate.

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

Update the tool docstring to document that the payload is a list of matches. New `Returns` line:

> `JSON envelope，payload 为匹配列表，每个元素包含 file（文件路径）、line（行号）、content（该行内容）。`

### Impact on Task 1: Recursive Context Building

During Task 1, the agent uses `find_function` repeatedly to resolve unresolved references. With the new array payload, the agent may receive multiple matches for helper functions too. Add a brief note in the `doc_gen` system prompt's Task 1 section:

> When `find_function` returns multiple matches during context building, prefer the match in the same package or directory as the calling code.

This is a one-line addition to the existing Task 1 step 4.

### 4. Tests — Update Assertions

Update `tests/tools/test_code_search.py`:
- All existing tests that assert `payload` is a dict must be updated to assert `payload` is a list containing one dict
- Add a new test case for multiple matches (same function name in different files)

## Files Changed

| File | Change |
|------|--------|
| `src/prompts/system/doc_gen.md` | Add Pre-check section (~15 lines) + one-line addition to Task 1 step 4 |
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

## Manual Testing Scenarios

After implementation, verify these end-to-end flows:

1. **Short name, single match, no existing docs**: User says "生成 BuyResource 的文档" → agent calls `find_function`, finds one match, calls `list_documents`, finds no existing doc, proceeds to Task 1
2. **Short name, multiple matches**: User says "生成 BuyResource 的文档" → agent calls `find_function`, finds 2+ matches, presents options, user picks one, flow re-enters and resolves
3. **Short name, existing doc found**: User says "生成 BuyResource 的文档" → agent resolves target, calls `list_documents`, finds existing doc, asks user → user chooses view/regenerate/cancel
4. **Full path, existing doc found**: User provides full path → agent skips `find_function`, checks `list_documents`, finds existing doc, asks user
5. **Short name, no match**: User says "生成 FooBar 的文档" → agent calls `find_function`, gets no results, informs user
