# Graph 模块设计

## 概述

graph 模块是 doc-flow agent 的核心编排层，使用 LangGraph 框架实现。负责将意图识别、文档生成和工具调用串联为一个完整的 agent 工作流。

## 文件结构

```
src/graph/
├── __init__.py      # 导出 build_graph
├── graph.py         # build_graph()：构建并编译 StateGraph
└── nodes.py         # State 定义、节点函数、路由函数
```

## State 定义

```python
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages

class State(TypedDict):
    messages: Annotated[list, add_messages]  # LLM 对话消息列表（自动累加）
    intent: str                               # 意图识别结果，如 "doc_gen"
    confidence: float                         # 意图置信度
    params: dict                              # 从用户输入提取的参数（如 directory_path）
```

- `messages` 使用 `add_messages` reducer，自动追加新消息
- `intent` / `confidence` / `params` 由意图识别节点写入，路由函数和后续节点读取
- 与现有 `intent` 提示词模板的输出格式完全对应

## 图结构

```
        START
          │
   intent_recognize
          │
    (route_by_intent)
       /        \
   doc_gen      END (unknown intent)
    ↕  ↕
   tools
  (ReAct loop)
```

- 意图识别作为入口节点，根据识别结果条件路由
- `doc_gen` 与 `ToolNode` 之间形成 ReAct 循环
- 未来新增意图只需加节点 + 路由分支

## 节点定义

### intent_recognize

- 使用 `load_prompt("intent")` 加载提示词模板
- 调用 LLM 进行意图分类，不绑定工具
- 解析返回的 JSON，写入 `state["intent"]`, `state["confidence"]`, `state["params"]`

### doc_gen

- 使用 `load_prompt("doc_gen")` 加载提示词模板
- 创建绑定了 5 个工具的 LLM（`bind_tools`）
- 从 `state["params"]` 取出参数，格式化提示词
- 返回 AI 消息，可能包含 `tool_calls`

### tools

- 直接使用 `langgraph.prebuilt.ToolNode`
- 传入 5 个工具：`scan_directory`, `read_file`, `save_document`, `read_document`, `list_documents`

## 路由函数

### route_by_intent

- `intent == "doc_gen"` → 进入 `doc_gen` 节点
- 其他/未知意图 → `END`

### route_doc_gen

- 最后一条 AI 消息有 `tool_calls` → `"tools"`
- 没有 `tool_calls` → `END`

## 图编排（graph.py）

```python
def build_graph():
    graph = StateGraph(State)

    graph.add_node("intent_recognize", intent_recognize)
    graph.add_node("doc_gen", doc_gen)
    graph.add_node("tools", ToolNode(tools=[...]))

    graph.add_edge(START, "intent_recognize")
    graph.add_conditional_edges("intent_recognize", route_by_intent)
    graph.add_conditional_edges("doc_gen", route_doc_gen)
    graph.add_edge("tools", "doc_gen")

    return graph.compile()
```

## Prompts 与 Graph 的衔接

采用**节点内格式化、不入 state**的方式（思路 A）：

- 每个节点内部调用 `load_prompt(name).format_messages(...)` 生成消息列表
- 格式化后的 system/user 消息仅用于本次 LLM 调用，不写入 `state["messages"]`
- `state["messages"]` 只存用户原始输入和工具调用来回消息
- `doc_gen` 节点在 ReAct 循环中，每轮将 system prompt + `state["messages"]` 合并后发给 LLM

```python
def doc_gen(state: State) -> dict:
    prompt = load_prompt("doc_gen")
    system_messages = prompt.format_messages(
        directory_path=state["params"]["directory_path"],
    )
    all_messages = system_messages + state["messages"]
    response = llm_with_tools.invoke(all_messages)
    return {"messages": [response]}
```

## 模块依赖

```
graph.py
  ├── nodes.py（State, intent_recognize, doc_gen, 路由函数）
  ├── src/tools/*（5 个工具传给 ToolNode）
  └── langgraph.prebuilt.ToolNode

nodes.py
  ├── src/prompts（load_prompt）
  ├── src/config（settings，获取 LLM 配置）
  └── src/logs（get_logger）
```

## 对外接口

```python
from src.graph import build_graph

graph = build_graph()
result = graph.invoke({"messages": [("human", "请为 ./handler/user 生成文档")]})
```

## 新增依赖

`pyproject.toml` 需添加：
- `langgraph`
- `langchain-openai`
