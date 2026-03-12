# doc_qa — 基于文档的问答功能设计

## 概述

为 doc-flow agent 新增 `doc_qa` 意图，支持用户基于已生成的 API 文档进行单文档问答。采用与 `doc_gen` 相同的 ReAct 工具调用模式，复用已有的 `read_document` 和 `list_documents` 工具函数。

## 需求

- **场景**：用户针对某个已生成的 API 文档提问，如「CreateUser 接口的请求参数有哪些？」「这个接口返回哪些错误码？」
- **前提**：文档已预先生成，问答基于已有文档
- **交互**：单轮对话，无会话记忆，与当前架构保持一致
- **工具**：使用 ReAct 循环调用工具读取文档，LLM 基于文档内容生成回答

## 图结构

```
START -> intent_recognize -> [route_by_intent] -> doc_gen -> [route_doc_gen] -> tools    -> doc_gen
                                    |
                                    +-----------> doc_qa  -> [route_doc_qa] -> qa_tools  -> doc_qa
                                    |
                                    +-----------> END (unknown intent)
```

`doc_qa` 拥有独立的 `qa_tools` ToolNode，与 `doc_gen` 的 ReAct 循环互不干扰。两个 ToolNode 实例包装不同的工具子集，但底层工具函数完全复用。

## 组件设计

### 1. 工具子集

```python
# src/graph/nodes.py
QA_TOOLS = [read_document, list_documents]
```

从已有工具中选取 `read_document` 和 `list_documents`，不引入任何新工具代码。

### 2. `doc_qa` 节点

```python
async def doc_qa(state: State, config: RunnableConfig) -> dict:
    prompt = load_prompt("doc_qa")
    user_input = state["messages"][-1].content

    system_messages = prompt.format_messages(user_input=user_input)

    llm = ChatOpenAI(
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
        model=settings.llm.model,
    )
    llm_with_tools = llm.bind_tools(QA_TOOLS)

    all_messages = system_messages + state["messages"]
    response = await llm_with_tools.ainvoke(all_messages, config=config)

    logger.info("文档问答节点调用完成")
    return {"messages": [response]}
```

与 `doc_gen` 结构一致：
1. 调用 `load_prompt("doc_qa")` 加载专用 prompt，传入 `user_input` 模板变量
2. 使用 `system_messages + state["messages"]` 拼接消息列表（system prompt 在前，会话消息在后，确保 ReAct 循环的工具调用/响应消息被保留）
3. 使用 `ChatOpenAI` 并绑定 `QA_TOOLS`
4. 通过 `ainvoke` 异步调用 LLM
5. 记录日志并返回 `{"messages": [response]}`

### 3. `route_doc_qa` 条件路由

```python
def route_doc_qa(state: State) -> str:
```

逻辑与 `route_doc_gen` 完全一致：AI 消息包含 `tool_calls` 时路由到 `"qa_tools"`，否则路由到 `END`。

### 4. `route_by_intent` 扩展

需要两处独立的变更：

**（a）`nodes.py` — 扩展意图列表和路由函数：**

```python
INTENT_LIST = "doc_gen, doc_qa"
```

`route_by_intent` 增加 `"doc_qa"` 分支：
- `intent == "doc_gen"` → `doc_gen` 节点
- `intent == "doc_qa"` → `doc_qa` 节点
- 其他 → `END`

**（b）`src/prompts/system/intent.md` — 增加意图描述：**

在意图列表的描述中补充 `doc_qa` 的说明，让 LLM 能准确区分两种意图。具体做法是在 `intent.md` 中将 `{intent_list}` 周围的文本扩展为带描述的列表格式：

```
可用意图：
- doc_gen：用户要求为某个文件或模块生成 API 文档
- doc_qa：用户基于已有文档提问（查询接口参数、用法、错误码等）
```

这两处变更是互补的：`INTENT_LIST` 用于代码内的路由判断，`intent.md` 的描述用于 LLM 的意图分类。

### 5. `graph.py` 变更

更新 import 语句，新增节点和边：

