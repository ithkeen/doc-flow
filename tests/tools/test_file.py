# tests/tools/test_file.py
"""Tests for list_directory and find_files tools in src.tools.file."""

import json
from unittest.mock import patch

import pytest


@pytest.fixture()
def code_dir(tmp_path):
    """Create a temporary code_space_dir and patch settings."""
    with patch("src.tools.file.settings") as mock_settings:
        mock_settings.code_space_dir = str(tmp_path)
        mock_settings.docs_space_dir = str(tmp_path / "docs")
        yield tmp_path


class TestListDirectory:
    def test_lists_files_and_dirs(self, code_dir):
        """list_directory returns files and dirs with correct types."""
        from src.tools.file import list_directory

        (code_dir / "proj").mkdir()
        (code_dir / "proj" / "main.go").write_text("package main", encoding="utf-8")
        (code_dir / "proj" / "cmd").mkdir()

        result = json.loads(list_directory.invoke({"path": "proj"}))

        assert result["success"] is True
        entries = result["payload"]
        names = {e["name"] for e in entries}
        assert "main.go" in names
        assert "cmd" in names

        file_entry = next(e for e in entries if e["name"] == "main.go")
        assert file_entry["type"] == "file"
        assert "size" in file_entry

        dir_entry = next(e for e in entries if e["name"] == "cmd")
        assert dir_entry["type"] == "dir"

    def test_excludes_noise_dirs(self, code_dir):
        """list_directory excludes .git, node_modules, vendor, __pycache__."""
        from src.tools.file import list_directory

        proj = code_dir / "proj"
        proj.mkdir()
        (proj / ".git").mkdir()
        (proj / "node_modules").mkdir()
        (proj / "vendor").mkdir()
        (proj / "__pycache__").mkdir()
        (proj / "src").mkdir()

        result = json.loads(list_directory.invoke({"path": "proj"}))

        assert result["success"] is True
        names = {e["name"] for e in result["payload"]}
        assert ".git" not in names
        assert "node_modules" not in names
        assert "vendor" not in names
        assert "__pycache__" not in names
        assert "src" in names

    def test_nonexistent_path(self, code_dir):
        """list_directory returns fail for nonexistent path."""
        from src.tools.file import list_directory

        result = json.loads(list_directory.invoke({"path": "nonexistent"}))

        assert result["success"] is False
        assert "不存在" in result["error"]

    def test_max_depth_two(self, code_dir):
        """list_directory with max_depth=2 includes subdirectory contents."""
        from src.tools.file import list_directory

        proj = code_dir / "proj"
        (proj / "cmd").mkdir(parents=True)
        (proj / "cmd" / "main.go").write_text("package main", encoding="utf-8")

        result = json.loads(list_directory.invoke({"path": "proj", "max_depth": 2}))

        assert result["success"] is True
        entries = result["payload"]
        cmd_entry = next(e for e in entries if e["name"] == "cmd")
        assert "children" in cmd_entry
        child_names = {c["name"] for c in cmd_entry["children"]}
        assert "main.go" in child_names

    def test_empty_directory(self, code_dir):
        """list_directory returns empty list for empty dir."""
        from src.tools.file import list_directory

        (code_dir / "empty").mkdir()

        result = json.loads(list_directory.invoke({"path": "empty"}))

        assert result["success"] is True
        assert result["payload"] == []

    def test_truncates_large_directory(self, code_dir):
        """list_directory truncates when entries exceed 200."""
        from src.tools.file import list_directory

        proj = code_dir / "proj"
        proj.mkdir()
        for i in range(210):
            (proj / f"file_{i:03d}.go").write_text("package main", encoding="utf-8")

        result = json.loads(list_directory.invoke({"path": "proj"}))

        assert result["success"] is True
        assert len(result["payload"]) == 200
        assert "截断" in result["message"]


