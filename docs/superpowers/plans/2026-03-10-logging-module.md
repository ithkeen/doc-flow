# 日志模块实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 doc-flow 实现应用级运维日志模块，JSON 格式输出到文件，按天轮转保留 7 天。

**Architecture:** 日志模块代码在 `src/logs/`，由三个文件组成：`formatter.py`（JSON 格式化器）、`setup.py`（handler 配置与初始化）、`__init__.py`（对外 API）。配置通过 `LogSettings` 融入现有 Pydantic Settings 体系。日志文件输出到项目根目录 `logs/`。

**Tech Stack:** Python 3.11 标准库 `logging`、`logging.handlers.TimedRotatingFileHandler`、`json`；Pydantic Settings v2。

**Spec:** `docs/superpowers/specs/2026-03-10-logging-module-design.md`

---

## File Structure

| 操作 | 文件路径 | 职责 |
|------|----------|------|
| Create | `src/logs/__init__.py` | 导出 `get_logger`、`setup_logging` |
| Create | `src/logs/formatter.py` | `JSONFormatter` 类 — 将 LogRecord 序列化为 JSON |
| Create | `src/logs/setup.py` | `setup_logging(config)` — 配置 root logger、handler、轮转 |
| Modify | `src/config/settings.py` | 新增 `LogSettings` 类，在 `Settings` 中组合 |
| Modify | `.env.example` | 新增 `LOG_*` 环境变量示例 |
| Create | `tests/logs/__init__.py` | 测试包 |
| Create | `tests/logs/test_formatter.py` | JSONFormatter 单元测试 |
| Create | `tests/logs/test_setup.py` | setup_logging 集成测试 |
| Create | `tests/config/test_log_settings.py` | LogSettings 配置测试 |

---

## Chunk 1: 配置与格式化器

### Task 1: 在 Settings 中新增 LogSettings

**Files:**
- Modify: `src/config/settings.py:34` (在 `LangSmithSettings` 之后插入)
- Create: `tests/config/test_log_settings.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/config/test_log_settings.py`：

```python
"""LogSettings 单元测试。"""

import pytest
from pydantic import ValidationError

from src.config.settings import LogSettings, Settings


class TestLogSettings:
    """LogSettings 配置测试。"""

    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        monkeypatch.delenv("LOG_DIR", raising=False)
        monkeypatch.delenv("LOG_BACKUP_COUNT", raising=False)

        s = LogSettings(_env_file=None)
        assert s.level == "INFO"
        assert s.dir == "logs/"
        assert s.backup_count == 7

    def test_loads_from_env(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("LOG_DIR", "/var/log/docflow/")
        monkeypatch.setenv("LOG_BACKUP_COUNT", "14")

        s = LogSettings(_env_file=None)
        assert s.level == "DEBUG"
        assert s.dir == "/var/log/docflow/"
        assert s.backup_count == 14

    def test_settings_includes_log(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        s = Settings(_env_file=None)
        assert s.log.level == "INFO"
        assert s.log.dir == "logs/"
        assert s.log.backup_count == 7
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/ithkeen/CodeSpace/agent-project/doc-flow && python -m pytest tests/config/test_log_settings.py -v`
Expected: FAIL — `ImportError: cannot import name 'LogSettings'`

- [ ] **Step 3: 实现 LogSettings**

在 `src/config/settings.py` 的 `LangSmithSettings` 类之后、`Settings` 类之前，插入：

```python
class LogSettings(BaseSettings):
    """日志配置。"""

    model_config = SettingsConfigDict(
        env_prefix="LOG_",
        env_file=_ENV_FILE,
        extra="ignore",
    )

    level: str = "INFO"
    dir: str = "logs/"
    backup_count: int = 7
```

在 `Settings` 类中添加 `log` 字段：

```python
log: LogSettings = Field(default_factory=LogSettings)
```

在 `Settings.__init__` 中添加 `log` 的 `_env_file` 传递：

```python
if "log" not in kwargs:
    kwargs["log"] = LogSettings(_env_file=env_file)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/ithkeen/CodeSpace/agent-project/doc-flow && python -m pytest tests/config/test_log_settings.py -v`
Expected: 3 passed

- [ ] **Step 5: 更新 .env.example**

在 `.env.example` 末尾追加：

```
# 日志配置
LOG_LEVEL=INFO
LOG_DIR=logs/
LOG_BACKUP_COUNT=7
```

- [ ] **Step 6: 运行全部已有测试确认无回归**

Run: `cd /Users/ithkeen/CodeSpace/agent-project/doc-flow && python -m pytest tests/ -v`
Expected: 所有测试通过

