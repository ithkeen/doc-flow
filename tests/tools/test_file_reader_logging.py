"""file_reader 日志测试。"""

import json
import logging
from pathlib import Path

import pytest

from src.logs import setup_logging
from src.config.settings import LogSettings


@pytest.fixture(autouse=True)
def _reset_logging():
    yield
    root = logging.getLogger()
    for handler in root.handlers[:]:
        handler.close()
        root.removeHandler(handler)
    root.setLevel(logging.WARNING)


@pytest.fixture()
def log_dir(tmp_path):
    d = tmp_path / "logs"
    d.mkdir()
    return str(d) + "/"


def _read_log_lines(log_dir: str) -> list[dict]:
    log_file = list(Path(log_dir).glob("*.log"))[0]
    content = log_file.read_text().strip()
    return [json.loads(line) for line in content.split("\n") if line]


class TestFileReaderLogging:
    def test_logs_error_on_nonexistent_file(self, log_dir, tmp_path):
        config = LogSettings(_env_file=None, dir=log_dir)
        setup_logging(config)

        from src.tools.file_reader import read_file

        read_file.invoke({"file_path": str(tmp_path / "ghost.go")})

        lines = _read_log_lines(log_dir)
        error_lines = [l for l in lines if l["level"] == "ERROR"]
        assert len(error_lines) >= 1
        assert "ghost.go" in error_lines[0]["message"]

    def test_logs_warning_on_encoding_fallback(self, log_dir, tmp_path):
        config = LogSettings(_env_file=None, dir=log_dir)
        setup_logging(config)

        bad_file = tmp_path / "bad_encoding.go"
        bad_file.write_bytes(b"\x80\x81\x82 some content")

        from src.tools.file_reader import read_file

        read_file.invoke({"file_path": str(bad_file)})

        lines = _read_log_lines(log_dir)
        warn_lines = [l for l in lines if l["level"] == "WARNING"]
        assert len(warn_lines) >= 1

    def test_logs_info_on_successful_read(self, log_dir, tmp_path):
        config = LogSettings(_env_file=None, dir=log_dir)
        setup_logging(config)

        go_file = tmp_path / "main.go"
        go_file.write_text("package main", encoding="utf-8")

        from src.tools.file_reader import read_file

        read_file.invoke({"file_path": str(go_file)})

        lines = _read_log_lines(log_dir)
        info_lines = [l for l in lines if l["level"] == "INFO"]
        assert len(info_lines) >= 1
        assert "main.go" in info_lines[0]["message"]
