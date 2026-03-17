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
- `langchain.tools.tool`
- `src.config.settings`（获取 `code_space_dir`）
- `src.logs.get_logger`
- `src.tools.utils.ok`, `src.tools.utils.fail`

## 接口定义

```python
@tool
def match_api_name(file_path: str, pattern: str) -> str:
    """在 code_space_dir 下指定文件中，使用正则表达式匹配 API 名称。

    Args:
        file_path: 相对于 code_space_dir 的文件路径，如 "ubill-access-api/router.go"
        pattern: 正则表达式字符串，必须包含一个捕获组，捕获组即为 API 名称

    Returns:
        JSON Envelope 格式的响应字符串
    """
```

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `file_path` | `str` | 相对于 `code_space_dir` 的文件路径 |
| `pattern` | `str` | 正则表达式，必须包含至少一个捕获组 |

### 返回值

成功时 payload 结构：

```json
{
  "api_name": "DeleteResource",
  "file": "ubill-access-api/router.go",
  "line": 42,
  "match": "http.HandlerFunc(DeleteResource)"
}
```

## 核心逻辑流程

1. **验证 pattern**: `re.compile(pattern)`，失败则 `fail("无效的正则表达式: ...")`
2. **验证捕获组**: `compiled.groups >= 1`，否则 `fail("正则表达式必须包含至少一个捕获组")`
3. **构建绝对路径**: `Path(settings.code_space_dir) / file_path`
4. **验证文件**: 文件存在且非目录
5. **读取文件内容**: UTF-8 编码，fallback Latin-1
6. **逐行匹配**: `re.search(compiled, line)`
   - 第一个命中 → 提取 `group(1)` 作为 `api_name`
   - 返回 `ok()`，payload 含 `api_name`、`file`、`line`、`match`
7. **无匹配** → `fail("文件中未匹配到符合模式的 API")`

### 设计决策

- **逐行匹配**而非全文匹配：正则模式通常为行内模式，逐行匹配更快且能提供行号
- **返回第一个匹配**：满足"单模式单结果"需求
- **正则预编译验证**：提前报错，避免扫描过程中才发现正则有误

## 错误处理

| 场景 | 处理方式 |
|------|---------|
| `pattern` 为空 | `fail("匹配模式不能为空")` |
| 正则编译失败 | `fail(f"无效的正则表达式: {error}")` |
| 无捕获组 | `fail("正则表达式必须包含至少一个捕获组")` |
| 文件不存在 | `fail(f"文件不存在: {file_path}")` |
| 路径是目录 | `fail(f"{file_path} 是目录，不是文件")` |
| 文件读取失败 | `fail(f"文件读取失败: {error}")` |
| 无匹配 | `fail("文件中未匹配到符合模式的 API")` |

所有错误通过 `fail()` 返回 JSON Envelope，不抛出异常（与 `code_search.py`、`config_reader.py` 保持一致）。

## 测试策略

- 使用 `tmp_path` fixture 创建临时 Go 文件
- Mock `settings.code_space_dir` 指向 `tmp_path`
- 测试用例：
  1. 正常匹配：文件含 `http.HandlerFunc(DeleteResource)`，返回 `DeleteResource`
  2. 无匹配：文件不含匹配内容
  3. 无效正则：传入语法错误的正则
  4. 无捕获组：传入不含 `()` 的正则
  5. 文件不存在
  6. 空 pattern
