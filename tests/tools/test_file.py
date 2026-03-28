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
