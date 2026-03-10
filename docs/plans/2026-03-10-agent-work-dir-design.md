# AGENT_WORK_DIR Design

## Summary

Add an `AGENT_WORK_DIR` environment variable to configure the agent's working directory. All tools (scan_directory, read_file, git_diff) will resolve paths relative to this directory. Document output remains independently controlled by `DOCS_OUTPUT_DIR`. Also fixes the existing disconnect where `doc_storage.py` hardcodes `DOCS_BASE_DIR = "docs"` instead of using `settings.docs_output_dir`.

## Approach: Settings Singleton + Tool-Layer Path Resolution (方案 A)

Tools read `settings.agent_work_dir` and prepend it to user/LLM-supplied paths. LLM continues to pass relative paths — completely unaware of the base directory.

## Changes

### 1. Config Layer

**`src/config/settings.py`** — `Settings` class:
```python
agent_work_dir: str = "."
```
- Env var: `AGENT_WORK_DIR` (no prefix, same level as `DOCS_OUTPUT_DIR`)
- Default `"."` — backward compatible

**`.env.example`** — add:
```
AGENT_WORK_DIR=.
```

### 2. Tools Layer

**`src/tools/code_scanner.py`** — `scan_directory`:
```python
path = Path(settings.agent_work_dir) / directory_path
```

**`src/tools/file_reader.py`** — `read_file`:
```python
path = Path(settings.agent_work_dir) / file_path
```

**`src/tools/git_ops.py`** — `git_diff`:
```python
repo = Path(settings.agent_work_dir) / repo_path
```

**`src/tools/doc_storage.py`** — fix `DOCS_BASE_DIR` disconnect:
- Remove module-level `DOCS_BASE_DIR = "docs"` constant
- `_get_doc_path` and `list_documents` read from `settings.docs_output_dir`
- Does NOT use `agent_work_dir` — document output location is independent

### 3. Tests

**Delete** all existing files in `tests/tools/`:
- `test_code_scanner_logging.py`
- `test_doc_storage_logging.py`
- `test_file_reader_logging.py`
- `test_git_ops_logging.py`

**`tests/config/test_settings.py`** — add:
- Test `AGENT_WORK_DIR` env var loads correctly
- Test default value is `"."`

**New `tests/tools/` tests** — written after implementation, using `monkeypatch` on `settings.agent_work_dir` / `settings.docs_output_dir` with `tmp_path` for filesystem isolation.

## Files Affected

| File | Action |
|---|---|
| `src/config/settings.py` | Add `agent_work_dir` field |
| `.env.example` | Add `AGENT_WORK_DIR` |
| `src/tools/code_scanner.py` | Import settings, prepend `agent_work_dir` |
| `src/tools/file_reader.py` | Import settings, prepend `agent_work_dir` |
| `src/tools/git_ops.py` | Import settings, prepend `agent_work_dir` |
| `src/tools/doc_storage.py` | Remove `DOCS_BASE_DIR`, use `settings.docs_output_dir` |
| `tests/tools/test_*` | Delete 4 files, rewrite after implementation |
| `tests/config/test_settings.py` | Add `AGENT_WORK_DIR` tests |
