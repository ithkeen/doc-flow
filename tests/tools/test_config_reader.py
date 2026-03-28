"""Tests for src.tools.config_reader Pydantic models."""

import json
from unittest.mock import patch

import pytest
import yaml


@pytest.fixture()
def docs_dir(tmp_path):
    """Create a temporary docs_space_dir and patch settings."""
    with patch("src.tools.config_reader.settings") as mock_settings:
        mock_settings.docs_space_dir = str(tmp_path)
        yield tmp_path


def _write_config(docs_dir, project: str, config: dict) -> str:
    """Write a .doc_gen.yaml and return the config_path."""
    project_dir = docs_dir / project
    project_dir.mkdir(parents=True, exist_ok=True)
    config_file = project_dir / ".doc_gen.yaml"
    config_file.write_text(yaml.dump(config), encoding="utf-8")
    return f"{project}/.doc_gen.yaml"


def test_new_format_with_type(docs_dir):
    """Mapping values as {name, type} objects are parsed correctly."""
    from src.tools.config_reader import load_docgen_config

    config_path = _write_config(docs_dir, "proj", {
        "modules": {
            "mapping": {
                "proj/api/logic": {"name": "order", "type": "api"},
                "proj/cron/handler": {"name": "sync", "type": "cron"},
                "proj/mq/handler": {"name": "events", "type": "mq"},
            }
        },
        "search_rules": {
            "function_patterns": [r"func\s+(\w+)"],
            "struct_patterns": [r"type\s+(\w+)\s+struct"],
        },
    })

    result = json.loads(load_docgen_config.invoke({"config_path": config_path}))

    assert result["success"] is True
    mapping = result["payload"]["modules"]["mapping"]
    assert mapping["proj/api/logic"] == {"name": "order", "type": "api"}
    assert mapping["proj/cron/handler"] == {"name": "sync", "type": "cron"}
    assert mapping["proj/mq/handler"] == {"name": "events", "type": "mq"}


def test_backward_compat_string_format(docs_dir):
    """Plain string mapping values are normalized to {name: str, type: 'api'}."""
    from src.tools.config_reader import load_docgen_config

    config_path = _write_config(docs_dir, "proj", {
        "modules": {
            "mapping": {
                "proj/logic": "order",
            }
        },
        "search_rules": {
            "function_patterns": [r"func\s+(\w+)"],
            "struct_patterns": [r"type\s+(\w+)\s+struct"],
        },
    })

    result = json.loads(load_docgen_config.invoke({"config_path": config_path}))

    assert result["success"] is True
    mapping = result["payload"]["modules"]["mapping"]
    assert mapping["proj/logic"] == {"name": "order", "type": "api"}


def test_mixed_format(docs_dir):
    """Mixing string and object values in the same mapping works."""
    from src.tools.config_reader import load_docgen_config

    config_path = _write_config(docs_dir, "proj", {
        "modules": {
            "mapping": {
                "proj/api/logic": "order",
                "proj/cron/handler": {"name": "sync", "type": "cron"},
            }
        },
        "search_rules": {
            "function_patterns": [r"func\s+(\w+)"],
            "struct_patterns": [r"type\s+(\w+)\s+struct"],
        },
    })

    result = json.loads(load_docgen_config.invoke({"config_path": config_path}))

    assert result["success"] is True
    mapping = result["payload"]["modules"]["mapping"]
    assert mapping["proj/api/logic"] == {"name": "order", "type": "api"}
    assert mapping["proj/cron/handler"] == {"name": "sync", "type": "cron"}


def test_type_defaults_to_api(docs_dir):
    """Object mapping without explicit type defaults to 'api'."""
    from src.tools.config_reader import load_docgen_config

    config_path = _write_config(docs_dir, "proj", {
        "modules": {
            "mapping": {
                "proj/logic": {"name": "order"},
            }
        },
        "search_rules": {
            "function_patterns": [r"func\s+(\w+)"],
            "struct_patterns": [r"type\s+(\w+)\s+struct"],
        },
    })

    result = json.loads(load_docgen_config.invoke({"config_path": config_path}))

    assert result["success"] is True
    mapping = result["payload"]["modules"]["mapping"]
    assert mapping["proj/logic"] == {"name": "order", "type": "api"}


def test_empty_mapping_rejected(docs_dir):
    """Empty mapping dict is rejected."""
    from src.tools.config_reader import load_docgen_config

    config_path = _write_config(docs_dir, "proj", {
        "modules": {"mapping": {}},
        "search_rules": {
            "function_patterns": [r"func\s+(\w+)"],
            "struct_patterns": [r"type\s+(\w+)\s+struct"],
        },
    })

    result = json.loads(load_docgen_config.invoke({"config_path": config_path}))

    assert result["success"] is False
    assert "mapping" in result["error"].lower() or "不能为空" in result["error"]
