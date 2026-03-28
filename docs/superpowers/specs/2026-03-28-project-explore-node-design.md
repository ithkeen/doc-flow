# project_explore 节点设计规格

## 目标

新增 `project_explore` 节点，以 ReAct 循环方式智能探索一个项目，输出项目结构汇总文档 `task.md`。

## 范围

- 只实现 `project_explore` ReAct 循环节点及其配套工具
- 不涉及 Send API、doc_gen_worker、project_summarize 等后续链路
- doc_gen 后续对接由未来迭代完成

## 图拓扑变更

在现有图中新增一条路径，其他路径不变：

```
START → intent_recognize → route_by_intent
    ├── doc_qa → END                          (不变)
    ├── chat → END                            (不变)
    ├── doc_gen ←→ doc_gen_tools              (不变)
    └── project_explore ←→ explore_tools      (新增)
            ↓ (无更多 tool_calls)
           END
```

- `project_explore`：新节点，LLM + 工具绑定
- `explore_tools`：新 `ToolNode(EXPLORE_TOOLS)`
- `route_project_explore`：新路由函数，检查 tool_calls 决定循环或结束
- `route_by_intent` 增加 `"project_explore"` 分支
- intent prompt 增加 `project_explore` 意图说明

## State 变更

不新增 state 字段。现有 `State(messages, intent)` 足够：
- `intent` 新增值 `"project_explore"`
- `messages` 承载 ReAct 循环的全部交互

## 工具集

### 复用现有工具（5个）

| 工具 | 来源 | 用途 |
|------|------|------|
| `read_file` | `src/tools/file.py` | 读取源代码/配置文件内容 |
| `find_function` | `src/tools/code_search.py` | 按名称搜索函数定义 |
| `find_struct` | `src/tools/code_search.py` | 按名称搜索 struct 定义 |
| `load_docgen_config` | `src/tools/config_reader.py` | 加载 .doc_gen.yaml |
| `write_file` | `src/tools/file.py` | 写入最终 task.md |

### 新增工具（2个）

#### `list_directory`

```python
@tool
def list_directory(path: str, max_depth: int = 1) -> str:
    """列出 CODE_SPACE_DIR 下指定路径的文件和子目录。

    Args:
        path: 相对于 CODE_SPACE_DIR 的目录路径
        max_depth: 递归深度，1=仅当前层，2=包含子目录内容，以此类推

    Returns:
        JSON 格式的目录内容列表，每项包含 name、type(file/dir)、size
    """
```

- 读取 `CODE_SPACE_DIR / path`
- 返回 JSON 列表：`[{"name": "cmd", "type": "dir"}, {"name": "main.go", "type": "file", "size": 1234}]`
- 排除常见噪音目录：`.git`、`node_modules`、`vendor`、`__pycache__`
- 超过 200 个条目时截断并提示

#### `find_files`

```python
@tool
def find_files(directory: str, pattern: str) -> str:
    """在 CODE_SPACE_DIR 下指定目录中按 glob 模式搜索文件。

    Args:
        directory: 相对于 CODE_SPACE_DIR 的搜索起始目录
        pattern: glob 模式，如 "*.go"、"**/main.go"、"**/deploy/*.yaml"

    Returns:
        JSON 格式的匹配文件路径列表（相对于 CODE_SPACE_DIR）
    """
```

- 基于 `pathlib.Path.glob()` 或 `rglob()`
- 返回 JSON 列表：`["ubill-access-api/ubill-order/cmd/main.go", ...]`
- 排除 `.git`、`node_modules`、`vendor` 等
- 超过 100 个结果时截断并提示

两个新工具放置在 `src/tools/explorer.py`，遵循现有的 `ok()`/`fail()` JSON 信封约定。

## 节点实现

### `project_explore` 节点

```python
EXPLORE_TOOLS = [
    list_directory, find_files,
    read_file, find_function, find_struct,
    load_docgen_config, write_file,
]

async def project_explore(state: State, config: RunnableConfig) -> dict:
    prompt = load_prompt("project_explore")
    user_input = _get_last_human_message(state)
    messages = prompt.format_messages(user_input=user_input)
    llm = get_llm("project_explore").bind_tools(EXPLORE_TOOLS)
    response = await llm.ainvoke(messages + state["messages"])
    return {"messages": [response]}
```

### `route_project_explore` 路由函数

```python
def route_project_explore(state: State) -> Literal["explore_tools", "__end__"]:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "explore_tools"
    return END
```

### 图注册

