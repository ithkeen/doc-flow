# Doc Gen Pre-check Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable the doc_gen agent to accept short function names (e.g., `BuyResource`) instead of full file paths, and detect existing documentation before regenerating.

**Architecture:** Pure prompt-driven approach with one tool enhancement. Modify `find_function` to return all matches (enabling multi-match disambiguation), update the `doc_gen` system prompt with a Pre-check phase, and adjust the user prompt wording.

**Tech Stack:** Python, LangChain tools, LangGraph prompts

---

## Chunk 1: find_function Enhancement

### Task 1: Enhance find_function to Return All Matches

**Files:**
- Modify: `src/tools/code_search.py:18-72`
- Test: `tests/tools/test_code_search.py`

- [ ] **Step 1: Write the failing test for multiple matches**

Add to `tests/tools/test_code_search.py`:

```python
def test_returns_all_matches_across_files(self, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

    pkg_a = tmp_path / "pkg_a"
    pkg_a.mkdir()
    (pkg_a / "handler.go").write_text(
        "package pkg_a\n\nfunc BuyResource(ctx context.Context) error {\n\treturn nil\n}\n"
    )

    pkg_b = tmp_path / "pkg_b"
    pkg_b.mkdir()
    (pkg_b / "handler.go").write_text(
        "package pkg_b\n\nfunc BuyResource(ctx context.Context) error {\n\treturn nil\n}\n"
    )

    result = json.loads(find_function.invoke({"function_name": "BuyResource"}))
    assert result["success"] is True
    assert isinstance(result["payload"], list)
    assert len(result["payload"]) == 2
    files = {m["file"] for m in result["payload"]}
    assert any("pkg_a" in f for f in files)
    assert any("pkg_b" in f for f in files)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_code_search.py::TestFindFunction::test_returns_all_matches_across_files -v`

Expected: FAIL — current `find_function` returns a dict payload (not a list), and stops at first match.

- [ ] **Step 3: Update existing tests to expect list payload**

Update all existing tests in `tests/tools/test_code_search.py` that assert on `result["payload"]` as a dict. Change them to expect a list with one element. The tests to update:

In `test_finds_plain_function`, change:
```python
assert result["payload"]["file"].endswith("service/buy.go")
assert result["payload"]["line"] == 3
assert "buyResourcePostPaid" in result["payload"]["content"]
```
to:
```python
assert isinstance(result["payload"], list)
assert len(result["payload"]) == 1
assert result["payload"][0]["file"].endswith("service/buy.go")
assert result["payload"][0]["line"] == 3
assert "buyResourcePostPaid" in result["payload"][0]["content"]
```

In `test_finds_method_with_receiver`, change:
```python
assert result["payload"]["line"] == 3
assert "ProcessOrder" in result["payload"]["content"]
```
to:
```python
assert isinstance(result["payload"], list)
assert len(result["payload"]) == 1
assert result["payload"][0]["line"] == 3
assert "ProcessOrder" in result["payload"][0]["content"]
```

In `test_handles_non_utf8_file`, change:
```python
assert result["payload"]["line"] == 3
```
to:
```python
assert isinstance(result["payload"], list)
assert len(result["payload"]) == 1
assert result["payload"][0]["line"] == 3
```

- [ ] **Step 4: Run all tests to verify they fail**

Run: `uv run pytest tests/tools/test_code_search.py -v`

Expected: The 3 updated tests and the new multi-match test FAIL. The other tests (not found, directory errors, etc.) still PASS.

- [ ] **Step 5: Implement find_function changes**

In `src/tools/code_search.py`, make these changes:

1. Update docstring `Returns` line (line 30) from:
```
        JSON envelope，payload 包含 file（文件路径）、line（行号）、content（该行内容）。
```
to:
```
        JSON envelope，payload 为匹配列表，每个元素包含 file（文件路径）、line（行号）、content（该行内容）。
```

2. Replace the scanning loop (lines 52-69) — remove early return, collect all matches:

Replace:
```python
    for go_file in go_files:
        try:
            content = go_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = go_file.read_text(encoding="latin-1")
            except Exception as e:
                logger.warning("文件 %s 读取失败，已跳过：%s", go_file, e)
                continue

        for line_num, line in enumerate(content.splitlines(), 1):
            if pattern.match(line):
                rel_path = str(go_file.relative_to(Path(settings.agent_work_dir)))
                logger.info("找到函数 %s 定义：%s:%d", function_name, rel_path, line_num)
                return ok(
                    "找到函数定义",
                    payload={"file": rel_path, "line": line_num, "content": line.strip()},
                )

    logger.info("未找到函数 %s 的定义", function_name)
    return fail(f"未找到函数 {function_name} 的定义")
```

