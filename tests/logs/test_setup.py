"""setup_logging 集成测试。"""

import json
import logging
from logging.handlers import TimedRotatingFileHandler
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
        file_handlers = [
            h for h in root.handlers if isinstance(h, TimedRotatingFileHandler)
        ]
        assert len(file_handlers) == 1
