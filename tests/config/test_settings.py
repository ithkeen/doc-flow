"""配置模块单元测试。"""

import sys

import pytest
from pydantic import ValidationError

from src.config.settings import LLMSettings, LangSmithSettings, NodeLLMSettings, Settings


class TestLLMSettings:
    """LLM 配置测试。"""

    def test_loads_from_env(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setenv("LLM_MODEL", "gpt-3.5-turbo")
        monkeypatch.setenv("LLM_BASE_URL", "https://custom.api/v1")

        s = LLMSettings(_env_file=None)
        assert s.api_key == "test-key"
        assert s.model == "gpt-3.5-turbo"
        assert s.base_url == "https://custom.api/v1"

    def test_defaults(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")

        s = LLMSettings(_env_file=None)
        assert s.base_url == "https://api.openai.com/v1"
        assert s.model == "gpt-4"

    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)

        with pytest.raises(ValidationError):
            LLMSettings(_env_file=None)


class TestLangSmithSettings:
    """LangSmith 配置测试。"""

    def test_all_optional(self, monkeypatch):
        monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
        monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
        monkeypatch.delenv("LANGSMITH_PROJECT", raising=False)
        monkeypatch.delenv("LANGSMITH_ENDPOINT", raising=False)

        s = LangSmithSettings(_env_file=None)
        assert s.tracing is True
        assert s.api_key is None
        assert s.project == "doc-flow"
        assert s.endpoint == "https://api.smith.langchain.com"

    def test_loads_from_env(self, monkeypatch):
        monkeypatch.setenv("LANGSMITH_TRACING", "false")
        monkeypatch.setenv("LANGSMITH_API_KEY", "ls-key")

        s = LangSmithSettings(_env_file=None)
        assert s.tracing is False
        assert s.api_key == "ls-key"


class TestSettings:
    """Root Settings 测试。"""

    def test_loads_all_groups(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.delenv("DOCS_OUTPUT_DIR", raising=False)

        s = Settings(_env_file=None)
        assert s.llm.api_key == "test-key"
        assert s.docs_output_dir == "./docs"
        assert s.langsmith.tracing is True

    def test_docs_output_dir_from_env(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setenv("DOCS_OUTPUT_DIR", "/custom/docs")

        s = Settings(_env_file=None)
        assert s.docs_output_dir == "/custom/docs"

    def test_fail_fast_without_llm_key(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)

        with pytest.raises(ValidationError):
            Settings(_env_file=None)

    def test_agent_work_dir_default(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.delenv("AGENT_WORK_DIR", raising=False)

        s = Settings(_env_file=None)
        assert s.agent_work_dir == "."

    def test_agent_work_dir_from_env(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setenv("AGENT_WORK_DIR", "/home/user/go-project")

        s = Settings(_env_file=None)
        assert s.agent_work_dir == "/home/user/go-project"


class TestSettingsSingleton:
    """Singleton 导入测试。"""

    def test_import_settings(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "singleton-key")
        monkeypatch.delitem(sys.modules, "src.config", raising=False)

        import src.config

        assert src.config.settings.llm.api_key == "singleton-key"

    def test_same_instance(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "singleton-key")
        monkeypatch.delitem(sys.modules, "src.config", raising=False)

        import src.config

        from src.config import settings as s1
        s2 = src.config.settings

        assert s1 is s2


class TestNodeLLMSettings:
    """节点级 LLM 配置测试。"""

    def test_all_fields_default_to_none(self, monkeypatch):
        """未设置环境变量时，所有字段应为 None。"""
        monkeypatch.delenv("INTENT_LLM_BASE_URL", raising=False)
        monkeypatch.delenv("INTENT_LLM_API_KEY", raising=False)
        monkeypatch.delenv("INTENT_LLM_MODEL", raising=False)

        s = NodeLLMSettings(_env_file=None, _env_prefix="INTENT_LLM_")
        assert s.base_url is None
        assert s.api_key is None
        assert s.model is None

    def test_loads_from_env_with_prefix(self, monkeypatch):
        """设置环境变量时，应正确加载。"""
        monkeypatch.setenv("INTENT_LLM_MODEL", "gpt-4o-mini")
        monkeypatch.setenv("INTENT_LLM_BASE_URL", "https://custom.api/v1")
        monkeypatch.setenv("INTENT_LLM_API_KEY", "intent-key")

        s = NodeLLMSettings(_env_file=None, _env_prefix="INTENT_LLM_")
        assert s.model == "gpt-4o-mini"
        assert s.base_url == "https://custom.api/v1"
        assert s.api_key == "intent-key"

    def test_different_prefixes_load_independently(self, monkeypatch):
        """不同 env_prefix 的实例应独立加载各自的环境变量。"""
        monkeypatch.setenv("INTENT_LLM_MODEL", "gpt-4o-mini")
        monkeypatch.setenv("DOC_GEN_LLM_MODEL", "gpt-4")
        monkeypatch.delenv("CHAT_LLM_MODEL", raising=False)

        intent = NodeLLMSettings(_env_file=None, _env_prefix="INTENT_LLM_")
        doc_gen = NodeLLMSettings(_env_file=None, _env_prefix="DOC_GEN_LLM_")
        chat = NodeLLMSettings(_env_file=None, _env_prefix="CHAT_LLM_")

        assert intent.model == "gpt-4o-mini"
        assert doc_gen.model == "gpt-4"
        assert chat.model is None

    def test_ignores_extra_env_vars(self, monkeypatch):
        """带有匹配前缀但不在字段中的环境变量应被忽略（extra=ignore）。"""
        monkeypatch.setenv("INTENT_LLM_TEMPERATURE", "0.5")

        s = NodeLLMSettings(_env_file=None, _env_prefix="INTENT_LLM_")
        assert not hasattr(s, "temperature")


