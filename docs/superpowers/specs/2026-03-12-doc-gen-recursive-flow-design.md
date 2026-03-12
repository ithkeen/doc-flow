# doc_gen Prompt: Recursive Context Building & Execution Flow

**Date:** 2026-03-12
**Status:** Approved

## Problem

The current doc_gen system prompt (v2, from 2026-03-11) has two shortcomings:

1. **Task 1 (Deep Reading) is a passive checklist.** It lists what to read (structs, helpers, sub-functions) but doesn't give the LLM a systematic exploration strategy. The LLM may stop reading prematurely, missing deeply nested dependencies or cross-package references.

2. **No execution flow documentation.** The generated docs describe parameters, responses, and error codes in isolation, but don't show how the API actually executes—the step-by-step path from request to response, including where each error can occur. This makes it hard to understand the relationship between steps, conditions, and errors.

## Solution

### Workflow Change: 3-Task → 4-Task

```
Old: Task 1 Deep Reading → Task 2 Generate Docs → Task 3 Save
New: Task 1 Recursive Context Building → Task 2 Execution Flow Analysis → Task 3 Generate Documentation → Task 4 Save
```

### Task 1: Recursive Context Building

Replace the passive checklist with an explicit queue-driven exploration loop:

- Maintain **Resolved** (fully read) and **Unresolved** (discovered but not yet read) lists
- Loop: read a file → extract references → add new ones to Unresolved → pick next → repeat until Unresolved is empty
- Track 6 reference types: request/response structs (including nested), business logic functions/helpers, custom error types/constants, middleware/interceptors, interfaces and implementations
- Termination: LLM must be able to answer 3 verification questions (all struct fields, all error paths, core logic flow)

### Task 2: Execution Flow Analysis (New)

A pure analysis step between reading and writing. The LLM produces a structured text analysis:

- **Happy Path:** step-by-step from request entry to successful response, noting which function/method each step calls
- **Branches & Error Exits:** for each step, list all failure conditions with their error codes, HTTP status codes, and error messages
- Completion: every step in the main flow is listed, every error exit for every step is covered

This is an intermediate "thinking" output, not directly included in the final document. It feeds Task 3.

### Task 3: Generate Documentation (Modified)

Added responsibility: convert Task 2's analysis into a Mermaid flowchart:

- Main path: rectangle nodes `[step description]`
- Decisions/branches: diamond nodes `{condition}`
- Error exits: rounded nodes `(error_code: description)`
- Success path flows top-down; error branches go left or right
- Error codes in the flowchart must match the Error Codes table exactly

### Task 4: Save (Unchanged)

Same as current Task 3.

## Documentation Template Change

New section **Execution Flow** added between Response and Error Codes:

```
# API Name
## Overview
## Request Parameters
## Response
## Execution Flow          ← NEW
## Error Codes
## Request Example
## Response Example
```

The Execution Flow section contains a Mermaid `flowchart TD` diagram showing all steps and error branches.

### Quality Rules Added

- Execution Flow Mermaid diagram must cover all steps and error branches identified in Task 2
- Error codes in the flowchart must be consistent with the Error Codes table
- Use `flowchart TD` (top-down) direction

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Reading strategy | Explicit queue (Resolved/Unresolved) | More systematic than natural language guidance; clear termination condition prevents premature stopping |
| Flow analysis timing | Separate Task 2 after reading, before writing | Pure analysis step (like chain-of-thought) produces higher quality than analyzing while reading or while formatting |
| Flow visualization | Mermaid flowchart | Rich enough to show branches and error exits; widely rendered in Markdown viewers |
| Execution Flow position | Between Response and Error Codes | Flow branches correspond to error codes below; reading them together is natural |
| Task 2 output format | Free-form text analysis | Letting LLM focus on logic completeness without worrying about Mermaid syntax during analysis |

## What Doesn't Change

- Role description and constraints (exported functions only, no fabrication, inferred marking)
- Request Parameters, Response, Error Codes table formats
- Request/Response example formats (curl + JSON)
- Existing quality rules (exact Go types, validation tags, nested struct handling)
- Save behavior (module name inference, `save_document` tool)
