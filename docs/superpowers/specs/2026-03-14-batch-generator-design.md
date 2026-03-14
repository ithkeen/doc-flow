# 批量文档生成器设计

> 日期: 2026-03-14
> 状态: 设计中

## 背景

doc-flow 当前通过 Chainlit 聊天界面逐个生成 API 文档。`AGENT_WORK_DIR` 配置为 codespace 根目录，下面包含多个 Go 项目（如 access、udata 等）。现有系统没有项目级组织、批量生成或黑名单机制。

用户需要一个 CLI 工具，能够一次性为整个项目生成所有 API 接口文档，并支持：
- 按项目组织文档输出目录
- 可配置的 API 发现规则（不同项目使用不同的注册函数模式）
- 黑名单机制（函数级和文件级，附带跳过原因）
- 文档索引生成（方便 LLM 快速定位文档）
- 增量生成（跳过已有文档，支持单个 API 重新生成）

未来规划：Chainlit 将下掉 `doc_gen` 意图，仅保留 `doc_qa`（文档问答）和 `chat`（闲聊）。文档视为开发者数据，普通用户只能查阅。

## 项目配置文件

每个项目在 `DOCS_OUTPUT_DIR/{project}/` 下有一个 `.docflow.yaml` 配置文件。配置使用 Pydantic model 进行校验，无效配置（缺少必填字段、无效正则等）在加载阶段立即报错并输出明确的错误信息。

### 完整示例

```yaml
# DOCS_OUTPUT_DIR/access/.docflow.yaml

# API 发现规则
discovery:
  # 扫描的源码根目录（相对于 AGENT_WORK_DIR）
  source_root: "access"
  # 注册函数模式列表，匹配源码中的注册调用
  # 支持正则，捕获组 1 为 handler 函数名
  patterns:
    - regex: 'RegisterHTTPTaskHandle\(.+,\s*(\w+)\)'

# 模块映射：源码路径 → 文档模块名
# match 使用 glob 模式（相对于 source_root），按顺序匹配，首次命中生效
modules:
  - match: "order/**"
    module: "order"
  - match: "user/**"
    module: "user"
  - match: "payment/**"
    module: "payment"
  # 未匹配的 fallback：取源码文件相对于 source_root 的第一级目录名
  # 如果文件直接在 source_root 下（无子目录），使用 "_root" 作为模块名

# 黑名单：不生成文档的函数和文件
blacklist:
  # 按函数名跳过
  functions:
    - name: "HealthCheck"
      reason: "内部健康检查接口，不对外暴露"
    - name: "LegacyOrderCreate"
      reason: "已废弃，由 CreateOrderV2 替代"
  # 按文件路径跳过（相对于 source_root）
  files:
    - path: "order/internal/debug.go"
      reason: "调试工具文件，不包含正式 API"
    - path: "common/middleware.go"
      reason: "中间件函数，非 API 接口"
```

### 配置字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `discovery.source_root` | string | 是 | 项目源码根目录，相对于 `AGENT_WORK_DIR` |
| `discovery.patterns` | list | 是 | API 注册函数的正则模式，捕获组 1 为函数名。加载时校验正则合法性 |
| `modules` | list | 否 | 模块映射规则，按顺序匹配 |
| `modules[].match` | string | 是 | glob 模式，相对于 `source_root` |
| `modules[].module` | string | 是 | 目标模块名 |
| `blacklist.functions` | list | 否 | 按函数名跳过的列表 |
| `blacklist.functions[].name` | string | 是 | 函数名 |
| `blacklist.functions[].reason` | string | 是 | 跳过原因 |
| `blacklist.files` | list | 否 | 按文件路径跳过的列表 |
| `blacklist.files[].path` | string | 是 | 文件路径，相对于 `source_root` |
| `blacklist.files[].reason` | string | 是 | 跳过原因 |

### 配置校验

`config.py` 使用 Pydantic model 校验 `.docflow.yaml`：
- `discovery` 和 `discovery.source_root` 为必填字段
- `discovery.patterns` 至少包含一项，且每项的 `regex` 必须是合法的正则表达式且包含至少一个捕获组
- `modules[].module` 必须匹配 `^[a-z][a-z0-9_]*$`
- `blacklist` 整体可选，`functions` 和 `files` 列表也可选