```python
# import 新增
from src.graph.nodes import (
    TOOLS,
    QA_TOOLS,        # 新增
    State,
    doc_gen,
    doc_qa,           # 新增
    intent_recognize,
    route_by_intent,
    route_doc_gen,
    route_doc_qa,     # 新增
)

# 新增节点
graph.add_node("doc_qa", doc_qa)
graph.add_node("qa_tools", ToolNode(QA_TOOLS))

# 新增边（使用与现有代码一致的 list 语法）
graph.add_conditional_edges("doc_qa", route_doc_qa, ["qa_tools", "__end__"])
graph.add_edge("qa_tools", "doc_qa")

# route_by_intent 扩展（原 list 中追加 "doc_qa"）
graph.add_conditional_edges("intent_recognize", route_by_intent, ["doc_gen", "doc_qa", "__end__"])
```

### 6. State

无变更。现有的 `messages`、`intent`、`confidence`、`params` 字段足以支持 `doc_qa`。

## Prompt 设计

### 系统 Prompt (`src/prompts/system/doc_qa.md`)

角色定义：基于已生成 API 文档的问答助手。

工作流程：
1. 分析用户问题，判断需要查找哪个模块/接口的文档
2. 如果不确定目标文档，先使用 `list_documents` 查看可用文档列表
3. 使用 `read_document` 读取目标文档内容
4. 基于文档内容准确回答用户问题

约束：
- 只能基于文档内容回答，不得编造信息
- 如果文档中找不到答案，明确告知用户
- 回答使用中文

### 用户 Prompt (`src/prompts/user/doc_qa.md`)

```
用户问题：{user_input}
```

### 意图识别 Prompt 调整

见组件设计第 4 节（`route_by_intent` 扩展 b 部分）。

## Chainlit UI 适配 (`app.py`)

### 欢迎消息

`on_chat_start` 中的欢迎消息需要更新以反映新增的问答能力。

### 流式输出

```python
# 当前：只输出 doc_gen 节点
if metadata["langgraph_node"] == "doc_gen"

# 改为：同时支持 doc_gen 和 doc_qa
if metadata["langgraph_node"] in ("doc_gen", "doc_qa")
```

### Fallback 消息

当意图无法识别时，更新 fallback 消息：

```python
# 当前
"抱歉，我目前只支持文档生成功能。请告诉我你想为哪个目录生成文档。"

# 改为
"抱歉，我目前支持文档生成和文档问答功能。你可以让我为某个文件生成文档，或者基于已有文档提问。"
```

注意：`tests/test_app.py` 中有 fallback 消息的断言，需要同步更新。

## 测试策略

沿用现有测试模式（mock LLM、`tmp_path` 文件隔离、`@pytest.mark.asyncio`）。

### `tests/graph/test_nodes.py` 新增

- `test_doc_qa_node`：mock ChatOpenAI，验证 `doc_qa` 正确加载 prompt、绑定 `QA_TOOLS`、返回 AI 消息
- `test_route_doc_qa_with_tool_calls`：验证有 tool_calls 时返回 `"qa_tools"`
- `test_route_doc_qa_without_tool_calls`：验证无 tool_calls 时返回 `END`
- `test_route_by_intent_doc_qa`：验证 `intent == "doc_qa"` 时返回 `"doc_qa"`

### `tests/graph/test_graph.py` 新增

- 验证图中存在 `doc_qa` 和 `qa_tools` 节点
- 验证边的连接关系正确

### `tests/test_app.py` 扩展

- 验证 `doc_qa` 节点输出能被 Chainlit 正确流式展示

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `src/graph/nodes.py` | 修改 | 新增 `QA_TOOLS`、`doc_qa` 节点、`route_doc_qa`；扩展 `INTENT_LIST`、`route_by_intent` |
| `src/graph/graph.py` | 修改 | 新增 `qa_tools` 节点、`doc_qa` 节点、相关边和条件路由 |
| `src/prompts/system/doc_qa.md` | 新建 | doc_qa 系统 prompt |
| `src/prompts/user/doc_qa.md` | 新建 | doc_qa 用户 prompt |
| `src/prompts/system/intent.md` | 修改 | 意图列表描述中增加 `doc_qa` |
| `app.py` | 修改 | 流式输出支持 `doc_qa` 节点，更新 fallback 消息 |
| `tests/graph/test_nodes.py` | 修改 | 新增 doc_qa 相关测试 |
| `tests/graph/test_graph.py` | 修改 | 新增图结构验证 |
| `tests/test_app.py` | 修改 | 新增 doc_qa 流式输出测试，更新 fallback 消息断言 |

**不涉及变更的文件**：`src/tools/` 全部工具代码零改动，`src/config/` 无变更。