class TestFindFiles:
    def test_finds_go_files(self, code_dir):
        """find_files returns matching .go files."""
        from src.tools.file import find_files

        proj = code_dir / "proj"
        (proj / "cmd").mkdir(parents=True)
        (proj / "cmd" / "main.go").write_text("package main", encoding="utf-8")
        (proj / "cmd" / "README.md").write_text("# readme", encoding="utf-8")

        result = json.loads(find_files.invoke({"directory": "proj", "pattern": "**/*.go"}))

        assert result["success"] is True
        assert "proj/cmd/main.go" in result["payload"]
        assert not any(f.endswith(".md") for f in result["payload"])

    def test_finds_by_name(self, code_dir):
        """find_files matches specific filename patterns."""
        from src.tools.file import find_files

        proj = code_dir / "proj"
        (proj / "svc1" / "cmd").mkdir(parents=True)
        (proj / "svc2" / "cmd").mkdir(parents=True)
        (proj / "svc1" / "cmd" / "main.go").write_text("package main", encoding="utf-8")
        (proj / "svc2" / "cmd" / "main.go").write_text("package main", encoding="utf-8")

        result = json.loads(find_files.invoke({"directory": "proj", "pattern": "**/main.go"}))

        assert result["success"] is True
        assert len(result["payload"]) == 2

    def test_excludes_noise_dirs(self, code_dir):
        """find_files excludes .git, vendor, etc."""
        from src.tools.file import find_files

        proj = code_dir / "proj"
        (proj / "src").mkdir(parents=True)
        (proj / "vendor" / "lib").mkdir(parents=True)
        (proj / "src" / "main.go").write_text("package main", encoding="utf-8")
        (proj / "vendor" / "lib" / "dep.go").write_text("package lib", encoding="utf-8")

        result = json.loads(find_files.invoke({"directory": "proj", "pattern": "**/*.go"}))

        assert result["success"] is True
        paths = result["payload"]
        assert any("src/main.go" in p for p in paths)
        assert not any("vendor" in p for p in paths)

    def test_empty_result(self, code_dir):
        """find_files returns empty list when no match."""
        from src.tools.file import find_files

        (code_dir / "proj").mkdir()

        result = json.loads(find_files.invoke({"directory": "proj", "pattern": "**/*.go"}))

        assert result["success"] is True
        assert result["payload"] == []

    def test_nonexistent_directory(self, code_dir):
        """find_files returns fail for nonexistent directory."""
        from src.tools.file import find_files

        result = json.loads(find_files.invoke({"directory": "nonexistent", "pattern": "*.go"}))

        assert result["success"] is False

    def test_truncates_large_result(self, code_dir):
        """find_files truncates results exceeding 100 files."""
        from src.tools.file import find_files

        proj = code_dir / "proj"
        proj.mkdir()
        for i in range(110):
            (proj / f"file_{i:03d}.go").write_text("package main", encoding="utf-8")

        result = json.loads(find_files.invoke({"directory": "proj", "pattern": "*.go"}))

        assert result["success"] is True
        assert len(result["payload"]) == 100
        assert "截断" in result["message"]

    def test_expands_brace_syntax(self, code_dir):
        """find_files expands {yaml,yml,json} brace syntax (Python glob has no brace expansion)."""
        from src.tools.file import find_files

        proj = code_dir / "proj"
        deploy = proj / "deploy"
        deploy.mkdir(parents=True)
        (deploy / "config.yaml").write_text("key: value", encoding="utf-8")
        (deploy / "app.yml").write_text("env: prod", encoding="utf-8")
        (deploy / "db.json").write_text('{"host":"localhost"}', encoding="utf-8")

        result = json.loads(find_files.invoke({"directory": "proj", "pattern": "**/deploy/**/*.{yaml,yml,json}"}))

        assert result["success"] is True
        paths = result["payload"]
        assert any(p.endswith(".yaml") for p in paths)
        assert any(p.endswith(".yml") for p in paths)
        assert any(p.endswith(".json") for p in paths)
