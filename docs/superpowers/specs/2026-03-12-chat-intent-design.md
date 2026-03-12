# chat — 通用聊天意图设计

## 概述

为 doc-flow agent 新增 `chat` 意图，作为 `doc_gen`（文档生成）和 `doc_qa`（文档问答）之外的兜底出口。当用户输入不属于文档生成或文档问答时，agent 以自由对话方式回应，同时通过 system prompt 柔和引导用户使用核心文档功能。

## 需求

- **场景**：用户发送与文档生成/问答无关的消息，如闲聊、问候、技术讨论、功能询问等
- **能力**：纯自由对话，不绑定任何工具
- **多轮**：利用 MemorySaver 已有的多轮对话能力，chat 节点传入完整对话历史
- **引导**：通过 system prompt 让 LLM 在回复中自然地提及文档生成和文档问答功能，不强制每条都提，而是在话题相关时柔和引出
- **切换**：每条消息仍经过 `intent_recognize`，当用户意图变为 `doc_gen` 或 `doc_qa` 时自动切换路由

## 图结构

```
START -> intent_recognize -> [route_by_intent] -> doc_gen -> [route_doc_gen] -> tools    -> doc_gen (ReAct)
                                    |                              |
                                    |                              +-> END
                                    |
                                    +-----------> doc_qa  -> [route_doc_qa] -> qa_tools  -> doc_qa (ReAct)
                                    |                              |
                                    |                              +-> END
                                    |
                                    +-----------> chat    -> END
                                    |
                                    +-----------> END (unknown — JSON 解析失败等极端情况)
```

`chat` 节点是最简单的路径：无工具、无 ReAct 循环、无条件路由，直接 `chat → END`。

## 组件设计

### 1. `chat` 节点

```python
async def chat(state: State, config: RunnableConfig) -> dict:
    prompt = load_prompt("chat")
    user_input = _get_last_human_message(state["messages"])

    system_messages = prompt.format_messages(user_input=user_input)

    llm = ChatOpenAI(
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
        model=settings.llm.model,
    )

    # 不绑定工具 — 纯对话
    all_messages = system_messages + state["messages"]
    response = await llm.ainvoke(all_messages, config=config)

    logger.info("聊天节点调用完成")
    return {"messages": [response]}
```

关键设计决策：
- **不调用 `.bind_tools()`** — 纯 LLM 对话，无工具调用能力
- **传入完整对话历史** — `system_messages + state["messages"]`，支持多轮上下文
- **接收 `RunnableConfig`** — 与 `doc_gen`/`doc_qa` 一致，保证 Chainlit 的 `LangchainCallbackHandler` 正常工作
- **使用 `_get_last_human_message`** — 获取最新用户输入作为 prompt 模板变量

### 2. `route_by_intent` 扩展

```python
def route_by_intent(state: State) -> str:
    if state["intent"] == "doc_gen":
        return "doc_gen"
    if state["intent"] == "doc_qa":
        return "doc_qa"
    if state["intent"] == "chat":
        return "chat"
    return END
```

与现有代码风格一致：使用直接 key 访问（`state["intent"]`）而非 `.get()`，因为 `State` 是 `TypedDict`，`intent` 字段在 `intent_recognize` 节点中总会被设置。保留 `→ END` 作为安全兜底（JSON 解析失败等场景），正常情况下 `chat` 会捕获所有非 doc 意图。

### 3. 意图识别 Prompt 扩展

**`src/prompts/system/intent.md`** 中增加 `chat` 意图描述：

```
可用意图：
- doc_gen：用户要求为某个文件或模块生成 API 文档
- doc_qa：用户基于已有文档提问（查询接口参数、用法、错误码等）
- chat：用户的输入不属于以上两种意图，是一般性对话、闲聊、问候、技术讨论或其他内容
```

`chat` 作为兜底意图，LLM 在无法归类为 `doc_gen` 或 `doc_qa` 时应分类为 `chat`。

### 4. `INTENT_LIST` 常量

```python
INTENT_LIST = "doc_gen, doc_qa, chat"
```

更新常量以反映完整的意图列表。注意：`INTENT_LIST` 当前在代码中仅作为声明性常量存在，未被任何函数或 prompt 模板引用。意图列表的实际定义在 `src/prompts/system/intent.md` 的 prompt 文本中。保留此常量是为了代码可读性和未来可能的引用。

### 5. `graph.py` 变更

