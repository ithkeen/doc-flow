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
