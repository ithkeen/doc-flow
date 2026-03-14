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

每个项目在 `DOCS_OUTPUT_DIR/{project}/` 下有一个 `.docflow.yaml` 配置文件。

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
| `discovery.patterns` | list | 是 | API 注册函数的正则模式，捕获组 1 为函数名 |
| `modules` | list | 否 | 模块映射规则，按顺序匹配 |
| `modules[].match` | string | 是 | glob 模式，相对于 `source_root` |
| `modules[].module` | string | 是 | 目标模块名 |
| `blacklist.functions` | list | 否 | 按函数名跳过的列表 |
| `blacklist.functions[].name` | string | 是 | 函数名 |
| `blacklist.functions[].reason` | string | 是 | 跳过原因 |
| `blacklist.files` | list | 否 | 按文件路径跳过的列表 |
| `blacklist.files[].path` | string | 是 | 文件路径，相对于 `source_root` |
| `blacklist.files[].reason` | string | 是 | 跳过原因 |

## 文档索引（INDEX.md）

索引是批量生成系统的核心，位于 `DOCS_OUTPUT_DIR/{project}/INDEX.md`，承担两个职责：

1. **去重过滤**：重复运行时，对比已发现 API 的 (函数名, 源码位置) 与索引记录，相同则跳过
2. **LLM 定位**：`doc_qa` 节点读取索引快速找到目标文档

### 索引格式

```markdown
# access 项目 API 文档索引

## order

| API | 源码位置 | 文档位置 | 生成时间 |
|-----|---------|---------|---------|
| CreateOrder | order/logic/create.go:45 | order/create_order.md | 2026-03-14 |
| QueryOrder | order/handler/query.go:12 | order/query_order.md | 2026-03-14 |

## user

| API | 源码位置 | 文档位置 | 生成时间 |
|-----|---------|---------|---------|
| GetUserInfo | user/logic/info.go:30 | user/get_user_info.md | 2026-03-14 |

## 黑名单

| API | 源码位置 | 原因 |
|-----|---------|------|
| HealthCheck | common/health.go:5 | 内部健康检查接口，不对外暴露 |
| DebugHandler | - | 仅开发环境使用的调试接口 |
```

### 索引管理规则

- 每次批量生成完成后自动更新索引
- 单个 API 重新生成（`--api`）后更新对应条目
- 黑名单条目从 `.docflow.yaml` 同步到索引的黑名单区域
- 索引以 Markdown 表格形式存储，便于人类阅读和 LLM 解析

## 批量生成流程

### 整体执行流程

```
┌─────────────────────────────────────────────────────┐
│ 1. 加载配置                                          │
│    读取 DOCS_OUTPUT_DIR/{project}/.docflow.yaml      │
├─────────────────────────────────────────────────────┤
│ 2. API 发现                                          │
│    扫描 AGENT_WORK_DIR/{source_root}/ 下所有 .go 文件│
│    用 discovery.patterns 正则匹配注册调用             │
│    提取所有被注册的函数名 + 所在文件路径 + 行号        │
├─────────────────────────────────────────────────────┤
│ 3. 过滤                                              │
│    ├─ 解析 INDEX.md 获取已记录的 API 集合             │
│    ├─ 去掉黑名单中的函数（按 name 匹配）              │
│    ├─ 去掉黑名单中的文件（按 path 匹配）              │
│    └─ 去掉索引中已有的 API（函数名+源码位置相同）      │
├─────────────────────────────────────────────────────┤
│ 4. 模块分配                                          │
│    根据 modules 映射规则确定每个 API 的目标模块        │
│    未命中规则的使用 source_root 下的第一级目录名       │
├─────────────────────────────────────────────────────┤
│ 5. 串行生成                                          │
│    对每个待生成的 API：                                │
│    ├─ 构建初始 State（messages + params）             │
│    ├─ 调用 generator_graph（ReAct 循环）              │
│    ├─ 记录结果（成功/失败）                           │
│    └─ 输出进度 [3/15] ✓ order.CreateOrder             │
├─────────────────────────────────────────────────────┤
│ 6. 更新索引                                          │
│    将新生成的 API 追加到 INDEX.md                     │
│    同步黑名单条目到索引的黑名单区域                    │
├─────────────────────────────────────────────────────┤
│ 7. 输出报告                                          │
│    总计/成功/失败/跳过(已有)/跳过(黑名单) 统计         │
└─────────────────────────────────────────────────────┘
```

