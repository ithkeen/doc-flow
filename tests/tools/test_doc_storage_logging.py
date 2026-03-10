"""doc_storage 日志测试。"""

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


class TestDocStorageLogging:
    def test_logs_error_on_empty_api_name(self, log_dir):
        config = LogSettings(_env_file=None, dir=log_dir)
        setup_logging(config)

        from src.tools.doc_storage import save_document

        save_document.invoke({"module_name": "user", "api_name": "", "content": "x"})

        lines = _read_log_lines(log_dir)
        error_lines = [l for l in lines if l["level"] == "ERROR"]
        assert len(error_lines) >= 1

    def test_logs_error_on_invalid_module_name(self, log_dir):
        config = LogSettings(_env_file=None, dir=log_dir)
        setup_logging(config)

        from src.tools.doc_storage import save_document

        save_document.invoke({"module_name": "BAD!", "api_name": "CreateUser", "content": "x"})

        lines = _read_log_lines(log_dir)
        error_lines = [l for l in lines if l["level"] == "ERROR"]
        assert len(error_lines) >= 1

    def test_logs_info_on_successful_save(self, log_dir, tmp_path, monkeypatch):
        config = LogSettings(_env_file=None, dir=log_dir)
        setup_logging(config)

        import src.tools.doc_storage as ds
        monkeypatch.setattr(ds, "DOCS_BASE_DIR", str(tmp_path / "docs"))

        ds.save_document.invoke({"module_name": "user", "api_name": "CreateUser", "content": "# API"})

        lines = _read_log_lines(log_dir)
        info_lines = [l for l in lines if l["level"] == "INFO"]
        assert len(info_lines) >= 1
        assert "CreateUser" in info_lines[0]["message"] or "user" in info_lines[0]["message"]

    def test_logs_error_on_save_exception(self, log_dir, tmp_path, monkeypatch):
        config = LogSettings(_env_file=None, dir=log_dir)
        setup_logging(config)

        import src.tools.doc_storage as ds
        monkeypatch.setattr(ds, "DOCS_BASE_DIR", "/nonexistent/readonly/path")

        ds.save_document.invoke({"module_name": "user", "api_name": "Create", "content": "x"})

        lines = _read_log_lines(log_dir)
        error_lines = [l for l in lines if l["level"] == "ERROR"]
        assert len(error_lines) >= 1

    def test_logs_info_on_successful_read(self, log_dir, tmp_path, monkeypatch):
        config = LogSettings(_env_file=None, dir=log_dir)
        setup_logging(config)

        import src.tools.doc_storage as ds
        monkeypatch.setattr(ds, "DOCS_BASE_DIR", str(tmp_path / "docs"))

        doc_dir = tmp_path / "docs" / "user"
        doc_dir.mkdir(parents=True)
        (doc_dir / "GetUser.md").write_text("# Get User")

        ds.read_document.invoke({"module_name": "user", "api_name": "GetUser"})

        lines = _read_log_lines(log_dir)
        info_lines = [l for l in lines if l["level"] == "INFO"]
        assert len(info_lines) >= 1

    def test_logs_info_on_list_documents(self, log_dir, tmp_path, monkeypatch):
        config = LogSettings(_env_file=None, dir=log_dir)
        setup_logging(config)

        import src.tools.doc_storage as ds
        monkeypatch.setattr(ds, "DOCS_BASE_DIR", str(tmp_path / "docs"))

        doc_dir = tmp_path / "docs" / "order"
        doc_dir.mkdir(parents=True)
        (doc_dir / "ListOrders.md").write_text("# List Orders")

        ds.list_documents.invoke({"module_name": "order"})

        lines = _read_log_lines(log_dir)
        info_lines = [l for l in lines if l["level"] == "INFO"]
        assert len(info_lines) >= 1
