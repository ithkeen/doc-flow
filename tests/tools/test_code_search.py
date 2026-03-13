"""code_search 工具测试。"""

import json

from src.config import settings
from src.tools.code_search import find_function


class TestFindFunction:
    def test_finds_plain_function(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        go_dir = tmp_path / "service"
        go_dir.mkdir()
        (go_dir / "buy.go").write_text(
            "package service\n\nfunc buyResourcePostPaid(ctx context.Context) error {\n\treturn nil\n}\n"
        )

        result = json.loads(find_function.invoke({"function_name": "buyResourcePostPaid", "directory": "service"}))
        assert result["success"] is True
        assert isinstance(result["payload"], list)
        assert len(result["payload"]) == 1
        assert result["payload"][0]["file"].endswith("service/buy.go")
        assert result["payload"][0]["line"] == 3
        assert "buyResourcePostPaid" in result["payload"][0]["content"]

    def test_finds_method_with_receiver(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        go_dir = tmp_path / "service"
        go_dir.mkdir()
        (go_dir / "svc.go").write_text(
            "package service\n\nfunc (s *Service) ProcessOrder(ctx context.Context) error {\n\treturn nil\n}\n"
        )

        result = json.loads(find_function.invoke({"function_name": "ProcessOrder", "directory": "service"}))
        assert result["success"] is True
        assert isinstance(result["payload"], list)
        assert len(result["payload"]) == 1
        assert result["payload"][0]["line"] == 3
        assert "ProcessOrder" in result["payload"][0]["content"]

    def test_returns_fail_when_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        go_dir = tmp_path / "service"
        go_dir.mkdir()
        (go_dir / "empty.go").write_text("package service\n")

        result = json.loads(find_function.invoke({"function_name": "nonExistent", "directory": "service"}))
        assert result["success"] is False
        assert "nonExistent" in result["error"]

    def test_excludes_test_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        go_dir = tmp_path / "service"
        go_dir.mkdir()
        (go_dir / "buy_test.go").write_text(
            "package service\n\nfunc TestBuy(t *testing.T) {\n}\n"
        )

        result = json.loads(find_function.invoke({"function_name": "TestBuy", "directory": "service"}))
        assert result["success"] is False

    def test_fails_when_directory_not_exists(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        result = json.loads(find_function.invoke({"function_name": "Foo", "directory": "no_such_dir"}))
        assert result["success"] is False
        assert "不存在" in result["error"]

    def test_fails_when_path_is_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        (tmp_path / "a_file.txt").write_text("hello")

        result = json.loads(find_function.invoke({"function_name": "Foo", "directory": "a_file.txt"}))
        assert result["success"] is False
        assert "不是一个目录" in result["error"]

    def test_handles_regex_special_chars_in_name(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        go_dir = tmp_path / "service"
        go_dir.mkdir()
        (go_dir / "main.go").write_text("package service\n\nfunc normalFunc() {}\n")

        result = json.loads(find_function.invoke({"function_name": "foo.*bar", "directory": "service"}))
        assert result["success"] is False

    def test_handles_non_utf8_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        go_dir = tmp_path / "service"
        go_dir.mkdir()
        (go_dir / "binary.go").write_bytes(b"package service\n\nfunc Target() {}\n\xff\xfe")

        result = json.loads(find_function.invoke({"function_name": "Target", "directory": "service"}))
        assert result["success"] is True
        assert isinstance(result["payload"], list)
        assert len(result["payload"]) == 1
        assert result["payload"][0]["line"] == 3

    def test_returns_all_matches_across_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        pkg_a = tmp_path / "pkg_a"
        pkg_a.mkdir()
        (pkg_a / "handler.go").write_text(
            "package pkg_a\n\nfunc BuyResource(ctx context.Context) error {\n\treturn nil\n}\n"
        )

        pkg_b = tmp_path / "pkg_b"
        pkg_b.mkdir()
        (pkg_b / "handler.go").write_text(
            "package pkg_b\n\nfunc BuyResource(ctx context.Context) error {\n\treturn nil\n}\n"
        )

        result = json.loads(find_function.invoke({"function_name": "BuyResource"}))
        assert result["success"] is True
        assert isinstance(result["payload"], list)
        assert len(result["payload"]) == 2
        files = {m["file"] for m in result["payload"]}
        assert any("pkg_a" in f for f in files)
        assert any("pkg_b" in f for f in files)