With:
```python
    matches = []

    for go_file in go_files:
        try:
            content = go_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = go_file.read_text(encoding="latin-1")
            except Exception as e:
                logger.warning("文件 %s 读取失败，已跳过：%s", go_file, e)
                continue

        for line_num, line in enumerate(content.splitlines(), 1):
            if pattern.match(line):
                rel_path = str(go_file.relative_to(Path(settings.agent_work_dir)))
                logger.info("找到函数 %s 定义：%s:%d", function_name, rel_path, line_num)
                matches.append({"file": rel_path, "line": line_num, "content": line.strip()})

    if not matches:
        logger.info("未找到函数 %s 的定义", function_name)
        return fail(f"未找到函数 {function_name} 的定义")

    logger.info("找到函数 %s 共 %d 处定义", function_name, len(matches))
    return ok(f"找到 {len(matches)} 处函数定义", payload=matches)
```

- [ ] **Step 6: Run all tests to verify they pass**

Run: `uv run pytest tests/tools/test_code_search.py -v`

Expected: All tests PASS (including the new multi-match test).

- [ ] **Step 7: Commit**

```bash
git add src/tools/code_search.py tests/tools/test_code_search.py
git commit -m "feat: find_function returns all matches instead of first only"
```

---

## Chunk 2: Prompt Changes

### Task 2: Update doc_gen Prompts

**Files:**
- Modify: `src/prompts/system/doc_gen.md:13-15` (insert Pre-check before Task 1)
- Modify: `src/prompts/system/doc_gen.md:27` (add multi-match note to Task 1 step 4)
- Modify: `src/prompts/user/doc_gen.md:1` (change one word)

- [ ] **Step 1: Add Pre-check section to system prompt**

In `src/prompts/system/doc_gen.md`, insert the following block between line 15 (`The user will specify the file(s) to document. Follow these four tasks in order:`) and line 17 (`### Task 1: Recursive Context Building`):

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
- Use `list_documents` (without specifying a module name) to get a full listing of all existing documentation
- Search the returned document names for the target API name (best-effort name matching — the saved document name may not exactly match the function name)
- If a likely match is found, inform the user and ask how to proceed:
  - 查看现有文档
  - 重新生成并覆盖
  - 取消
- Only proceed to Task 1 if the user confirms generation/regeneration, or if no existing documentation is found

```

- [ ] **Step 2: Add multi-match note to Task 1 step 4**

In `src/prompts/system/doc_gen.md`, find Task 1 step 4 (the line starting with `4. Use \`find_function\``). Append the following sentence to the end of that line:

```
 When `find_function` returns multiple matches, prefer the match in the same package or directory as the calling code.
```

So the full line becomes:
```
4. Use `find_function` to locate the file containing the next Unresolved function or method. Only fall back to `scan_directory` for non-function references (e.g., struct types, constants). When `find_function` returns multiple matches, prefer the match in the same package or directory as the calling code.
```

- [ ] **Step 3: Update user prompt wording**

In `src/prompts/user/doc_gen.md`, change:
```
请为以下文件生成接口文档：{file_path}
```
to:
```
请为以下目标生成接口文档：{file_path}
```

- [ ] **Step 4: Verify prompt loading still works**

Run: `uv run pytest tests/ -v`

Expected: All tests PASS. No prompt loading errors.

- [ ] **Step 5: Commit**

```bash
git add src/prompts/system/doc_gen.md src/prompts/user/doc_gen.md
git commit -m "feat: add pre-check phase to doc_gen prompt for target resolution and duplicate detection"
```

---

## Chunk 3: Update CLAUDE.md

### Task 3: Update CLAUDE.md Documentation

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update CLAUDE.md**

In the `find_function` description under **Key patterns**, update the sentence about return behavior. Change:
```
`find_function` searches Go function definitions by regex-matching `func <name>(` patterns. Returns only the first match (file path, line number, content).
```
to:
```
`find_function` searches Go function definitions by regex-matching `func <name>(` patterns. Returns all matches as a list (each with file path, line number, content).
```

Also add a note about the Pre-check phase. After the bullet about `doc_gen` loading the `"doc_gen"` prompt in the **Graph orchestration** section, or wherever the `doc_gen` prompt behavior is described, add:
```
The `doc_gen` system prompt includes a Pre-check phase that resolves short function names via `find_function` and checks for existing docs via `list_documents` before starting the 4-task workflow.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with find_function multi-match and pre-check phase"
```