- [ ] **Step 7: 提交**

```bash
git add src/config/settings.py tests/config/test_log_settings.py .env.example
git commit -m "feat(config): add LogSettings for logging module"
```

---

### Task 2: 实现 JSONFormatter

**Files:**
- Create: `src/logs/formatter.py`
- Create: `tests/logs/__init__.py`
- Create: `tests/logs/test_formatter.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/logs/__init__.py`（空文件）。

创建 `tests/logs/test_formatter.py`：

```python
"""JSONFormatter 单元测试。"""

import json
import logging
import sys

from src.logs.formatter import JSONFormatter


class TestJSONFormatter:
    """JSON 格式化器测试。"""

    def _make_record(self, msg: str, level: int = logging.INFO) -> logging.LogRecord:
        return logging.LogRecord(
            name="test.module",
            level=level,
            pathname="test.py",
            lineno=1,
            msg=msg,
            args=(),
            exc_info=None,
        )

    def test_basic_format(self):
        formatter = JSONFormatter()
        record = self._make_record("测试消息")
        result = json.loads(formatter.format(record))

        assert result["level"] == "INFO"
        assert result["module"] == "test.module"
        assert result["message"] == "测试消息"
        assert "time" in result
        assert "error" not in result

    def test_error_level(self):
        formatter = JSONFormatter()
        record = self._make_record("错误消息", logging.ERROR)
        result = json.loads(formatter.format(record))

        assert result["level"] == "ERROR"
        assert result["message"] == "错误消息"

    def test_exception_info(self):
        formatter = JSONFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            record = self._make_record("异常发生")
            record.exc_info = sys.exc_info()

        result = json.loads(formatter.format(record))

        assert "error" in result
        assert "ValueError: test error" in result["error"]

    def test_time_format_iso(self):
        formatter = JSONFormatter()
        record = self._make_record("时间测试")
        result = json.loads(formatter.format(record))

        # ISO 格式包含 T 分隔符
        assert "T" in result["time"]

    def test_output_is_valid_json(self):
        formatter = JSONFormatter()
        record = self._make_record("JSON 有效性测试")
        output = formatter.format(record)

        # 不应抛出异常
        parsed = json.loads(output)
        assert isinstance(parsed, dict)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/ithkeen/CodeSpace/agent-project/doc-flow && python -m pytest tests/logs/test_formatter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.logs.formatter'`

- [ ] **Step 3: 实现 JSONFormatter**

创建 `src/logs/__init__.py`（暂时空文件，Task 4 再填充）。

创建 `src/logs/formatter.py`：

```python
"""JSON 日志格式化器。"""

import json
import logging
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """将 LogRecord 格式化为 JSON 字符串。

    输出字段：time, level, module, message, error（仅异常时）。
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "time": datetime.fromtimestamp(
                record.created, tz=timezone.utc,
            ).astimezone().isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info and record.exc_info[1] is not None:
            log_entry["error"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/ithkeen/CodeSpace/agent-project/doc-flow && python -m pytest tests/logs/test_formatter.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add src/logs/__init__.py src/logs/formatter.py tests/logs/__init__.py tests/logs/test_formatter.py
git commit -m "feat(logs): implement JSONFormatter"
```

---

## Chunk 2: 初始化与集成

### Task 3: 实现 setup_logging

**Files:**
- Create: `src/logs/setup.py`
- Create: `tests/logs/test_setup.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/logs/test_setup.py`：

