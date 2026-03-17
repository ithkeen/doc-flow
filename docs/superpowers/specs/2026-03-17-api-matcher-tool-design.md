# API Matcher Tool 设计文档

**日期**: 2026-03-17
**状态**: 设计完成，待实现

## 概述

新增 `src/tools/api_matcher.py` 模块，提供一个 LangChain `@tool` 函数，用于在指定文件中通过正则表达式快速匹配 API 名称。

## 需求

- 传入文件路径（相对 `code_space_dir`）和正则表达式
- 正则必须包含一个捕获组，捕获组的值即为 API 名称
- 返回第一个匹配的 API 名称（单模式单结果）
- 作为 LLM Agent 工具使用，遵循 JSON Envelope 返回格式

### 示例

- 模式: `http\.HandlerFunc\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)`
- 文件内容含: `http.HandlerFunc(DeleteResource)`
- 返回: `DeleteResource`

## 模块结构

**文件**: `src/tools/api_matcher.py`

**依赖**:
- `re`, `pathlib.Path`
- `langchain_core.tools.tool`
- `src.config.settings`（获取 `code_space_dir`）
- `src.logs.get_logger`
- `src.tools.utils.ok`, `src.tools.utils.fail`

## 接口定义

```python
@tool
def match_api_name(file_path: str, pattern: str) -> str:
    """在 code_space_dir 下指定文件中，使用正则表达式匹配 API 名称。

    传入一个正则表达式（必须包含一个捕获组），工具会逐行扫描文件，
    返回第一个匹配的捕获组内容作为 API 名称。
    若正则包含多个捕获组，仅使用第一个捕获组（group(1)）。

    Args:
        file_path: 相对于 code_space_dir 的文件路径，如 "ubill-access-api/router.go"
        pattern: 正则表达式字符串，必须包含至少一个捕获组，第一个捕获组即为 API 名称

    Returns:
        JSON Envelope 格式的响应字符串：
        - 成功: {"success": true, "message": "...", "payload": {...}, "error": null}
        - 失败: {"success": false, "message": "...", "payload": null, "error": "..."}
    """
```

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `file_path` | `str` | 相对于 `code_space_dir` 的文件路径 |
| `pattern` | `str` | 正则表达式，必须包含至少一个捕获组。若有多个捕获组，仅使用 `group(1)` |

### 返回值

成功时 payload 结构：

```json
{
  "api_name": "DeleteResource",
  "file": "ubill-access-api/router.go",
  "line": 42,
  "content": "    http.HandlerFunc(DeleteResource)"
}
```

- `api_name`: 第一个捕获组匹配到的 API 名称
- `file`: 文件相对路径（与传入的 `file_path` 一致）
- `line`: 匹配所在行号（1-based，与 `code_search.py` 一致）
- `content`: 匹配行的完整内容（`line.strip()`，与 `code_search.py` 的 `content` 字段一致）

成功时 message 示例: `"匹配到 API: DeleteResource（文件: router.go, 第 42 行）"`

## 核心逻辑流程

1. **验证 file_path**: 非空且非纯空白，否则 `fail("文件路径不能为空")`
2. **验证 pattern**: 非空且非纯空白，否则 `fail("匹配模式不能为空")`
3. **编译正则**: `re.compile(pattern)`，失败则 `fail("无效的正则表达式: ...")`
4. **验证捕获组**: `compiled.groups >= 1`，否则 `fail("正则表达式必须包含至少一个捕获组")`
5. **构建绝对路径**: `Path(settings.code_space_dir) / file_path`
6. **验证文件**: 文件存在且非目录
7. **读取文件内容**:
   - 尝试 UTF-8 编码读取
   - `UnicodeDecodeError` → 尝试 Latin-1 编码读取
   - 其他异常 → `fail("文件读取失败: ...")`
8. **逐行匹配**: `enumerate(content.splitlines(), 1)` + `re.search(compiled, line)`
   - 第一个命中 → 提取 `group(1)` 作为 `api_name`
   - logger.info 记录匹配结果
   - 返回 `ok(message=f"匹配到 API: {api_name}（...）", payload={...})`
9. **全文件无匹配** → logger.info 记录 → `fail("文件中未匹配到符合模式的 API")`
10. **意外异常**: 外层 try/except 兜底，返回 `fail(f"匹配过程发生意外错误: {error}")`

### 设计决策

- **逐行匹配**而非全文匹配：正则模式通常为行内模式（如 `http.HandlerFunc(...)`），逐行匹配更快且能提供行号
- **返回第一个匹配**：满足"单模式单结果"需求
- **正则预编译验证**：提前报错，避免扫描过程中才发现正则有误
- **仅使用 group(1)**：即使正则含多个捕获组，也只取第一个，行为明确可预期
- **payload.content 为 line.strip()**：与 `code_search.py` 的返回格式保持一致

## 错误处理

| 场景 | 处理方式 |
|------|---------|
| `file_path` 为空/空白 | `fail("文件路径不能为空")` |
| `pattern` 为空/空白 | `fail("匹配模式不能为空")` |
| 正则编译失败 | `fail(f"无效的正则表达式: {error}")` |
| 无捕获组 | `fail("正则表达式必须包含至少一个捕获组")` |
| 文件不存在 | `fail(f"文件不存在: {file_path}")` |
| 路径是目录 | `fail(f"{file_path} 是目录，不是文件")` |
| 文件读取失败 | `fail(f"文件读取失败: {error}")` |
| 无匹配 | `fail("文件中未匹配到符合模式的 API")` |
| 意外异常 | `fail(f"匹配过程发生意外错误: {error}")` |

所有错误通过 `fail()` 返回 JSON Envelope，不抛出异常（与 `code_search.py`、`config_reader.py` 保持一致）。

## 日志

使用 `logger = get_logger(__name__)` 记录关键事件：
- `logger.info`: 匹配成功（含 API 名称、文件、行号）
- `logger.info`: 无匹配
- `logger.error`: 文件不存在、正则无效等错误
- `logger.warning`: 文件编码 fallback（UTF-8 失败，使用 Latin-1）

## 测试策略

- 使用 `tmp_path` fixture 创建临时文件
- Mock `settings.code_space_dir` 指向 `tmp_path`
- 测试用例：
  1. 正常匹配：文件含 `http.HandlerFunc(DeleteResource)`，返回 `DeleteResource`
  2. 无匹配：文件不含匹配内容
  3. 无效正则：传入语法错误的正则
  4. 无捕获组：传入不含 `()` 的正则
  5. 文件不存在
  6. 空 pattern
  7. 空 file_path
  8. 多捕获组正则：验证只取 group(1)
