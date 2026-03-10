"""git_ops 工具测试。"""

import json
import subprocess

import pytest

from src.config import settings
from src.tools.git_ops import git_diff


class TestGitDiff:
    def test_fails_when_not_a_repo(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        result = json.loads(git_diff.invoke({"repo_path": "."}))
        assert result["success"] is False

    def test_fails_when_no_last_commit(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        (tmp_path / ".git").mkdir()

        result = json.loads(git_diff.invoke({"repo_path": "."}))
        assert result["success"] is False

    def test_fails_when_last_commit_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        (tmp_path / ".git").mkdir()
        (tmp_path / ".last_commit").write_text("")

        result = json.loads(git_diff.invoke({"repo_path": "."}))
        assert result["success"] is False

    def test_successful_diff(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "agent_work_dir", str(tmp_path))

        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, capture_output=True)
        (tmp_path / "a.go").write_text("package main")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

        first = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True
        ).stdout.strip()

        (tmp_path / "b.go").write_text("package main")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add b"], cwd=tmp_path, capture_output=True)

        (tmp_path / ".last_commit").write_text(first)

        result = json.loads(git_diff.invoke({"repo_path": "."}))
        assert result["success"] is True
        assert "1" in result["message"]