## 文档索引（INDEX.md）

索引是批量生成系统的核心，位于 `DOCS_OUTPUT_DIR/{project}/INDEX.md`，承担两个职责：

1. **去重过滤**：重复运行时，对比已发现 API 的 (函数名, 源码位置) 与索引记录，相同则跳过
2. **LLM 定位**：`doc_qa` 节点读取索引快速找到目标文档

### 索引格式

索引使用 Markdown 表格，便于人类阅读和 LLM 解析。`index.py` 使用基于正则的行级解析器处理表格（逐行匹配 `|` 分隔的字段），不依赖第三方 Markdown 解析库。所有字段值在写入时转义管道符（`|` → `\|`），读取时反转义。

```markdown
# access 项目 API 文档索引

## order

| API | 源码位置 | 文档位置 | 生成时间 |
|-----|---------|---------|---------|
| CreateOrder | order/logic/create.go:45 | order/CreateOrder.md | 2026-03-14 10:30 |
| QueryOrder | order/handler/query.go:12 | order/QueryOrder.md | 2026-03-14 10:31 |

## user

| API | 源码位置 | 文档位置 | 生成时间 |
|-----|---------|---------|---------|
| GetUserInfo | user/logic/info.go:30 | user/GetUserInfo.md | 2026-03-14 10:32 |

## 黑名单

| API | 源码位置 | 原因 |
|-----|---------|------|
| HealthCheck | common/health.go:5 | 内部健康检查接口，不对外暴露 |
| DebugHandler | - | 仅开发环境使用的调试接口 |
```

### 索引管理规则

- **增量更新**：每生成一个 API 文档后立即更新索引（追加或替换条目），确保进程中断后已完成的工作不会丢失
- 单个 API 重新生成（`--api`）后替换对应条目
- 黑名单条目从 `.docflow.yaml` 同步到索引的黑名单区域
- 生成时间精确到分钟（`YYYY-MM-DD HH:MM`）

### 路径约定

索引中的所有路径都是相对路径：
- **源码位置**：相对于 `source_root`（如 `order/logic/create.go:45`）
- **文档位置**：相对于 `DOCS_OUTPUT_DIR/{project}/`（如 `order/CreateOrder.md`）

### 文件命名规则

文档文件名直接使用原始 API 函数名，如 `CreateOrder.md`、`GetUserInfo.md`。

## 文档存储与 doc_qa 的兼容

### 路径方案

批量生成的文档存储在 `DOCS_OUTPUT_DIR/{project}/{module}/{api}.md`。放宽 `save_document` 的 `_validate_module_name` 正则，使其支持 `/` 路径分隔符，LLM 在 ReAct 循环中直接调用 `save_document` 保存文档，流程与现有 `doc_gen` 一致。

具体做法：
- 将 `_validate_module_name` 正则从 `^[a-z][a-z0-9_]*$` 放宽为 `^[a-z][a-z0-9_]*(/[a-z][a-z0-9_]*)*$`，支持如 `access/order` 的路径形式
- gen_doc prompt 指导 LLM 完成 Task 1-4（递归上下文构建 → 执行流分析 → 生成文档 → 调用 `save_document` 保存），module_name 使用 `{project}/{module}` 格式
- 工具集：`read_file`、`find_function`、`save_document`

### doc_qa 兼容性

放宽 `_validate_module_name` 后，`doc_qa` 的 `read_document` 和 `list_documents` 工具自然支持包含 `/` 的 module_name（如 `access/order`）。

**后续跟进**（不在本次范围）：
- 更新 `doc_qa` prompt，指导 LLM 先读取 INDEX.md 定位文档路径，再用 `read_document` 读取

## 批量生成流程

### 整体执行流程