```python
# import 新增
from src.graph.nodes import (
    TOOLS,
    QA_TOOLS,
    State,
    chat,            # 新增
    doc_gen,
    doc_qa,
    intent_recognize,
    route_by_intent,
    route_doc_gen,
    route_doc_qa,
)

# 新增节点
graph.add_node("chat", chat)

# 新增边
graph.add_edge("chat", END)

# route_by_intent 扩展出口列表
graph.add_conditional_edges(
    "intent_recognize",
    route_by_intent,
    ["doc_gen", "doc_qa", "chat", "__end__"]
)
```

### 6. State

无变更。现有的 `messages`、`intent`、`confidence`、`params` 字段完全满足 `chat` 节点需求。

## Prompt 设计

### 系统 Prompt (`src/prompts/system/chat.md`)

角色定位：代码文档助手的通用对话模式。

核心要素：
1. **身份**：你是一个专注于 Go 代码文档的 AI 助手，当前在与用户进行自由对话
2. **通用能力**：可以聊任何话题，友好、有帮助、专业
3. **引导策略**：在对话中适时自然地提及你的核心能力 — 为 Go 代码生成 API 文档（告诉你文件路径即可）、回答已有文档相关的问题。不是每条回复都要提，而是在话题相关或自然衔接时引出
4. **语言**：中文

### 用户 Prompt (`src/prompts/user/chat.md`)

```
用户输入：{user_input}
```

与其他 prompt 模板格式一致。

## Chainlit UI 适配 (`app.py`)

### 欢迎消息

欢迎消息有意不做更新。当前欢迎消息引导用户使用文档生成和文档问答功能，chat 作为兜底意图不需要显式提及——用户自然地发送任何消息即可触发。

### 流式输出

```python
# 当前
if metadata["langgraph_node"] in ("doc_gen", "doc_qa")

# 改为
if metadata["langgraph_node"] in ("doc_gen", "doc_qa", "chat")
```

### Fallback 消息

当 chat 节点兜住大部分非 doc 意图后，fallback 触发概率极低（仅 JSON 解析失败等）。保留现有 fallback 逻辑，但更新提示文案：

```python
# 改为
"抱歉，我暂时无法理解你的意思。你可以让我进行文档生成、文档问答，也可以和我自由聊天。"
```

注意保留 "文档生成" 和 "文档问答" 关键词，因为现有测试断言依赖这些关键词。

## 测试策略

沿用现有测试模式（mock LLM、`tmp_path` 文件隔离、`@pytest.mark.asyncio`）。

### `tests/graph/test_nodes.py` 新增

**`TestChat` 测试类：**
- `test_chat_returns_ai_response`：mock ChatOpenAI，验证 chat 节点返回 AI 消息
- `test_chat_does_not_bind_tools`：验证 LLM 没有调用 `.bind_tools()`
- `test_chat_loads_prompt`：验证加载了 `"chat"` prompt
- `test_chat_passes_message_history`：验证完整对话历史被传递给 LLM
- `test_chat_passes_config_to_ainvoke`：验证 `config` 被正确传递给 `llm.ainvoke()`（Chainlit callback 集成的关键）

**`TestRouteByIntent` 扩展：**
- `test_route_by_intent_chat`：验证 `intent == "chat"` 时返回 `"chat"`

### `tests/graph/test_graph.py` 更新

- 验证图中包含 `chat` 节点（使用成员检查 `assert "chat" in node_names`，与现有测试风格一致）

### `tests/test_app.py` 扩展

- 验证 `chat` 节点输出能被 Chainlit 正确流式展示
- 更新 fallback 消息断言（保留对 "文档生成"、"文档问答" 的断言，新增对 "聊天" 的断言）

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `src/graph/nodes.py` | 修改 | 新增 `chat` 节点函数；更新 `INTENT_LIST`（声明性）、扩展 `route_by_intent` |
| `src/graph/graph.py` | 修改 | 新增 `chat` 节点、`chat → END` 边；扩展 `route_by_intent` 出口列表 |
| `src/prompts/system/chat.md` | 新建 | chat 系统 prompt |
| `src/prompts/user/chat.md` | 新建 | chat 用户 prompt |
| `src/prompts/system/intent.md` | 修改 | 意图列表中增加 `chat` 描述 |
| `app.py` | 修改 | 流式输出支持 `chat` 节点，更新 fallback 消息 |
| `tests/graph/test_nodes.py` | 修改 | 新增 `TestChat` 类和 `route_by_intent` chat 测试 |
| `tests/graph/test_graph.py` | 修改 | 验证 chat 节点存在 |
| `tests/test_app.py` | 修改 | 新增 chat 流式测试，更新 fallback 断言 |

**不涉及变更的文件**：`src/tools/` 全部工具代码零改动、`src/config/` 无变更、`src/logs/` 无变更。
