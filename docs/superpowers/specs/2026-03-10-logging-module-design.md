# 日志模块设计文档

## 概述

为 doc-flow 项目实现应用级运维日志模块，用于记录程序运行状态和异常信息。Agent 执行链路追踪由 LangSmith 负责，本模块不涉及。

## 需求总结

| 项目 | 决策 |
|------|------|
| 用途 | 应用级运维日志（INFO/WARNING/ERROR 等） |
| 输出目标 | 仅文件（项目根目录 `logs/`） |
| 轮转策略 | 按时间轮转，每天一个文件，保留最近 7 天 |
| 日志格式 | JSON |
| 配置方式 | 融入现有 Pydantic Settings，通过 `.env` 配置 |
| 使用方式 | `get_logger(name)` 工厂函数，各模块独立 logger |
| 外部依赖 | 无，纯标准库 `logging` 实现 |

## 模块结构

代码位于 `src/logs/`，日志文件输出到项目根目录 `logs/`。

```
src/logs/
├── __init__.py      # 导出 get_logger, setup_logging
├── formatter.py     # JSONFormatter 类
└── setup.py         # 日志初始化逻辑（handler、轮转策略）
```

## 配置集成

在 `src/config/settings.py` 中新增 `LogSettings`：

```python
class LogSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOG_", extra="ignore")

    level: str = "INFO"
    dir: str = "logs/"
    backup_count: int = 7
```

在根 `Settings` 中通过 `Field(default_factory=LogSettings)` 组合，与现有 `LLMSettings`、`LangSmithSettings` 模式一致。

对应 `.env` 变量：

```
LOG_LEVEL=INFO
LOG_DIR=logs/
LOG_BACKUP_COUNT=7
```

## JSON 日志格式

```json
{
  "time": "2026-03-10T14:30:00.123",
  "level": "INFO",
  "module": "src.tools.file_reader",
  "message": "文件读取成功",
  "error": "traceback内容（仅异常时存在）"
}
```

- `time` — ISO 格式时间戳，精确到毫秒
- `level` — 日志级别
- `module` — logger name（通过 `__name__` 传入）
- `message` — 日志消息
- `error` — 仅异常时附带 traceback，正常日志不包含此字段

## JSONFormatter

继承 `logging.Formatter`，重写 `format()` 方法，将 LogRecord 序列化为 JSON 字符串。约 20 行代码。

## 使用方式

### 初始化（应用启动时调用一次）

```python
from src.config import settings
from src.logs import setup_logging

setup_logging(settings.log)
```

### 各模块中使用

```python
from src.logs import get_logger

logger = get_logger(__name__)

logger.info("文件读取成功")
logger.error("读取失败", exc_info=True)
```

## 技术决策

- **纯标准库实现**：JSON 格式需求简单，自定义 Formatter 即可，无需引入 `python-json-logger`
- **工厂函数模式**：各模块通过 `get_logger(__name__)` 获取独立 logger，方便按模块区分日志来源和调整日志级别
- **TimedRotatingFileHandler**：标准库内置，按天轮转 + 自动清理旧文件
