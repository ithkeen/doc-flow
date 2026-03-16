"""Tests for generator runner orchestration."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from src.generator.runner import filter_apis, build_blacklist_entries
from src.generator.config import BlacklistConfig, BlacklistFunction, BlacklistFile
from src.generator.discovery import DiscoveredAPI
from src.generator.index import Index, IndexEntry, BlacklistEntry


@pytest.fixture
def sample_apis():
    return [
        DiscoveredAPI("CreateOrder", "order/create.go", 45),
        DiscoveredAPI("QueryOrder", "order/query.go", 12),
        DiscoveredAPI("HealthCheck", "common/health.go", 5),
        DiscoveredAPI("DebugHandler", "order/internal/debug.go", 10),
    ]


@pytest.fixture
def sample_blacklist():
    return BlacklistConfig(
        functions=[BlacklistFunction(name="HealthCheck", reason="内部接口")],
        files=[BlacklistFile(path="order/internal/debug.go", reason="调试文件")],
    )


class TestFilterAPIs:
    def test_filter_removes_blacklisted_functions(self, sample_apis, sample_blacklist):
        idx = Index(Path("/tmp/INDEX.md"))
        result = filter_apis(sample_apis, sample_blacklist, idx, force=False)
        names = {a.function_name for a in result}
        assert "HealthCheck" not in names

    def test_filter_removes_blacklisted_files(self, sample_apis, sample_blacklist):
        idx = Index(Path("/tmp/INDEX.md"))
        result = filter_apis(sample_apis, sample_blacklist, idx, force=False)
        names = {a.function_name for a in result}
        assert "DebugHandler" not in names

    def test_filter_removes_existing_index_entries(self, sample_apis, sample_blacklist):
        idx = Index(Path("/tmp/INDEX.md"))
        idx.entries["order"] = [
            IndexEntry("CreateOrder", "order/create.go:45", "order/CreateOrder.md", "2026-03-14 10:30")
        ]
        result = filter_apis(sample_apis, sample_blacklist, idx, force=False)
        names = {a.function_name for a in result}
        assert "CreateOrder" not in names
        assert "QueryOrder" in names

    def test_filter_force_ignores_index(self, sample_apis, sample_blacklist):
        idx = Index(Path("/tmp/INDEX.md"))
        idx.entries["order"] = [
            IndexEntry("CreateOrder", "order/create.go:45", "order/CreateOrder.md", "2026-03-14 10:30")
        ]
        result = filter_apis(sample_apis, sample_blacklist, idx, force=True)
        names = {a.function_name for a in result}
        assert "CreateOrder" in names
        assert "HealthCheck" not in names

    def test_filter_keeps_non_blacklisted(self, sample_apis, sample_blacklist):
        idx = Index(Path("/tmp/INDEX.md"))
        result = filter_apis(sample_apis, sample_blacklist, idx, force=False)
        names = {a.function_name for a in result}
        assert "CreateOrder" in names
        assert "QueryOrder" in names


class TestBuildBlacklistEntries:
    def test_build_from_config_and_apis(self, sample_apis, sample_blacklist):
        entries = build_blacklist_entries(sample_blacklist, sample_apis)
        assert len(entries) == 2
        names = {e.api_name for e in entries}
        assert "HealthCheck" in names
        assert "DebugHandler" in names

    def test_function_blacklist_with_source(self, sample_apis, sample_blacklist):
        entries = build_blacklist_entries(sample_blacklist, sample_apis)
        hc = next(e for e in entries if e.api_name == "HealthCheck")
        assert hc.source_location == "common/health.go:5"

    def test_file_blacklist_entries(self, sample_apis, sample_blacklist):
        entries = build_blacklist_entries(sample_blacklist, sample_apis)
        dh = next(e for e in entries if e.api_name == "DebugHandler")
        assert "调试文件" in dh.reason
