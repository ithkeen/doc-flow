"""doc_storage 工具测试。"""

import json

import pytest

from src.config import settings
from src.tools.doc_storage import save_document, read_document, list_documents


class TestSaveDocument:
    def test_saves_to_docs_output_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "docs_output_dir", str(tmp_path / "out"))

        result = json.loads(save_document.invoke({
            "module_name": "user",
            "api_name": "CreateUser",
            "content": "# Create User API",
        }))
        assert result["success"] is True
        assert (tmp_path / "out" / "user" / "CreateUser.md").read_text() == "# Create User API"

    def test_fails_on_empty_api_name(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "docs_output_dir", str(tmp_path / "out"))

        result = json.loads(save_document.invoke({
            "module_name": "user",
            "api_name": "",
            "content": "x",
        }))
        assert result["success"] is False

    def test_fails_on_invalid_module_name(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "docs_output_dir", str(tmp_path / "out"))

        result = json.loads(save_document.invoke({
            "module_name": "BAD!",
            "api_name": "Create",
            "content": "x",
        }))
        assert result["success"] is False

    def test_fails_on_empty_content(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "docs_output_dir", str(tmp_path / "out"))

        result = json.loads(save_document.invoke({
            "module_name": "user",
            "api_name": "Create",
            "content": "",
        }))
        assert result["success"] is False


class TestReadDocument:
    def test_reads_saved_document(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "docs_output_dir", str(tmp_path / "out"))

        doc_dir = tmp_path / "out" / "user"
        doc_dir.mkdir(parents=True)
        (doc_dir / "GetUser.md").write_text("# Get User")

        result = json.loads(read_document.invoke({
            "module_name": "user",
            "api_name": "GetUser",
        }))
        assert result["success"] is True
        assert result["payload"] == "# Get User"

    def test_fails_on_missing_document(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "docs_output_dir", str(tmp_path / "out"))

        result = json.loads(read_document.invoke({
            "module_name": "user",
            "api_name": "NoSuch",
        }))
        assert result["success"] is False


class TestListDocuments:
    def test_lists_module_documents(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "docs_output_dir", str(tmp_path / "out"))

        doc_dir = tmp_path / "out" / "order"
        doc_dir.mkdir(parents=True)
        (doc_dir / "ListOrders.md").write_text("# List Orders")
        (doc_dir / "CreateOrder.md").write_text("# Create Order")

        result = json.loads(list_documents.invoke({"module_name": "order"}))
        assert result["success"] is True
        assert "2" in result["message"]

    def test_lists_all_documents(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "docs_output_dir", str(tmp_path / "out"))

        for mod in ["user", "order"]:
            d = tmp_path / "out" / mod
            d.mkdir(parents=True)
            (d / "Api.md").write_text("# Api")

        result = json.loads(list_documents.invoke({"module_name": None}))
        assert result["success"] is True
        assert "2" in result["message"]

    def test_empty_when_no_docs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "docs_output_dir", str(tmp_path / "out"))

        result = json.loads(list_documents.invoke({"module_name": None}))
        assert result["success"] is True
        assert "没有" in result["message"]