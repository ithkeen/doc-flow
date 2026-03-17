"""Tests for src.tools.api_matcher."""

import json
from unittest.mock import patch

import pytest


@pytest.fixture()
def code_dir(tmp_path):
    """Create a temporary code_space_dir and patch settings."""
    with patch("src.tools.api_matcher.settings") as mock_settings:
        mock_settings.code_space_dir = str(tmp_path)
        yield tmp_path


def test_match_api_name_happy_path(code_dir):
    """Normal match: file contains http.HandlerFunc(DeleteResource)."""
    from src.tools.api_matcher import match_api_name

    go_file = code_dir / "router.go"
    go_file.write_text(
        'package main\n\nimport "net/http"\n\n'
        "func init() {\n"
        "    http.HandlerFunc(DeleteResource)\n"
        "}\n",
        encoding="utf-8",
    )

    result_str = match_api_name.invoke(
        {
            "file_path": "router.go",
            "pattern": r"http\.HandlerFunc\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)",
        }
    )
    result = json.loads(result_str)

    assert result["success"] is True
    assert result["payload"]["api_name"] == "DeleteResource"
    assert result["payload"]["file"] == "router.go"
    assert result["payload"]["line"] == 6
    assert "DeleteResource" in result["payload"]["content"]


def test_empty_file_path(code_dir):
    """Empty file_path returns fail."""
    from src.tools.api_matcher import match_api_name

    result = json.loads(match_api_name.invoke({"file_path": "  ", "pattern": r"(\w+)"}))
    assert result["success"] is False
    assert "文件路径不能为空" in result["error"]


def test_empty_pattern(code_dir):
    """Empty pattern returns fail."""
    from src.tools.api_matcher import match_api_name

    (code_dir / "a.go").write_text("x", encoding="utf-8")
    result = json.loads(match_api_name.invoke({"file_path": "a.go", "pattern": ""}))
    assert result["success"] is False
    assert "匹配模式不能为空" in result["error"]


def test_invalid_regex(code_dir):
    """Invalid regex returns fail."""
    from src.tools.api_matcher import match_api_name

    (code_dir / "a.go").write_text("x", encoding="utf-8")
    result = json.loads(match_api_name.invoke({"file_path": "a.go", "pattern": r"(["}))
    assert result["success"] is False
    assert "无效的正则表达式" in result["error"]


def test_no_capture_group(code_dir):
    """Pattern without capture group returns fail."""
    from src.tools.api_matcher import match_api_name

    (code_dir / "a.go").write_text("hello", encoding="utf-8")
    result = json.loads(match_api_name.invoke({"file_path": "a.go", "pattern": r"hello"}))
    assert result["success"] is False
    assert "捕获组" in result["error"]


def test_file_not_found(code_dir):
    """Non-existent file returns fail."""
    from src.tools.api_matcher import match_api_name

    result = json.loads(
        match_api_name.invoke({"file_path": "no_such.go", "pattern": r"(\w+)"})
    )
    assert result["success"] is False
    assert "文件不存在" in result["error"]


def test_path_is_directory(code_dir):
    """Directory path returns fail."""
    from src.tools.api_matcher import match_api_name

    subdir = code_dir / "subdir"
    subdir.mkdir()
    result = json.loads(match_api_name.invoke({"file_path": "subdir", "pattern": r"(\w+)"}))
    assert result["success"] is False
    assert "目录" in result["error"]


def test_no_match(code_dir):
    """File with no matching content returns fail."""
    from src.tools.api_matcher import match_api_name

    (code_dir / "empty.go").write_text("package main\n", encoding="utf-8")
    result = json.loads(
        match_api_name.invoke(
            {
                "file_path": "empty.go",
                "pattern": r"http\.HandlerFunc\(\s*([a-zA-Z_]\w*)\s*\)",
            }
        )
    )
    assert result["success"] is False
    assert "未匹配到" in result["error"]


def test_multiple_capture_groups_uses_first(code_dir):
    """When pattern has multiple capture groups, only group(1) is used."""
    from src.tools.api_matcher import match_api_name

    (code_dir / "multi.go").write_text(
        "route.Handle(GET, /api/v1, Handler)\n", encoding="utf-8"
    )
    # Two capture groups: (GET) and (Handler)
    result = json.loads(
        match_api_name.invoke(
            {
                "file_path": "multi.go",
                "pattern": r"route\.Handle\((\w+),\s*\S+,\s*(\w+)\)",
            }
        )
    )
    assert result["success"] is True
    assert result["payload"]["api_name"] == "GET"