### 单个 API 重新生成流程

使用 `--api CreateOrder` 时：

1. 加载配置
2. 在 `source_root` 中查找该函数（使用 `find_function` 逻辑）
3. 跳过索引检查和黑名单检查，直接生成
4. 更新索引中该 API 的条目（替换旧记录）

### 全量强制重新生成

使用 `--force` 时：跳过步骤 3 的索引过滤，对所有发现的非黑名单 API 重新生成文档。

## 生成专用图

独立构建的 LangGraph StateGraph，不复用现有主图：

```
START → gen_doc → [has_tool_calls?] ─yes→ gen_tools → gen_doc (循环)
                        │
                        └─ no ─→ END
```

### gen_doc 节点

- 使用专用的 `batch_doc_gen` prompt（见下文）
- 接收预确定的上下文：项目名、模块名、函数名、源码文件路径
- 绑定工具集：`read_file`、`save_document`、`find_function`
- 使用 `_get_node_llm("doc_gen")` 获取 LLM 实例（复用 per-node LLM 配置）

### batch_doc_gen prompt 与现有 doc_gen prompt 的区别

| 方面 | 现有 doc_gen | batch_doc_gen |
|------|-------------|---------------|
| Pre-check 阶段 | 需要（解析目标、去重检查） | 不需要（目标已确定） |
| 模块推断 | LLM 从包名/目录推断 | 预分配，通过参数传入 |
| save_document 路径 | LLM 自行决定 module_name | 使用预分配的 `{project}/{module}` |
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

# 强制重新生成整个项目（忽略索引）
uv run python -m src.generator --project access --force
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `--project` | 指定项目名（对应 `DOCS_OUTPUT_DIR/{project}/` 目录） |
| `--all` | 遍历所有有 `.docflow.yaml` 的项目 |
| `--api` | 指定重新生成的单个 API 函数名（与 `--project` 配合使用） |
| `--force` | 忽略索引，强制重新生成所有非黑名单 API |

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
├── config.py            # .docflow.yaml 解析，返回 ProjectConfig dataclass
├── discovery.py         # API 发现：扫描 .go 文件 + 正则匹配注册调用
├── index.py             # INDEX.md 读写：解析/查询/追加/更新/写回
├── runner.py            # 主编排：加载配置 → 发现 → 过滤 → 模块分配 → 生成 → 更新索引
└── graph.py             # 生成专用图：gen_doc ↔ gen_tools ReAct 循环
```

### 各模块依赖关系

```
src/config (settings singleton: AGENT_WORK_DIR, DOCS_OUTPUT_DIR, LLM config)
    └─> src/generator/config.py (reads .docflow.yaml)
    └─> src/generator/discovery.py (uses AGENT_WORK_DIR for scanning)
    └─> src/generator/index.py (uses DOCS_OUTPUT_DIR for index path)
    └─> src/generator/graph.py (uses _get_node_llm, tools from src/tools/)

src/tools/ (read_file, save_document, find_function)
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
| `src/tools/doc_storage.py` | **需修改** | `module_name` 验证正则 `^[a-z][a-z0-9_]*$` 需放宽为支持 `/` 路径分隔符（如 `access/order`） |
| `src/tools/` 其他 | 无变化 | `read_file`、`find_function` 等直接复用 |
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
│   │   ├── create_order.md
│   │   ├── query_order.md
│   │   └── cancel_order.md
│   └── user/                    # user 模块
│       ├── get_user_info.md
│       └── update_profile.md
├── udata/                       # udata 项目
│   ├── .docflow.yaml
│   ├── INDEX.md
│   └── ...
```
