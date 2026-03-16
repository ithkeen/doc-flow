"""Tests for INDEX.md management."""

import pytest
from pathlib import Path

from src.generator.index import IndexEntry, BlacklistEntry, Index


class TestIndexLoad:
    def test_load_empty_file(self, tmp_path):
        index_path = tmp_path / "INDEX.md"
        index_path.write_text("# test 项目 API 文档索引\n", encoding="utf-8")
        idx = Index(index_path)
        idx.load()
        assert idx.entries == {}
        assert idx.blacklist_entries == []

    def test_load_nonexistent_creates_empty(self, tmp_path):
        index_path = tmp_path / "INDEX.md"
        idx = Index(index_path)
        idx.load()
        assert idx.entries == {}

    def test_load_with_entries(self, tmp_path):
        content = (
            "# test 项目 API 文档索引\n\n"
            "## order\n\n"
            "| API | 源码位置 | 文档位置 | 生成时间 |\n"
            "|-----|---------|---------|--------|\n"
            "| CreateOrder | order/logic/create.go:45 | order/CreateOrder.md | 2026-03-14 10:30 |\n"
            "| QueryOrder | order/handler/query.go:12 | order/QueryOrder.md | 2026-03-14 10:31 |\n"
        )
        index_path = tmp_path / "INDEX.md"
        index_path.write_text(content, encoding="utf-8")
        idx = Index(index_path)
        idx.load()
        assert "order" in idx.entries
        assert len(idx.entries["order"]) == 2
        assert idx.entries["order"][0].api_name == "CreateOrder"
        assert idx.entries["order"][0].source_location == "order/logic/create.go:45"

    def test_load_with_blacklist(self, tmp_path):
        content = (
            "# test 项目 API 文档索引\n\n"
            "## 黑名单\n\n"
            "| API | 源码位置 | 原因 |\n"
            "|-----|---------|------|\n"
            "| HealthCheck | common/health.go:5 | 内部健康检查接口 |\n"
        )
        index_path = tmp_path / "INDEX.md"
        index_path.write_text(content, encoding="utf-8")
        idx = Index(index_path)
        idx.load()
        assert len(idx.blacklist_entries) == 1
        assert idx.blacklist_entries[0].api_name == "HealthCheck"

    def test_load_malformed_index_warns_and_resets(self, tmp_path):
        index_path = tmp_path / "INDEX.md"
        index_path.write_text("totally invalid content\n||||\n", encoding="utf-8")
        idx = Index(index_path)
        idx.load()
        assert idx.entries == {}


class TestIndexQuery:
    def test_has_entry_true(self, tmp_path):
        idx = Index(tmp_path / "INDEX.md")
        idx.entries["order"] = [IndexEntry("CreateOrder", "order/create.go:45", "order/CreateOrder.md", "2026-03-14 10:30")]
        assert idx.has_entry("CreateOrder", "order/create.go:45") is True

    def test_has_entry_false_different_location(self, tmp_path):
        idx = Index(tmp_path / "INDEX.md")
        idx.entries["order"] = [IndexEntry("CreateOrder", "order/create.go:45", "order/CreateOrder.md", "2026-03-14 10:30")]
        assert idx.has_entry("CreateOrder", "order/create.go:99") is False

    def test_has_entry_false_not_exists(self, tmp_path):
        idx = Index(tmp_path / "INDEX.md")
        assert idx.has_entry("CreateOrder", "order/create.go:45") is False


class TestIndexMutations:
    def test_add_entry(self, tmp_path):
        idx = Index(tmp_path / "INDEX.md")
        entry = IndexEntry("CreateOrder", "order/create.go:45", "order/CreateOrder.md", "2026-03-14 10:30")
        idx.add_or_replace_entry("order", entry)
        assert len(idx.entries["order"]) == 1

    def test_replace_entry(self, tmp_path):
        idx = Index(tmp_path / "INDEX.md")
        old = IndexEntry("CreateOrder", "order/create.go:45", "order/CreateOrder.md", "2026-03-14 10:30")
        new = IndexEntry("CreateOrder", "order/create.go:45", "order/CreateOrder.md", "2026-03-15 11:00")
        idx.add_or_replace_entry("order", old)
        idx.add_or_replace_entry("order", new)
        assert len(idx.entries["order"]) == 1
        assert idx.entries["order"][0].generated_at == "2026-03-15 11:00"

    def test_sync_blacklist(self, tmp_path):
        idx = Index(tmp_path / "INDEX.md")
        bl = [BlacklistEntry("HealthCheck", "common/health.go:5", "内部接口")]
        idx.sync_blacklist(bl)
        assert len(idx.blacklist_entries) == 1


class TestIndexSave:
    def test_roundtrip(self, tmp_path):
        index_path = tmp_path / "INDEX.md"
        idx = Index(index_path, project_name="access")
        idx.add_or_replace_entry("order", IndexEntry("CreateOrder", "order/create.go:45", "order/CreateOrder.md", "2026-03-14 10:30"))
        idx.add_or_replace_entry("user", IndexEntry("GetUserInfo", "user/info.go:30", "user/GetUserInfo.md", "2026-03-14 10:32"))
        idx.sync_blacklist([BlacklistEntry("HealthCheck", "common/health.go:5", "内部接口")])
        idx.save()

        idx2 = Index(index_path)
        idx2.load()
        assert len(idx2.entries["order"]) == 1
        assert idx2.entries["order"][0].api_name == "CreateOrder"
        assert len(idx2.entries["user"]) == 1
        assert len(idx2.blacklist_entries) == 1

    def test_pipe_escaping(self, tmp_path):
        index_path = tmp_path / "INDEX.md"
        idx = Index(index_path, project_name="test")
        idx.add_or_replace_entry("mod", IndexEntry("Handler", "file.go:1", "mod/Handler.md", "2026-03-14 10:30"))
        idx.sync_blacklist([BlacklistEntry("Bad|Func", "file.go:2", "reason with | pipe")])
        idx.save()

        raw = index_path.read_text(encoding="utf-8")
        assert r"Bad\|Func" in raw
        assert r"reason with \| pipe" in raw

        idx2 = Index(index_path)
        idx2.load()
        assert idx2.blacklist_entries[0].api_name == "Bad|Func"
        assert idx2.blacklist_entries[0].reason == "reason with | pipe"
