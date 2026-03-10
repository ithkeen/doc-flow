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
    if any(isinstance(h, TimedRotatingFileHandler) for h in root_logger.handlers):
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
