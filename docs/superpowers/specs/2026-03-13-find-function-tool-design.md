# find_function 工具设计

## 问题背景

在 API 文档生成过程中，LLM 需要追踪 Go 代码中的内部函数调用链。当前只有 `scan_directory`（列出文件）和 `read_file`（读取文件内容）两个工具，LLM 必须靠猜测来定位函数定义所在的文件。例如 `BuyResource` 内部调用 `buyResourcePostPaid`，该函数定义在另一个文件中，LLM 需要反复尝试 5 次左右才能找到，浪费大量 token 和时间。

## 设计目标

- 将函数定位从"盲搜"（多次 scan_directory + read_file）降低到一次精确查找
- 实现轻量，不引入 AST 解析等重型依赖
- 与现有架构保持一致（LangChain @tool、JSON envelope 响应）

## 方案概述

新增 `find_function` 工具 + 更新 doc_gen 提示词 + 增加搜索失败保底策略。

## 详细设计

### 1. 新增工具：`find_function`

**模块位置：** `src/tools/code_search.py`

**输入参数：**
- `function_name: str` — 要查找的函数名（不含 `func` 关键字）
- `directory: str = "."` — 搜索起始目录，相对于 `settings.agent_work_dir`

**内部逻辑：**
1. 验证目录：检查 `settings.agent_work_dir / directory` 是否存在且为目录，不满足时返回 `fail()` 错误（与 `scan_directory` 一致）
2. 对 `function_name` 使用 `re.escape()` 防止正则注入
3. 递归查找所有 `.go` 文件（`rglob("*.go")`），排除 `_test.go`，按文件路径字母序排列（结果确定性）
4. 逐行读取每个文件，匹配搜索模式。兼顾 Go 两种函数定义形式：
   - 普通函数：`func buyResourcePostPaid(`
   - 方法（带接收者）：`func (s *Service) buyResourcePostPaid(`
   - 匹配模式：`r"^func\s+(\(.*?\)\s+)?{escaped_name}\s*\("` 对每行单独匹配
5. 文件编码处理：UTF-8 优先，`UnicodeDecodeError` 时回退到 latin-1（与 `file_reader` 一致）
6. 只返回第一条匹配结果
7. 使用 `ok()` / `fail()` JSON envelope 返回

**返回格式：**
- 找到时：`ok("找到函数定义", {"file": "相对路径", "line": 行号, "content": "该行内容"})`
- 未找到时：`fail(f"未找到函数 {function_name} 的定义")`

**工具描述（docstring）：**
> 在指定目录下查找 Go 函数的定义位置。仅当你需要定位一个具体的函数或方法的定义所在文件时使用此工具，不要用于通用代码搜索。传入函数名（不含 func 关键字），工具会自动匹配普通函数和方法定义。

**路径安全：** 与 `scan_directory`、`read_file` 一致，所有路径相对于 `settings.agent_work_dir` 解析。

### 2. 集成到图节点

**文件：** `src/graph/nodes.py`

- 在 `TOOLS` 列表中新增 `find_function`（从 5 个变为 6 个）
- **不加入** `QA_TOOLS` — 文档问答场景不需要搜索函数定义
- `doc_gen` 节点无需改动，`bind_tools(TOOLS)` 自动包含新工具

### 3. 更新 doc_gen 提示词

**文件：** `src/prompts/system/doc_gen.md`

在 Task 1（递归上下文构建）部分增加两条规则：

**规则 A — 优先使用 find_function：**
> 当遇到未知的函数调用时，优先使用 `find_function` 定位函数定义所在文件，而不是用 `scan_directory` 逐个文件猜测。

**规则 B — 搜索失败保底：**
> 当 `find_function` 返回未找到时，跳过该函数，不再尝试通过其他方式查找。在生成的文档中标注"该函数未找到定义，无法展开分析"，然后继续处理下一个未解析的引用。

## 涉及的文件变更

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `src/tools/code_search.py` | 新增 | `find_function` 工具实现 |
| `src/graph/nodes.py` | 修改 | 新增 `from src.tools.code_search import find_function`，加入 `TOOLS` 列表 |
| `src/prompts/system/doc_gen.md` | 修改 | 增加优先使用 find_function 的指导和搜索失败保底规则 |
| `tests/tools/test_code_search.py` | 新增 | `find_function` 单元测试 |
| `tests/graph/test_nodes.py` | 修改 | 验证 TOOLS 列表包含新工具 |

## 测试策略

- 使用 `tmp_path` 创建临时 Go 文件，测试普通函数匹配
- 测试方法（带接收者）匹配
- 测试未找到时的返回
- 测试 `_test.go` 文件被正确排除
- 测试路径沙箱（相对于 `agent_work_dir`）
- 测试目录不存在 / 非目录时的错误返回
- 测试函数名含正则特殊字符（如 `.`、`*`）时不会报错
- 测试非 UTF-8 编码文件不会导致崩溃
