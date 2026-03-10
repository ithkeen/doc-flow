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
