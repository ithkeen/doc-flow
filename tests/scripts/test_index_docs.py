"""Tests for batch indexing script."""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def docs_dir(tmp_path):
    """Create a temp docs directory with sample markdown files."""
    # project_a/module_x/GetUser.md
    api_dir = tmp_path / "project_a" / "module_x"
    api_dir.mkdir(parents=True)
    (api_dir / "GetUser.md").write_text("# GetUser\n\nGet user by ID.", encoding="utf-8")
    (api_dir / "CreateUser.md").write_text("# CreateUser\n\nCreate a new user.", encoding="utf-8")

    # project_a/module_y/ListOrders.md
    api_dir2 = tmp_path / "project_a" / "module_y"
    api_dir2.mkdir(parents=True)
    (api_dir2 / "ListOrders.md").write_text("# ListOrders\n\nList all orders.", encoding="utf-8")

    return tmp_path


def test_collect_md_files(docs_dir):
    """collect_md_files finds all .md files recursively."""
    from scripts.index_docs import collect_md_files
    files = collect_md_files(docs_dir)
    assert len(files) == 3
    names = {f.name for f in files}
    assert names == {"GetUser.md", "CreateUser.md", "ListOrders.md"}


def test_build_metadata(docs_dir):
    """build_metadata extracts project, module, api_name from path."""
    from scripts.index_docs import build_metadata
    file_path = docs_dir / "project_a" / "module_x" / "GetUser.md"
    meta = build_metadata(file_path, docs_dir)
    assert meta["source"] == "project_a/module_x/GetUser.md"
    assert meta["project"] == "project_a"
    assert meta["module"] == "module_x"
    assert meta["api_name"] == "GetUser"


def test_index_single_file(docs_dir):
    """--file flag indexes only the specified file."""
    from scripts.index_docs import collect_single_file
    file_path = collect_single_file("project_a/module_x/GetUser.md", docs_dir)
    assert file_path.name == "GetUser.md"
    assert file_path.exists()


def test_index_single_file_not_found(docs_dir):
    """--file with nonexistent path raises FileNotFoundError."""
    from scripts.index_docs import collect_single_file
    with pytest.raises(FileNotFoundError):
        collect_single_file("nonexistent/Api.md", docs_dir)