```
┌─────────────────────────────────────────────────────┐
│ 1. 加载配置                                          │
│    读取 DOCS_OUTPUT_DIR/{project}/.docflow.yaml      │
│    Pydantic 校验，无效配置立即报错退出                 │
├─────────────────────────────────────────────────────┤
│ 2. API 发现                                          │
│    扫描 AGENT_WORK_DIR/{source_root}/ 下所有 .go 文件│
│    （排除 _test.go）                                  │
│    用 discovery.patterns 正则匹配注册调用             │
│    提取所有被注册的函数名 + 所在文件路径 + 行号        │
│    ※ 同一函数名在多个文件中被注册：全部记录，各自生成  │
│    ※ 正则匹配到函数名但捕获组为空：跳过并警告         │
├─────────────────────────────────────────────────────┤
│ 3. 过滤                                              │
│    ├─ 解析 INDEX.md 获取已记录的 API 集合             │
│    ├─ 去掉黑名单中的函数（按 name 匹配）              │
│    ├─ 去掉黑名单中的文件（按 path 匹配）              │
│    │  ※ 所有路径统一转为 source_root 相对路径再比较    │
│    └─ 去掉索引中已有的 API（函数名+源码位置相同）      │
├─────────────────────────────────────────────────────┤
│ 4. 模块分配                                          │
│    根据 modules 映射规则确定每个 API 的目标模块        │
│    未命中规则的使用 source_root 下的第一级目录名       │
│    ※ 文件直接在 source_root 下（无子目录）：          │
│       使用 "_root" 作为模块名                         │
├─────────────────────────────────────────────────────┤
│ 5. 串行生成                                          │
│    对每个待生成的 API：                                │
│    ├─ 构建初始 State（messages + params）             │
│    ├─ 调用 generator_graph（ReAct 循环）              │
│    │  LLM 读取源码、分析、生成文档、调用 save_document │
│    ├─ 立即更新 INDEX.md（追加/替换该 API 条目）       │
│    ├─ 记录结果（成功/失败）                           │
│    └─ 输出进度 [3/15] ✓ order.CreateOrder             │
├─────────────────────────────────────────────────────┤
│ 6. 同步黑名单                                        │
│    将 .docflow.yaml 中的黑名单条目同步到 INDEX.md     │
├─────────────────────────────────────────────────────┤
│ 7. 输出报告                                          │
│    总计/成功/失败/跳过(已有)/跳过(黑名单) 统计         │
└─────────────────────────────────────────────────────┘
```

### 单个 API 重新生成流程

使用 `--api CreateOrder` 时：

1. 加载配置
2. 在 `source_root` 中查找该函数（复用 `find_function` 的正则逻辑扫描 `.go` 文件）
3. 如果找到多个匹配：列出所有匹配项并报错退出，提示用户用 `--api-file` 指定具体文件路径
4. 如果该函数在黑名单中：输出警告（"该函数在黑名单中，原因：xxx"），仍然执行生成（用户显式指定表示有意覆盖）
5. 根据模块映射规则确定模块
6. 生成文档
7. 更新索引中该 API 的条目（替换旧记录）

### 全量强制重新生成

使用 `--force` 时：跳过步骤 3 的索引过滤，对所有发现的非黑名单 API 重新生成文档。

### `--all` 模式

遍历 `DOCS_OUTPUT_DIR` 下所有包含 `.docflow.yaml` 的子目录，逐项目执行。单个项目失败不影响后续项目，最终输出每个项目的独立报告。

## 生成专用图

独立构建的 LangGraph StateGraph，不复用现有主图：

```
START → gen_doc → [has_tool_calls?] ─yes→ gen_tools → gen_doc (循环)
                        │
                        └─ no ─→ END
```

### State 定义

```python
class GenState(TypedDict):
    messages: Annotated[list, add_messages]
    project: str        # 项目名（如 "access"）
    module: str         # 目标模块名（如 "order"）
    function_name: str  # 目标函数名（如 "CreateOrder"）
    source_file: str    # 源码文件路径，相对于 AGENT_WORK_DIR（如 "access/order/logic/create.go"）
    source_line: int    # 函数定义行号
```

### gen_doc 节点

- 使用专用的 `batch_doc_gen` prompt
- prompt 模板变量：`{project}`、`{module}`、`{function_name}`、`{source_file}`、`{source_line}`
- 绑定工具集：`read_file`、`find_function`、`save_document`
- 使用 `get_node_llm("doc_gen")` 获取 LLM 实例（复用 per-node LLM 配置）

