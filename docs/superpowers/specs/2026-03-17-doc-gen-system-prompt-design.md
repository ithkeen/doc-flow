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

### 步骤 2：加载项目配置

调用 `load_docgen_config`，参数为 `{项目名}/.doc_gen.yaml`。

全局记住配置中的：
- `modules.mapping`：路径到模块名的映射
- `search_rules.function_patterns`：API 函数匹配模式
- `search_rules.struct_patterns`：结构体匹配模式

### 步骤 3：确定模块

用 `modules.mapping` 的 key 匹配文件路径前缀，确定模块名。

示例：文件路径 `ubill-access-api/ubill-order/logic/BuyResource.go` 匹配 `ubill-access-api/ubill-order/logic` → 模块名 `order`。

### 步骤 4：解析 API 名称

调用 `match_api_name`，传入文件路径和 `function_patterns` 中的第一个模式，获取 API 名称。

### 步骤 5：查询索引

调用 `query_api_index`，传入 API 名称和项目名称。

- 如果索引已存在：反问用户"该 API 文档已存在，是否覆盖？"，等待用户确认
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

调用 `write_file`，路径为 `{项目名}/{模块名}/{API名}.md`。

示例：`ubill-access-api/order/BuyResource.md`

### 步骤 9：写入索引

调用 `save_api_index`，传入：
- `api`：API 名称
- `project`：项目名称
- `source`：源码文件路径
- `doc`：文档文件路径

## 文档模板

复用 `batch_doc_gen.md` 的文档模板，调整如下：

- 保留：Overview、Request Parameters、Response、Execution Flow（Mermaid）、Error Codes
- 调整：请求示例部分只保留一个成功请求示例（移除失败示例）
- 保留：所有质量规则（Go 类型精确匹配、错误码完整覆盖、Mermaid 规范等）

## 提示词语言

系统提示词使用中文编写，与工具注释和用户交互风格一致。

## 用户模板

`src/prompts/user/doc_gen.md` 内容：

```
用户输入：{user_input}
```

与现有 `intent.md` 的用户模板风格一致。
