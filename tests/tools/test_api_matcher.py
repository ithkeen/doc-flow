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
