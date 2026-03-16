# 移除 doc_gen 节点设计文档

**日期**: 2026-03-16
**状态**: 设计阶段
**作者**: Claude (brainstorming with user)

## 背景

`src/generator` 模块已实现批量 API 文档生成功能，通过 CLI 命令 `uv run python -m src.generator` 控制文档生成。现在需要将 API 文档变为只读，不再允许用户通过 Chainlit 聊天 UI 主动生成文档。因此需要从 LangGraph StateGraph 中移除 `doc_gen` 节点。

## 目标

1. 完全移除 `doc_gen` 节点及其相关代码
2. 保持 `doc_qa` 节点功能不变（本次不调整，用户后续自行调整）
3. 清理无用的 State 字段（`params`、`confidence`）
4. 保留 `doc_gen_llm` 配置（`src/generator/graph.py` 仍在使用）
5. 保留所有 tool 源文件（`doc_qa` 和 `generator` 仍在使用）
6. 更新用户界面提示，引导用户使用 CLI 工具或文档问答

## 用户交互变化

**之前**: 用户在 Chainlit 中说「帮我生成 handler.go 的文档」→ intent 识别为 `doc_gen` → 调用 6 个工具扫描代码并生成文档

**之后**: 用户在 Chainlit 中说「帮我生成 handler.go 的文档」→ intent 识别为 `doc_qa` 或 `chat` → 系统引导用户使用 CLI 工具，或查询已有文档

## 方案选择

**方案 A（采用）**: 干净移除，删除所有 doc_gen 相关代码和文件，不留死代码
**方案 B（不采用）**: 最小移除，仅从图中摘除节点，其余代码留在原地（会留下大量死代码）

## 详细设计

### 1. Graph 层改动 (`src/graph/graph.py`)

**移除内容**:
- 导入: `doc_gen`, `route_doc_gen`, `TOOLS`
- 导入: `ToolNode`（如果 `qa_tools` 也用则保留）
- 节点注册: `graph.add_node("doc_gen", doc_gen)`
- 节点注册: `graph.add_node("tools", ToolNode(tools=TOOLS))`
- 条件边: `graph.add_conditional_edges("doc_gen", route_doc_gen, ["tools", "__end__"])`
- 边: `graph.add_edge("tools", "doc_gen")`

**修改内容**:
- `route_by_intent` 的条件边列表: `["doc_gen", "doc_qa", "chat", "__end__"]` → `["doc_qa", "chat", "__end__"]`

**改动后图结构**:
```
START -> intent_recognize -> [route_by_intent] -+-> doc_qa -> [route_doc_qa] -> qa_tools -> doc_qa
                                                |                     |
                                                |                     +-> END
                                                +-> chat -> END
                                                +-> END (unknown)
```

### 2. Nodes 层改动 (`src/graph/nodes.py`)

**删除内容**:
- `INTENT_LIST = "doc_gen, doc_qa, chat"` 常量（无人使用）
- `TOOLS` 列表（6 个工具: `scan_directory`, `read_file`, `save_document`, `read_document`, `list_documents`, `find_function`）
- `doc_gen` 异步函数（约 18 行）
- `route_doc_gen` 函数（约 6 行）
- 工具导入: `scan_directory`, `read_file`, `save_document`, `find_function`（保留 `read_document`, `list_documents` 给 `QA_TOOLS`）

**修改内容**:
- `route_by_intent`: 移除 `if state["intent"] == "doc_gen": return "doc_gen"` 分支

**State 定义改动**:
```python
# 之前
class State(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str
    confidence: float  # 从未被路由逻辑使用
    params: dict       # 仅 doc_gen 读取

# 之后
class State(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str
```

**`intent_recognize` 函数改动**:
- 解析 LLM JSON 响应时，不再提取 `confidence` 和 `params`
- 返回值简化: `{"messages": ..., "intent": ..., "confidence": ..., "params": ...}` → `{"messages": ..., "intent": ...}`

### 3. Prompt 文件改动

**删除文件**:
- `src/prompts/system/doc_gen.md`
- `src/prompts/user/doc_gen.md`

**修改文件**:
- `src/prompts/system/intent.md`: 仅删除 `doc_gen` 意图那一行（不修改 doc_qa 描述）
- `src/prompts/system/chat.md`: 移除「为 Go 源码文件生成 API 文档」能力描述，改为引导用户使用 CLI 工具或文档问答

### 4. UI 层改动 (`app.py`)

