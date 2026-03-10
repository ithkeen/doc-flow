"""code_scanner 工具测试。"""

import json

import pytest

from src.config import settings
from src.tools.code_scanner import scan_directory


class TestScanDirectory:
    def test_scans_under_agent_work_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        go_dir = tmp_path / "handler"
        go_dir.mkdir()
        (go_dir / "main.go").write_text("package handler")
        (go_dir / "main_test.go").write_text("package handler")

        result = json.loads(scan_directory.invoke({"directory_path": "handler"}))
        assert result["success"] is True
        assert "1" in result["message"]

    def test_fails_when_dir_not_in_work_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        result = json.loads(scan_directory.invoke({"directory_path": "no_such_dir"}))
        assert result["success"] is False

    def test_fails_when_path_is_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        (tmp_path / "a_file.txt").write_text("hello")

        result = json.loads(scan_directory.invoke({"directory_path": "a_file.txt"}))
        assert result["success"] is False

    def test_returns_no_go_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        (tmp_path / "subdir").mkdir()

        result = json.loads(scan_directory.invoke({"directory_path": "subdir"}))
        assert result["success"] is True
        assert "未发现" in result["message"]
