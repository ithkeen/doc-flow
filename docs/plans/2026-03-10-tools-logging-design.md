# Tools 模块日志接入设计

## 背景

`src/tools/` 下的工具代码在日志模块 (`src/logs/`) 实现之前编写，未接入日志。需要在工具代码的关键位置添加结构化日志。

## 方案

**方案 A：模块级 logger**（已选定）

每个工具模块独立获取 logger，在各自的错误处理和关键操作处添加日志调用。

### 原则

- 每个工具文件顶部：`from src.logs import get_logger` + `logger = get_logger(__name__)`
- 日志级别：`error` 用于异常/失败，`warning` 用于降级行为，`info` 用于关键操作成功
- `except` 块中使用 `exc_info=True` 保留完整堆栈
- `utils.py` 不加日志（纯数据构造函数）

## 日志点位

### code_scanner.py

| 位置 | 级别 | 内容 |
|------|------|------|
| 目录不存在/非目录 | error | 无效路径 |
| 扫描成功 | info | 目录路径 + 文件数量 |

### doc_storage.py

| 位置 | 级别 | 内容 |
|------|------|------|
| 参数校验失败 | error | 具体无效参数 |
| save 异常 | error | exc_info=True |
| save 成功 | info | 文件路径 |
| read 异常 | error | exc_info=True |
| read 成功 | info | 文件路径 |
| list 结果 | info | 文档数量 |

### file_reader.py

| 位置 | 级别 | 内容 |
|------|------|------|
| 文件不存在 | error | 路径 |
| 编码回退 | warning | 路径 + 编码 |
| 读取异常 | error | exc_info=True |
| 读取成功 | info | 路径 + 大小 |

### git_ops.py

| 位置 | 级别 | 内容 |
|------|------|------|
| .last_commit 不存在 | error | 路径 |
| 子进程超时 | error | 命令 + 超时时间 |
| git 未找到 | error | FileNotFoundError |
| 非零返回码 | error | returncode + stderr |
| 处理异常 | error | exc_info=True |
| diff 成功 | info | 变更文件数量 |
