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
