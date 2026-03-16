"""Tests for API discovery."""

import pytest
from pathlib import Path

from src.generator.discovery import DiscoveredAPI, discover_apis, resolve_module
from src.generator.config import DiscoveryPattern, ModuleMapping


class TestDiscoverAPIs:
    def _write_go_file(self, path: Path, content: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_discover_single_api(self, tmp_path):
        self._write_go_file(
            tmp_path / "handler.go",
            'package main\n\nfunc init() {\n\tRegister("create", CreateOrder)\n}\n',
        )
        patterns = [DiscoveryPattern(regex=r'Register\(.+,\s*(\w+)\)')]
        apis = discover_apis(tmp_path, patterns)
        assert len(apis) == 1
        assert apis[0].function_name == "CreateOrder"
        assert apis[0].source_file == "handler.go"

    def test_discover_multiple_apis_same_file(self, tmp_path):
        self._write_go_file(
            tmp_path / "handler.go",
            'package main\n\nfunc init() {\n\tRegister("create", CreateOrder)\n\tRegister("query", QueryOrder)\n}\n',
        )
        patterns = [DiscoveryPattern(regex=r'Register\(.+,\s*(\w+)\)')]
        apis = discover_apis(tmp_path, patterns)
        assert len(apis) == 2
        names = {a.function_name for a in apis}
        assert names == {"CreateOrder", "QueryOrder"}

    def test_discover_across_subdirectories(self, tmp_path):
        self._write_go_file(
            tmp_path / "order" / "handler.go",
            'package order\n\nfunc init() {\n\tRegister("create", CreateOrder)\n}\n',
        )
        self._write_go_file(
            tmp_path / "user" / "handler.go",
            'package user\n\nfunc init() {\n\tRegister("info", GetUserInfo)\n}\n',
        )
        patterns = [DiscoveryPattern(regex=r'Register\(.+,\s*(\w+)\)')]
        apis = discover_apis(tmp_path, patterns)
        assert len(apis) == 2

    def test_skips_test_files(self, tmp_path):
        self._write_go_file(
            tmp_path / "handler_test.go",
            'package main\n\nfunc init() {\n\tRegister("test", TestHandler)\n}\n',
        )
        patterns = [DiscoveryPattern(regex=r'Register\(.+,\s*(\w+)\)')]
        apis = discover_apis(tmp_path, patterns)
        assert len(apis) == 0

    def test_empty_capture_group_skipped(self, tmp_path):
        self._write_go_file(
            tmp_path / "handler.go",
            'package main\n\nfunc init() {\n\tRegister("create", )\n}\n',
        )
        patterns = [DiscoveryPattern(regex=r'Register\(.+,\s*(\w*)\)')]
        apis = discover_apis(tmp_path, patterns)
        assert len(apis) == 0

    def test_multiple_patterns(self, tmp_path):
        self._write_go_file(
            tmp_path / "handler.go",
            'package main\n\nfunc init() {\n\tRegisterHTTP("create", CreateOrder)\n\tRegisterGRPC("query", QueryOrder)\n}\n',
        )
        patterns = [
            DiscoveryPattern(regex=r'RegisterHTTP\(.+,\s*(\w+)\)'),
            DiscoveryPattern(regex=r'RegisterGRPC\(.+,\s*(\w+)\)'),
        ]
        apis = discover_apis(tmp_path, patterns)
        assert len(apis) == 2

    def test_same_function_in_multiple_files(self, tmp_path):
        self._write_go_file(tmp_path / "a.go", 'package main\n\nfunc init() {\n\tRegister("a", Handler)\n}\n')
        self._write_go_file(tmp_path / "b.go", 'package main\n\nfunc init() {\n\tRegister("b", Handler)\n}\n')
        patterns = [DiscoveryPattern(regex=r'Register\(.+,\s*(\w+)\)')]
        apis = discover_apis(tmp_path, patterns)
        assert len(apis) == 2

    def test_no_go_files(self, tmp_path):
        apis = discover_apis(tmp_path, [DiscoveryPattern(regex=r'(\w+)')])
        assert apis == []


class TestResolveModule:
    def test_match_first_rule(self):
        mappings = [ModuleMapping(match="order/**", module="order"), ModuleMapping(match="user/**", module="user")]
        assert resolve_module("order/logic/create.go", mappings) == "order"

    def test_match_second_rule(self):
        mappings = [ModuleMapping(match="order/**", module="order"), ModuleMapping(match="user/**", module="user")]
        assert resolve_module("user/handler.go", mappings) == "user"

    def test_no_match_uses_first_dir(self):
        mappings = [ModuleMapping(match="order/**", module="order")]
        assert resolve_module("payment/handler.go", mappings) == "payment"

    def test_no_match_root_file_uses_root(self):
        mappings = [ModuleMapping(match="order/**", module="order")]
        assert resolve_module("handler.go", mappings) == "_root"

    def test_empty_mappings_uses_first_dir(self):
        assert resolve_module("order/logic/create.go", []) == "order"
