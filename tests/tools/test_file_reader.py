"""file_reader 工具测试。"""

import json

import pytest

from src.config import settings
from src.config.settings import Settings
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


class TestReadFileIntegration:
    """集成测试：使用真实 .env 配置，不 mock，直接读取文件并打印结果。"""

    def test_read_real_file(self):
        s = Settings()
        file_path = "ubill-order/main.go"

        print(f"\n========== file_reader 集成测试 ==========")
        print(f"AGENT_WORK_DIR: {s.agent_work_dir}")
        print(f"读取文件: {file_path}")

        result = json.loads(read_file.invoke({"file_path": file_path}))

        print(f"success: {result['success']}")
        print(f"message: {result['message']}")
        if result.get("payload"):
            preview = result["payload"][:500]
            print(f"payload (前500字符):\n{preview}")
            if len(result["payload"]) > 500:
                print(f"... (共 {len(result['payload'])} 字符)")
        else:
            print("payload: (empty)")
        print("===========================================")