```python
"""setup_logging 集成测试。"""

import json
import logging
import os
from pathlib import Path

import pytest

from src.config.settings import LogSettings
from src.logs.setup import setup_logging


@pytest.fixture(autouse=True)
def _reset_logging():
    """每个测试后重置 root logger，避免 handler 累积。"""
    yield
    root = logging.getLogger()
    for handler in root.handlers[:]:
        handler.close()
        root.removeHandler(handler)
    root.setLevel(logging.WARNING)


@pytest.fixture()
def log_dir(tmp_path):
    """返回一个临时日志目录路径。"""
    d = tmp_path / "logs"
    d.mkdir()
    return str(d) + "/"


class TestSetupLogging:
    """日志初始化测试。"""

    def test_creates_log_file(self, log_dir):
        config = LogSettings(_env_file=None, dir=log_dir)
        setup_logging(config)

        logger = logging.getLogger("test.setup")
        logger.info("创建文件测试")

        log_files = list(Path(log_dir).glob("*.log"))
        assert len(log_files) == 1

    def test_log_output_is_json(self, log_dir):
        config = LogSettings(_env_file=None, dir=log_dir)
        setup_logging(config)

        logger = logging.getLogger("test.json")
        logger.info("JSON 格式测试")

        log_file = list(Path(log_dir).glob("*.log"))[0]
        line = log_file.read_text().strip().split("\n")[0]
        data = json.loads(line)

        assert data["level"] == "INFO"
        assert data["module"] == "test.json"
        assert data["message"] == "JSON 格式测试"

    def test_respects_log_level(self, log_dir):
        config = LogSettings(_env_file=None, dir=log_dir, level="WARNING")
        setup_logging(config)

        logger = logging.getLogger("test.level")
        logger.info("不应出现")
        logger.warning("应该出现")

        log_file = list(Path(log_dir).glob("*.log"))[0]
        content = log_file.read_text().strip()
        lines = [l for l in content.split("\n") if l]

        assert len(lines) == 1
        assert "应该出现" in lines[0]

    def test_creates_log_dir_if_missing(self, tmp_path):
        log_dir = str(tmp_path / "nonexistent" / "logs") + "/"
        config = LogSettings(_env_file=None, dir=log_dir)
        setup_logging(config)

        logger = logging.getLogger("test.mkdir")
        logger.info("目录创建测试")

        assert Path(log_dir).exists()

    def test_no_duplicate_handlers_on_repeat_call(self, log_dir):
        config = LogSettings(_env_file=None, dir=log_dir)
        setup_logging(config)
        setup_logging(config)

        logger = logging.getLogger("test.dup")
        logger.info("重复调用测试")

        log_file = list(Path(log_dir).glob("*.log"))[0]
        content = log_file.read_text().strip()
        lines = [l for l in content.split("\n") if l]

        assert len(lines) == 1

        root = logging.getLogger()
        assert len(root.handlers) == 1
```

- [ ] **Step 2: 运行测试确认失败**

Expected: FAIL — `ModuleNotFoundError: No module named 'src.logs.setup'`

- [ ] **Step 3: 实现 setup_logging**

创建 `src/logs/setup.py`：

```python
"""日志初始化。

配置 root logger：TimedRotatingFileHandler + JSONFormatter。
按天轮转，保留指定天数的日志文件。
"""

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from src.config.settings import LogSettings
from src.logs.formatter import JSONFormatter

_LOG_FILENAME = "app.log"


def setup_logging(config: LogSettings) -> None:
    """初始化日志系统。

    Args:
        config: LogSettings 配置实例。
    """
    root_logger = logging.getLogger()

    # 防止重复调用时叠加 handler
    if root_logger.handlers:
        return

    root_logger.setLevel(config.level.upper())

    log_dir = Path(config.dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    handler = TimedRotatingFileHandler(
        filename=log_dir / _LOG_FILENAME,
        when="midnight",
        backupCount=config.backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(JSONFormatter())

    root_logger.addHandler(handler)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/ithkeen/CodeSpace/agent-project/doc-flow && python -m pytest tests/logs/test_setup.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add src/logs/setup.py tests/logs/test_setup.py
git commit -m "feat(logs): implement setup_logging with timed rotation"
```

---

### Task 4: 完成 `src/logs/__init__.py` 导出

**Files:**
- Modify: `src/logs/__init__.py`

- [ ] **Step 1: 实现模块导出**

更新 `src/logs/__init__.py`：

```python
"""日志模块。

提供 JSON 格式的应用级运维日志，按天轮转，保留指定天数。

Usage::

    from src.logs import setup_logging, get_logger
    from src.config import settings

    setup_logging(settings.log)  # 应用启动时调用一次

    logger = get_logger(__name__)
    logger.info("操作成功")
"""

import logging

from src.logs.setup import setup_logging


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的 logger 实例。

    Args:
        name: logger 名称，通常传入 __name__。

    Returns:
        logging.Logger 实例。
    """
    return logging.getLogger(name)


__all__ = ["setup_logging", "get_logger"]
```

- [ ] **Step 2: 运行全部测试确认无回归**

Run: `cd /Users/ithkeen/CodeSpace/agent-project/doc-flow && python -m pytest tests/ -v`
Expected: 所有测试通过

- [ ] **Step 3: 提交**

```bash
git add src/logs/__init__.py
git commit -m "feat(logs): expose get_logger and setup_logging in __init__"
```

---

### Task 5: 将 `logs/` 加入 `.gitignore`

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: 在 `.gitignore` 中添加日志文件目录**

在 `.gitignore` 中追加：

```
# 日志文件
logs/
```

- [ ] **Step 2: 提交**

```bash
git add .gitignore
git commit -m "chore: add logs/ to .gitignore"
```