### _get_node_llm 公共化

现有 `_get_node_llm` 函数定义在 `src/graph/nodes.py` 中，以下划线开头表示私有。generator 模块需要跨模块调用此函数，因此需要将其提取为公共 API：

- 将 `_get_node_llm` 从 `src/graph/nodes.py` 移动到 `src/config/llm.py`（新文件）
- 重命名为 `get_node_llm`（去掉下划线前缀）
- `src/graph/nodes.py` 和 `src/generator/graph.py` 均从 `src.config.llm` 导入
- 在 `src/config/__init__.py` 中导出 `get_node_llm`

### batch_doc_gen prompt 与现有 doc_gen prompt 的区别

| 方面 | 现有 doc_gen | batch_doc_gen |
|------|-------------|---------------|
| Pre-check 阶段 | 需要（解析目标、去重检查） | 不需要（目标已确定） |
| 模块推断 | LLM 从包名/目录推断 | 预分配，通过参数传入 |
| 保存方式 | LLM 调用 `save_document`（module_name 自行推断） | LLM 调用 `save_document`（module_name 由 prompt 指定为 `{project}/{module}`） |
| 起点 | 从 Pre-check 开始 | 直接从 Task 1（递归上下文构建）开始 |
| Task 1-4 核心流程 | 递归上下文构建 → 执行流分析 → 生成文档 → 保存 | 相同 |

## CLI 接口

入口：`python -m src.generator`

```bash
# 生成指定项目的所有 API 文档
uv run python -m src.generator --project access

# 生成所有项目（扫描 DOCS_OUTPUT_DIR 下所有有 .docflow.yaml 的项目）
uv run python -m src.generator --all

# 重新生成指定项目中某个 API 的文档
uv run python -m src.generator --project access --api CreateOrder

# 通过文件路径精确指定（用于函数名有多个匹配的情况）
uv run python -m src.generator --project access --api CreateOrder --api-file order/logic/create.go

# 强制重新生成整个项目（忽略索引）
uv run python -m src.generator --project access --force

# 预览模式：显示会生成哪些 API，不实际调用 LLM
uv run python -m src.generator --project access --dry-run
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `--project` | 指定项目名（对应 `DOCS_OUTPUT_DIR/{project}/` 目录） |
| `--all` | 遍历所有有 `.docflow.yaml` 的项目 |
| `--api` | 指定重新生成的单个 API 函数名（与 `--project` 配合使用） |
| `--api-file` | 精确指定源码文件路径（当 `--api` 有多个匹配时使用，相对于 `source_root`） |
| `--force` | 忽略索引，强制重新生成所有非黑名单 API |
| `--dry-run` | 预览模式，只显示发现/过滤结果，不实际生成 |

### 参数约束

- `--project` 和 `--all` 互斥
- `--api` 必须与 `--project` 一起使用
- `--api-file` 必须与 `--api` 一起使用
- `--force` 不能与 `--api` 同时使用（单个 API 重新生成本身就忽略索引）

### 输出示例

```
[doc-flow] 加载项目配置: access
[doc-flow] 发现 23 个 API 函数
[doc-flow] 跳过 3 个黑名单函数
[doc-flow] 跳过 15 个已有文档
[doc-flow] 待生成: 5 个 API
[doc-flow] [1/5] 生成中: order.CreateOrder ...
[doc-flow] [1/5] ✓ order.CreateOrder (48s)
[doc-flow] [2/5] 生成中: order.CancelOrder ...
[doc-flow] [2/5] ✓ order.CancelOrder (62s)
[doc-flow] [3/5] 生成中: user.UpdateProfile ...
[doc-flow] [3/5] ✗ user.UpdateProfile (错误: LLM 调用超时)
...
[doc-flow] 索引已更新: DOCS_OUTPUT_DIR/access/INDEX.md

=== 生成报告 ===
总计: 23 | 成功: 4 | 失败: 1 | 跳过(已有): 15 | 跳过(黑名单): 3
失败列表:
  - user.UpdateProfile: LLM 调用超时
