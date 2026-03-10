"""git_ops 日志测试。"""

import json
import logging
from pathlib import Path

import pytest

from src.logs import setup_logging
from src.config.settings import LogSettings


@pytest.fixture(autouse=True)
def _reset_logging():
    yield
    root = logging.getLogger()
    for handler in root.handlers[:]:
        handler.close()
        root.removeHandler(handler)
    root.setLevel(logging.WARNING)


@pytest.fixture()
def log_dir(tmp_path):
    d = tmp_path / "logs"
    d.mkdir()
    return str(d) + "/"


def _read_log_lines(log_dir: str) -> list[dict]:
    log_file = list(Path(log_dir).glob("*.log"))[0]
    content = log_file.read_text().strip()
    return [json.loads(line) for line in content.split("\n") if line]


class TestGitOpsLogging:
    def test_logs_error_on_not_a_repo(self, log_dir, tmp_path):
        config = LogSettings(_env_file=None, dir=log_dir)
        setup_logging(config)

        from src.tools.git_ops import git_diff

        git_diff.invoke({"repo_path": str(tmp_path)})

        lines = _read_log_lines(log_dir)
        error_lines = [l for l in lines if l["level"] == "ERROR"]
        assert len(error_lines) >= 1

    def test_logs_error_on_missing_last_commit(self, log_dir, tmp_path):
        config = LogSettings(_env_file=None, dir=log_dir)
        setup_logging(config)

        (tmp_path / ".git").mkdir()

        from src.tools.git_ops import git_diff

        git_diff.invoke({"repo_path": str(tmp_path)})

        lines = _read_log_lines(log_dir)
        error_lines = [l for l in lines if l["level"] == "ERROR"]
        assert len(error_lines) >= 1

    def test_logs_error_on_empty_last_commit(self, log_dir, tmp_path):
        config = LogSettings(_env_file=None, dir=log_dir)
        setup_logging(config)

        (tmp_path / ".git").mkdir()
        (tmp_path / ".last_commit").write_text("")

        from src.tools.git_ops import git_diff

        git_diff.invoke({"repo_path": str(tmp_path)})

        lines = _read_log_lines(log_dir)
        error_lines = [l for l in lines if l["level"] == "ERROR"]
        assert len(error_lines) >= 1

    def test_logs_info_on_successful_diff(self, log_dir, tmp_path):
        """需要一个真实的 git 仓库来测试成功路径。"""
        config = LogSettings(_env_file=None, dir=log_dir)
        setup_logging(config)

        import subprocess

        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
        (tmp_path / "a.go").write_text("package main")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

        result = subprocess.run(
            ["git", "rev-parse", "HEAD~0"],
            cwd=tmp_path, capture_output=True, text=True,
        )
        first_commit = result.stdout.strip()

        (tmp_path / "b.go").write_text("package main")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add b"], cwd=tmp_path, capture_output=True)

        (tmp_path / ".last_commit").write_text(first_commit)

        from src.tools.git_ops import git_diff

        git_diff.invoke({"repo_path": str(tmp_path)})

        lines = _read_log_lines(log_dir)
        info_lines = [l for l in lines if l["level"] == "INFO"]
        assert len(info_lines) >= 1
        assert "1" in info_lines[0]["message"]
