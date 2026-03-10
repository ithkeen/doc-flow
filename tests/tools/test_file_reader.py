"""file_reader 工具测试。"""

import json

import pytest

from src.config import settings
from src.tools.file_reader import read_file


class TestReadFile:
    def test_reads_file_under_agent_work_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        (tmp_path / "main.go").write_text("package main", encoding="utf-8")

        result = json.loads(read_file.invoke({"file_path": "main.go"}))
        assert result["success"] is True
        assert result["payload"] == "package main"

    def test_fails_when_file_not_exists(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        result = json.loads(read_file.invoke({"file_path": "ghost.go"}))
        assert result["success"] is False

    def test_fails_when_path_is_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        (tmp_path / "subdir").mkdir()

        result = json.loads(read_file.invoke({"file_path": "subdir"}))
        assert result["success"] is False

    def test_encoding_fallback_latin1(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        bad_file = tmp_path / "bad.go"
        bad_file.write_bytes(b"\x80\x81\x82 content")

        result = json.loads(read_file.invoke({"file_path": "bad.go"}))
        assert result["success"] is True

    def test_truncates_large_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        big_file = tmp_path / "big.go"
        big_file.write_text("x" * (200 * 1024), encoding="utf-8")

        result = json.loads(read_file.invoke({"file_path": "big.go"}))
        assert result["success"] is True
        assert "截取" in result["message"]