```

## 模块结构

```
src/generator/
├── __init__.py
├── __main__.py          # CLI 入口，argparse 参数解析，调用 runner
├── config.py            # .docflow.yaml 解析，Pydantic model 校验，返回 ProjectConfig
├── discovery.py         # API 发现：扫描 .go 文件 + 正则匹配注册调用
├── index.py             # INDEX.md 读写：正则行级解析器，查询/追加/替换/写回
├── runner.py            # 主编排：加载配置 → 发现 → 过滤 → 模块分配 → 生成 → 更新索引
└── graph.py             # 生成专用图：gen_doc ↔ gen_tools ReAct 循环
```

### 各模块依赖关系

```
src/config (settings singleton: AGENT_WORK_DIR, DOCS_OUTPUT_DIR, LLM config)
    └─> src/generator/config.py (reads .docflow.yaml)
    └─> src/generator/discovery.py (uses AGENT_WORK_DIR for scanning)
    └─> src/generator/index.py (uses DOCS_OUTPUT_DIR for index path)
    └─> src/generator/graph.py (uses _get_node_llm, existing tools)

src/tools/ (read_file, find_function, save_document)
    └─> src/generator/graph.py (binds tools to LLM)

src/prompts/ (load_prompt)
    └─> src/generator/graph.py (loads batch_doc_gen prompt)

src/logs/ (logger)
    └─> all generator modules
```

## 对现有代码的影响

| 模块 | 变更 | 说明 |
|------|------|------|
| `src/config/settings.py` | 无变化 | `AGENT_WORK_DIR` 和 `DOCS_OUTPUT_DIR` 继续作为全局配置 |
| `src/config/` | **新增** | 新增 `llm.py`，将 `_get_node_llm` 提取为公共 `get_node_llm` 函数 |
| `src/graph/nodes.py` | **小改** | `_get_node_llm` 改为从 `src.config.llm` 导入 `get_node_llm` |
| `src/tools/doc_storage.py` | **小改** | 放宽 `_validate_module_name` 正则，支持 `/` 路径分隔符 |
| `src/tools/` 其他 | 无变化 | `read_file`、`find_function` 直接复用 |
| `src/graph/` | 无变化 | 现有主图保持不动 |
| `src/prompts/system/` | **新增** | 新增 `batch_doc_gen.md` prompt 模板 |
| `src/prompts/user/` | **新增** | 新增 `batch_doc_gen.md` user prompt 模板 |

## 文档目录结构示例

```
DOCS_OUTPUT_DIR/
├── access/                      # access 项目
│   ├── .docflow.yaml            # 项目配置
│   ├── INDEX.md                 # 文档索引
│   ├── order/                   # order 模块
│   │   ├── CreateOrder.md
│   │   ├── QueryOrder.md
│   │   └── CancelOrder.md
│   └── user/                    # user 模块
│       ├── GetUserInfo.md
│       └── UpdateProfile.md
├── udata/                       # udata 项目
│   ├── .docflow.yaml
│   ├── INDEX.md
│   └── ...
```

## 边界情况处理

| 场景 | 处理方式 |
|------|---------|
| `.docflow.yaml` 格式错误 | Pydantic 校验失败，输出错误详情并退出 |
| `discovery.patterns` 中的正则无效 | 加载时校验，报错退出 |
| 正则匹配到注册调用但捕获组为空 | 跳过该匹配，输出警告 |
| 同一函数名在多个文件中被注册 | 全部记录，各自生成独立文档 |
| `--api` 指定的函数有多个定义 | 报错退出，提示使用 `--api-file` 精确指定 |
| `--api` 指定的函数在黑名单中 | 输出警告但继续生成（用户显式指定） |
| `--api` 指定的函数存在于源码中但未被任何 discovery pattern 匹配 | 仍然生成（`--api` 是显式指令，不受发现规则限制） |
| 文件直接在 `source_root` 下（无子目录） | 使用 `_root` 作为模块名 |
| LLM 调用超时或失败 | 记录失败，继续处理下一个 API，最终报告中列出所有失败项 |
| `--all` 模式下某项目失败 | 继续处理后续项目，最终输出每个项目的独立报告 |
| INDEX.md 不存在 | 首次运行时自动创建 |
| INDEX.md 被手动修改导致格式异常 | 解析失败时输出警告，视为空索引重新生成 |
