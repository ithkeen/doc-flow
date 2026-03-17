# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

doc-flow is a LangGraph-based chatbot for API documentation Q&A and generation. It uses intent recognition to route user queries to specialized nodes: doc_qa (answer questions about docs), doc_gen (generate API docs with tools), or chat (general conversation).

## Architecture

**Graph Flow (src/graph/graph.py)**
- START → intent_recognize → route by intent → [doc_qa | doc_gen | chat] → END
- doc_gen forms a ReAct loop with doc_gen_tools (ToolNode with 8 tools)

**State Management (src/graph/nodes.py)**
- State: `messages` (conversation history) + `intent` (routing decision)
- Nodes: intent_recognize, doc_qa, doc_gen, chat
- Tools (DOC_GEN_TOOLS): load_docgen_config, match_api_name, query_api_index, read_file, find_function, find_struct, write_file, save_api_index

**Prompts (src/prompts/)**
- System/user prompts stored as markdown in src/prompts/system/ and src/prompts/user/
- Loaded via load_prompt() which returns ChatPromptTemplate

**LLM Configuration (src/config/llm.py)**
- get_llm(mode) returns configured LLM for each node type
- Settings loaded from environment via pydantic-settings

## Development Commands

**Run Chainlit UI:**
```bash
chainlit run app.py
```

**Run tests:**
```bash
pytest
```

**LangGraph Studio (if using):**
```bash
langgraph dev
```
The graph is defined in langgraph.json pointing to src/graph/graph.py:build_graph

## Key Files

- app.py: Chainlit entry point with streaming support
- src/graph/graph.py: Graph construction and compilation
- src/graph/nodes.py: Node functions, routing logic, and State definition
- src/tools/: LangChain Tool implementations for doc generation
- src/prompts/: Markdown-based prompt templates
- src/config/: LLM and settings configuration

## Environment

Requires .env file with LLM API keys (see .env.example). Python 3.11+.
