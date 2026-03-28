# Generalize doc_gen Node Design

**Date:** 2026-03-28
**Status:** Draft
**Approach:** Option A — Config-driven + Prompt template conditionals

## Problem

The `doc_gen` node is hardcoded for API documentation generation. The project also has cron task handlers and message subscription handlers that need documentation. The node should generalize to handle all three types, generating processing logic documentation for any handler file.

## Key Decisions

- `doc_gen` remains a single node with a single intent — no graph topology changes
- Handler type (`api`, `cron`, `mq`) is declared in `.doc_gen.yaml` config, not inferred from code
- `search_rules` stays unchanged — within one project, code style is consistent
- `doc_gen` only generates per-handler logic docs; higher-level aggregation (trigger conditions, event subscriptions) will be handled by future nodes
- Database schema (`t_api_index`) is not changed in this iteration

## Design

### 1. Config Structure Change (`.doc_gen.yaml`)

`modules.mapping` values change from plain strings to objects with `name` and `type`:

**Before:**
```yaml
modules:
  mapping:
    "proj/api-service/logic": "order"
```

**After:**
```yaml
modules:
  mapping:
    "proj/api-service/logic":
      name: "order"
      type: "api"
    "proj/cron-service/handler":
      name: "billing-sync"
      type: "cron"
    "proj/mq-consumer/handler":
      name: "event-processor"
      type: "mq"
```

**Backward compatibility:** If a mapping value is a plain string, treat it as `{name: <string>, type: "api"}`.

**Supported types:**
- `api` — HTTP API handler (default). Full document template including request/response params, curl examples
- `cron` — Scheduled task handler. Processing logic only, no request/response sections
- `mq` — Message subscription handler. Processing logic only, no request/response sections

`search_rules` is unchanged:
```yaml
search_rules:
  function_patterns:
    - 'http\.HandlerFunc\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)'
  struct_patterns:
    - '^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s+struct\s*\{'
```

### 2. Pydantic Model Changes (`src/tools/config_reader.py`)

Add a `ModuleEntry` model:

```python
class ModuleEntry(BaseModel):
    name: str
    type: str = "api"  # "api" | "cron" | "mq"
```

Update `ModulesConfig.mapping` type from `dict[str, str]` to `dict[str, ModuleEntry]`.

Add a Pydantic validator on `ModulesConfig` that normalizes plain string values to `ModuleEntry(name=value, type="api")` for backward compatibility.

### 3. Prompt Changes (`src/prompts/system/doc_gen.md`)

This is the primary change. The 234-line prompt is restructured:

#### 3a. Role Description — Generalized

**Before:** "A professional Go API documentation generation assistant"
**After:** "A professional Go code documentation generation assistant"

The responsibilities and constraints are generalized: "Analyze Go source code, extract handler logic, generate structured Markdown documentation."

#### 3b. Step 3 (Determine Module) — Extract Type

After longest-prefix-match determines the module, the LLM also extracts the `type` field from the matched mapping entry. This type is carried forward to step 7.

#### 3c. Step 7 (Generate Document) — Conditional Template

The document template becomes type-aware:

**Common sections (all types):**
- Overview (概述)
- Execution Flow with Mermaid flowchart (执行流程)
- Error Codes table (错误码)
- Function Signature / Input Parameters (函数签名/输入参数)

**API-only sections (type = "api"):**
- Request Parameters table (请求参数)
- Response Parameters table (响应参数)
- Request Example in curl format (请求示例)
- Response Example (响应示例)

The prompt explicitly states: "If type is `cron` or `mq`, skip the API-specific sections."

#### 3d. Other Steps — Unchanged

Steps 1, 2, 4, 5, 6, 8, 9 remain unchanged. The recursive code reading (step 6) and file writing (step 8) are already generic.

### 4. Template Update (`template/.doc_gen.yaml`)

Update the example template to demonstrate the new mapping format with type fields.

### 5. Test Updates

- `tests/` — Update config_reader tests to cover new `ModuleEntry` model, both new format and backward-compatible string format

## Files Changed

| File | Change |
|------|--------|
| `src/tools/config_reader.py` | Add `ModuleEntry` model, update `ModulesConfig.mapping` type, add backward-compat validator |
| `src/prompts/system/doc_gen.md` | Generalize role/constraints, add type extraction in step 3, conditional template in step 7 |
| `template/.doc_gen.yaml` | Update example to show new mapping format |
| Tests for config_reader | Cover new format + backward compatibility |

## Files NOT Changed

| File | Reason |
|------|--------|
| `src/graph/graph.py` | Graph topology unchanged |
| `src/graph/nodes.py` | Node function unchanged; type handling is in prompt |
| `src/prompts/system/intent.md` | Intent stays as single `doc_gen` |
| `src/tools/*.py` (other tools) | Tool interfaces unchanged |
| `schema/api_index.sql` | DB schema not changed this iteration |

## Out of Scope

- Higher-level documentation aggregation (trigger conditions, event subscriptions) — future nodes
- Database schema changes to record handler type
- New tools for cron/mq-specific code analysis
- Intent splitting into multiple types
