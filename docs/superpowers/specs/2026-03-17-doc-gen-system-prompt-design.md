# API 文档生成系统提示词设计

## 概述

设计一个新的系统提示词 `doc_gen`，用于交互式单文件 API 文档生成场景。agent 从用户的自然语言输入出发，自主完成从路径解析到文档保存的完整流程。

与现有 `batch_doc_gen` 的区别：
- `batch_doc_gen`：接收预解析好的参数（project/module/function_name/source_file/source_line），用于批量编排
- `doc_gen`（新）：从用户原始输入自主解析，支持索引检查和用户交互，用于单文件交互式生成

## 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/prompts/system/doc_gen.md` | 新建 | 系统提示词，定义角色、流程、工具、模板 |
| `src/prompts/user/doc_gen.md` | 新建 | 用户模板，仅传入 `{user_input}` |

不需要修改 `loader.py`，通过 `load_prompt("doc_gen")` 直接加载。

## 工具集

agent 绑定以下 8 个工具：

| 工具 | 用途 | 所属步骤 |
|------|------|----------|
| `load_docgen_config` | 读取 .doc_gen.yaml 项目配置 | 步骤 2 |
| `match_api_name` | 用正则从文件中解析 API 名称 | 步骤 4 |
| `query_api_index` | 查询 API 索引是否已存在 | 步骤 5 |
| `read_file` | 读取源码文件 | 步骤 6 |
| `find_function` | 定位函数定义所在文件 | 步骤 6 |
| `find_struct` | 定位结构体定义所在文件 | 步骤 6 |
| `write_file` | 写入生成的文档 | 步骤 8 |
| `save_api_index` | 写入 API 文档索引 | 步骤 9 |

## 执行流程

### 步骤 1：解析用户输入

从用户输入中提取：
- **项目名称**：路径的一级目录（如 `ubill-access-api`）
- **文件路径**：完整的相对路径（如 `ubill-access-api/ubill-order/logic/BuyResource.go`）

示例输入："帮我生成 ubill-access-api/ubill-order/logic/BuyResource.go 的 API 文档"

**错误处理**：如果用户输入中无法识别有效的文件路径，直接回复用户，请求提供正确的文件路径。

### 步骤 2：加载项目配置

调用 `load_docgen_config`，参数为 `{项目名}/.doc_gen.yaml`。

全局记住配置中的（保留在对话上下文中，后续步骤直接引用）：
- `modules.mapping`：路径到模块名的映射
- `search_rules.function_patterns`：API 函数匹配模式
- `search_rules.struct_patterns`：结构体匹配模式

### 步骤 3：确定模块

用 `modules.mapping` 的 key 匹配文件路径前缀，确定模块名。使用最长前缀匹配策略（当多个 key 都能匹配时，取最长的那个）。

示例：文件路径 `ubill-access-api/ubill-order/logic/BuyResource.go` 匹配 `ubill-access-api/ubill-order/logic` → 模块名 `order`。

### 步骤 4：解析 API 名称

调用 `match_api_name`，传入文件路径和 `function_patterns` 中的模式。如果有多个模式，按顺序逐个尝试，使用第一个成功匹配的结果。

### 步骤 5：查询索引

调用 `query_api_index`，传入 API 名称和项目名称。

- 如果索引已存在：直接回复用户"该 API 文档已存在，是否覆盖？"，等待用户在对话中回复确认（本 agent 运行在 Chainlit 对话式 UI 中，用户的下一条消息即为确认）
- 如果用户拒绝覆盖：终止流程，告知用户已取消
- 如果不存在或用户确认覆盖：继续执行

### 步骤 6：递归代码读取

维护两个跟踪列表：
- **Resolved**：已读取的类型、函数、文件
- **Unresolved**：代码中发现但未读取的引用