```python
graph.add_node("project_explore", project_explore)
graph.add_node("explore_tools", ToolNode(EXPLORE_TOOLS))
graph.add_conditional_edges("project_explore", route_project_explore,
                            ["explore_tools", END])
graph.add_edge("explore_tools", "project_explore")
```

`route_by_intent` 增加映射：`"project_explore" → "project_explore"`。

## Prompt 设计

新建 `src/prompts/system/project_explore.md` 和 `src/prompts/user/project_explore.md`。

### system prompt 核心内容

```
你是一个项目结构分析专家。你的任务是探索给定项目，生成项目结构汇总文档。

## 目标

你有3个目标，必须全部达成后立即停止：

1. 这个项目下有几个服务？
2. 每个服务属于什么类型？（API后端服务 / 定时任务 / 消息订阅）
3. 每个服务负责的全部功能（不能遗漏任何一个）

## 探索策略

- 你可以自由使用任何工具，以任何顺序，直到所有目标明确
- 优先读取部署配置文件（通常在 deploy 目录下），快速了解服务数量和类型
- 找到入口文件（如 main.go）确认服务角色
- 对于 API 服务：找到路由注册代码，穷举所有 API 端点及其处理函数文件
- 对于定时任务：找到 cron 调度注册，列出触发规则和处理函数文件
- 对于消息订阅：找到订阅注册代码，列出订阅名称和处理函数文件
- 重点是完整性——不遗漏任何功能点
- 达到目标后立即停止，不做多余探索

## 输出

当所有目标达成后，调用 write_file 工具将结果写入 {项目名称}/task.md，格式如下：

# {项目名称}

## 项目概览
- 语言: {语言}
- 服务数量: {N}

## 服务列表

### 1. {服务名} ({服务类型})
入口: {项目名称}/{入口文件相对路径}

#### API 列表（仅 API 服务）
| 路由 | 方法 | 处理文件 |
|------|------|---------|
| /api/v1/xxx | POST | {项目名称}/xxx/logic/Xxx.go |

#### 定时任务列表（仅定时任务服务）
| 触发规则 | 处理文件 |
|---------|---------|
| 0 3 * * * | {项目名称}/xxx/logic/Xxx.go |

#### 消息订阅列表（仅消息订阅服务）
| 订阅名称 | 处理文件 |
|---------|---------|
| order.created | {项目名称}/xxx/logic/Xxx.go |

注意：
- 所有文件路径从项目名称开始
- 不写说明、描述、注释
- 只列举事实数据
```

### user prompt

```
用户输入：{user_input}
```

## Intent Prompt 变更

在 `src/prompts/system/intent.md` 中增加 `project_explore` 意图：

```
- project_explore: 用户想要探索分析一个项目的结构，了解项目有哪些服务、API、定时任务或消息订阅
```

## LLM 配置

`get_llm("project_explore")` 回退到 `default_model`（与 intent/doc_qa 一致），不单独配置模型。如需独立模型，后续在 settings 中增加 `LLM_PROJECT_EXPLORE_MODEL`。

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/tools/explorer.py` | **新建** | `list_directory`、`find_files` 工具 |
| `src/graph/nodes.py` | 修改 | 新增 `project_explore` 节点、`route_project_explore` 路由、`EXPLORE_TOOLS` 列表 |
| `src/graph/graph.py` | 修改 | 注册新节点和边、更新 `route_by_intent` |
| `src/prompts/system/project_explore.md` | **新建** | project_explore 系统提示 |
| `src/prompts/user/project_explore.md` | **新建** | project_explore 用户提示模板 |
| `src/prompts/system/intent.md` | 修改 | 增加 project_explore 意图 |
| `app.py` | 修改 | streaming 过滤增加 project_explore 节点 |

## 测试计划

- `list_directory` 工具单元测试：正常目录、空目录、不存在路径、max_depth 控制
- `find_files` 工具单元测试：各种 glob 模式、空结果、排除噪音目录
- `project_explore` 节点测试：mock LLM 返回，验证 tool 绑定和消息流转
- `route_project_explore` 测试：有/无 tool_calls 的路由判断
- `route_by_intent` 测试：新增 project_explore 分支
- intent prompt 测试：验证 project_explore 意图可被正确识别

## 不在范围内

- Send API 并行调用 doc_gen（未来迭代）
- doc_gen_worker 子图封装（未来迭代）
- project_summarize 汇聚节点（未来迭代）
- CLI 入口（未来迭代）
- grep_codebase 工具（按需后续添加）