**流过滤** (line 61):
```python
# 之前
and metadata["langgraph_node"] in ("doc_gen", "doc_qa", "chat")

# 之后
and metadata["langgraph_node"] in ("doc_qa", "chat")
```

**欢迎消息** (line 28):
```python
# 之前
content="你好！我是 doc-flow，你可以让我为 Go 源码文件生成 API 文档，或者基于已有文档提问。"

# 之后
content="你好！我是 doc-flow，你可以基于已有文档提问，或者和我自由聊天。"
```

**兜底消息** (line 69):
```python
# 之前
answer.content = "抱歉，我暂时无法理解你的意思。你可以让我进行文档生成、文档问答，也可以和我自由聊天。"

# 之后
answer.content = "抱歉，我暂时无法理解你的意思。你可以让我进行文档问答，也可以和我自由聊天。"
```

### 5. 文档改动 (`CLAUDE.md`)

**更新内容**:
- 图结构图: 移除 doc_gen 分支和 tools 节点
- 节点说明: 移除 `doc_gen` 和 `route_doc_gen` 描述
- State 字段说明: 移除 `params` 和 `confidence` 字段
- `TOOLS` 列表说明: 说明已移除，仅保留 `QA_TOOLS`
- 保留 `doc_gen_llm` 配置说明（注明 `src/generator/graph.py` 仍在使用）

### 6. 保留项（不删除）

**配置文件**:
- `src/config/settings.py`: `doc_gen_llm` 字段（line 94, 111-112）
- `src/config/llm.py`: `_NODE_LLM_ATTR` 中的 `"doc_gen": "doc_gen_llm"` 映射（line 14）
- `.env.example`: `# DOC_GEN_LLM_MODEL=gpt-4` 注释（line 25）

**Tool 源文件**（全部保留，因为 `doc_qa` 或 `generator` 仍在使用）:
- `src/tools/code_scanner.py` (`scan_directory` - generator 不用，但保留备用)
- `src/tools/file_reader.py` (`read_file` - generator 使用)
- `src/tools/doc_storage.py` (`save_document`, `read_document`, `list_documents` - generator 和 doc_qa 使用)
- `src/tools/code_search.py` (`find_function` - generator 使用)

**测试文件**:
- `tests/test_llm.py`: 使用 `"doc_gen"` 作为测试节点名，但测试的是 LLM 工厂，不是 doc_gen 节点本身，保持不变

## 影响范围

**修改文件** (8 个):
1. `src/graph/graph.py` - 移除节点和边
2. `src/graph/nodes.py` - 移除函数、常量、State 字段
3. `src/prompts/system/intent.md` - 删除 doc_gen 意图
4. `src/prompts/system/chat.md` - 更新能力描述
5. `app.py` - 更新流过滤和消息
6. `CLAUDE.md` - 更新架构文档
7. `src/graph/__init__.py` - 更新模块 docstring

**删除文件** (2 个):
8. `src/prompts/system/doc_gen.md`
9. `src/prompts/user/doc_gen.md`

**不修改文件**:
- 所有 tool 源文件
- 所有配置文件
- 所有测试文件
- `src/generator/` 下所有文件

## 风险评估

**低风险**:
- 所有改动都是删除或简单修改，无复杂逻辑变更
- `doc_qa` 节点完全独立，不受影响
- `generator` 模块使用独立的 graph，不受影响
- 无现有测试覆盖 `build_graph()` 或 `doc_gen` 节点，无测试破坏风险

**潜在问题**:
- 用户习惯了在 Chainlit 中生成文档，需要通过 UI 提示引导到 CLI 工具
- Intent 识别可能将文档生成请求误判为 `chat` 而非 `doc_qa`（用户后续会调整 doc_qa）

## 验证方法

1. 启动 LangGraph dev server: `uv run langgraph dev`，检查图编译无错误
2. 启动 Chainlit UI: `uv run chainlit run app.py -w`，测试以下场景:
   - 发送「帮我生成 handler.go 的文档」，验证不会触发 doc_gen
   - 发送「查询 handler.go 的文档」，验证 doc_qa 正常工作
   - 发送「你好」，验证 chat 正常工作
3. 运行测试: `uv run pytest`，确保所有测试通过
4. 运行 generator: `uv run python -m src.generator --project <name>`，确保批量生成仍正常工作

## 后续工作

用户后续会自行调整 `doc_qa` 节点，使其能够:
1. 识别文档生成请求
2. 先查询已有文档
3. 如果文档不存在，提示用户「文档系统正在建设中」

---

**设计完成，等待用户审核。**
