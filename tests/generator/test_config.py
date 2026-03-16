"""Tests for .docflow.yaml config parsing."""

import pytest
import yaml
from pathlib import Path

from src.generator.config import ProjectConfig, load_project_config


class TestProjectConfigValidation:
    def test_minimal_valid_config(self):
        data = {
            "discovery": {
                "source_root": "access",
                "patterns": [{"regex": r"Register\(.+,\s*(\w+)\)"}],
            }
        }
        config = ProjectConfig(**data)
        assert config.discovery.source_root == "access"
        assert len(config.discovery.patterns) == 1
        assert config.modules == []
        assert config.blacklist.functions == []
        assert config.blacklist.files == []

    def test_full_config(self):
        data = {
            "discovery": {
                "source_root": "access",
                "patterns": [{"regex": r"RegisterHTTPTaskHandle\(.+,\s*(\w+)\)"}],
            },
            "modules": [
                {"match": "order/**", "module": "order"},
                {"match": "user/**", "module": "user"},
            ],
            "blacklist": {
                "functions": [{"name": "HealthCheck", "reason": "\u5185\u90e8\u63a5\u53e3"}],
                "files": [{"path": "debug.go", "reason": "\u8c03\u8bd5\u6587\u4ef6"}],
            },
        }
        config = ProjectConfig(**data)
        assert len(config.modules) == 2
        assert config.modules[0].module == "order"
        assert len(config.blacklist.functions) == 1
        assert config.blacklist.functions[0].name == "HealthCheck"

    def test_missing_discovery_fails(self):
        with pytest.raises(Exception):
            ProjectConfig(**{})

    def test_missing_source_root_fails(self):
        with pytest.raises(Exception):
            ProjectConfig(**{"discovery": {"patterns": [{"regex": r"(\w+)"}]}})

    def test_empty_patterns_fails(self):
        with pytest.raises(Exception):
            ProjectConfig(**{"discovery": {"source_root": "access", "patterns": []}})

    def test_invalid_regex_fails(self):
        with pytest.raises(Exception):
            ProjectConfig(**{"discovery": {"source_root": "access", "patterns": [{"regex": r"[invalid"}]}})

    def test_regex_without_capture_group_fails(self):
        with pytest.raises(Exception):
            ProjectConfig(**{"discovery": {"source_root": "access", "patterns": [{"regex": r"Register\w+"}]}})

    def test_invalid_module_name_fails(self):
        with pytest.raises(Exception):
            ProjectConfig(**{
                "discovery": {"source_root": "access", "patterns": [{"regex": r"(\w+)"}]},
                "modules": [{"match": "order/**", "module": "Order"}],
            })


class TestLoadProjectConfig:
    def test_load_valid_yaml(self, tmp_path):
        config_data = {"discovery": {"source_root": "myproject", "patterns": [{"regex": r"Handle\((\w+)\)"}]}}
        config_file = tmp_path / ".docflow.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")
        config = load_project_config(config_file)
        assert config.discovery.source_root == "myproject"

    def test_load_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_project_config(tmp_path / "nonexistent.yaml")

    def test_load_invalid_yaml_raises(self, tmp_path):
        config_file = tmp_path / ".docflow.yaml"
        config_file.write_text(": invalid: yaml: [", encoding="utf-8")
        with pytest.raises(Exception):
            load_project_config(config_file)
