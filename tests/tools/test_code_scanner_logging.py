"""code_scanner 日志测试。"""

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


class TestCodeScannerLogging:
    def test_logs_error_on_nonexistent_directory(self, log_dir, tmp_path):
        config = LogSettings(_env_file=None, dir=log_dir)
        setup_logging(config)

        from src.tools.code_scanner import scan_directory

        scan_directory.invoke({"directory_path": str(tmp_path / "no_such_dir")})

        lines = _read_log_lines(log_dir)
        error_lines = [l for l in lines if l["level"] == "ERROR"]
        assert len(error_lines) >= 1
        assert "no_such_dir" in error_lines[0]["message"]

    def test_logs_error_on_not_a_directory(self, log_dir, tmp_path):
        config = LogSettings(_env_file=None, dir=log_dir)
        setup_logging(config)

        a_file = tmp_path / "a_file.txt"
        a_file.write_text("hello")

        from src.tools.code_scanner import scan_directory

        scan_directory.invoke({"directory_path": str(a_file)})

        lines = _read_log_lines(log_dir)
        error_lines = [l for l in lines if l["level"] == "ERROR"]
        assert len(error_lines) >= 1

    def test_logs_info_on_successful_scan(self, log_dir, tmp_path):
        config = LogSettings(_env_file=None, dir=log_dir)
        setup_logging(config)

        go_file = tmp_path / "main.go"
        go_file.write_text("package main")

        from src.tools.code_scanner import scan_directory

        scan_directory.invoke({"directory_path": str(tmp_path)})

        lines = _read_log_lines(log_dir)
        info_lines = [l for l in lines if l["level"] == "INFO"]
        assert len(info_lines) >= 1
        assert "1" in info_lines[0]["message"]