循环执行：
1. 用 `read_file` 读取目标文件，从目标函数开始分析
2. 提取所有引用的类型、函数、导入包
3. 将未在 Resolved 中的引用加入 Unresolved
4. 对未解析的函数调用 `find_function` 定位文件，对结构体调用 `find_struct` 定位文件
5. 用 `read_file` 读取定位到的文件，移入 Resolved
6. 重复直到 Unresolved 为空

**递归深度限制**：最多读取 20 个文件。达到上限后停止递归，基于已收集的上下文生成文档，并在文档中注明部分引用未展开。

聚焦于目标函数的直接调用链，不要探索整个包。

需要跟踪的引用类型：
- 请求/响应结构体定义（含嵌套结构体）
- 业务逻辑函数和辅助方法
- 自定义错误类型和错误码常量
- 中间件或拦截器
- 接口及其实现

**兜底规则**：如果 `find_function` 或 `find_struct` 返回未找到，跳过该引用，在文档中标注"该定义未找到，无法展开分析"。

完成条件——能完整回答以下三个问题：
- 请求和响应结构体的每个字段是什么（含嵌套类型）？
- 所有错误返回路径、触发条件和错误码是什么？
- 核心逻辑流程是什么，每步调用了哪些子函数？

### 步骤 7：生成文档

基于步骤 6 的完整代码上下文：
1. 分析执行流程（Happy Path + 所有错误分支）
2. 按文档模板生成 Markdown 文档
3. 请求示例仅保留一个成功示例

### 步骤 8：写入文档

调用 `write_file`，路径为 `{项目名}/{模块名}/{API名}.md`（相对于 `docs_space_dir`）。

示例：`ubill-access-api/order/BuyResource.md`

### 步骤 9：写入索引

调用 `save_api_index`，传入：
- `api`：API 名称
- `project`：项目名称
- `source`：源码文件路径
- `doc`：文档文件路径

## 文档模板

基于 `batch_doc_gen.md` 的模板，调整请求示例部分仅保留成功示例。完整模板如下：

```markdown
# <API 名称>

## 概述
简要描述该 API 的功能和主要使用场景。

## 请求参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| paramName | string | 是 | 参数说明 |

## 响应

| 字段 | 类型 | 描述 |
|------|------|------|
| fieldName | string | 字段说明 |

## 执行流程

（Mermaid flowchart TD 流程图）

## 错误码

| 错误码 | 触发条件 | 描述 |
|--------|----------|------|
| 10001 | 输入无效 | 详细说明 |

## 请求示例

（curl 格式的成功请求示例，仅一个）

## 响应示例

（成功响应的 JSON 示例）
```

## 质量规则

- 参数和响应表必须使用 Markdown 表格格式
- 类型名必须与 Go 源码中的实际类型一致（如 `int64`、`[]string`，不得使用 `number`、`array`）
- 错误码必须覆盖代码中的每一条错误返回路径，不得遗漏
- 请求示例使用 curl 格式，基于实际结构体定义填写字段值
- 请求示例使用固定 URL `http://internal-api-test03.service.ucloud.cn`，不追加路径，仅填写 `-d` 中的请求体
- 响应示例必须反映实际的响应结构体，不使用泛化占位符
- 如果结构体字段有 validation tag（如 `binding:"required"`），在描述列中说明校验规则
- 嵌套结构体使用点号展开（如 `data.user.name`）或使用子表
- Mermaid 流程图必须覆盖所有步骤和错误分支
- Mermaid 中的错误码必须与错误码表一致
- Mermaid 使用 `flowchart TD`（自上而下）方向
- Mermaid 节点标签用双引号包裹，避免语法冲突
- 主路径使用矩形节点 `["标签"]`，错误分支使用圆角节点 `("标签")`

## 提示词语言

系统提示词使用中文编写，与工具注释和用户交互风格一致。

## 用户模板

`src/prompts/user/doc_gen.md` 内容：

```
用户输入：{user_input}
```

与现有 `intent.md` 的用户模板风格一致。
