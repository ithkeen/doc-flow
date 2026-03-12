"""load_prompt 单元测试。"""

import pytest
from langchain_core.prompts import ChatPromptTemplate

from src.prompts.loader import load_prompt


@pytest.fixture()
def prompts_dir(tmp_path):
    """创建临时提示词目录结构。"""
    system_dir = tmp_path / "system"
    user_dir = tmp_path / "user"
    system_dir.mkdir()
    user_dir.mkdir()
    return tmp_path


class TestLoadPromptBothTemplates:
    """system + user 模板同时存在。"""

    def test_returns_chat_prompt_template(self, prompts_dir):
        (prompts_dir / "system" / "test_node.md").write_text("你是助手。", encoding="utf-8")
        (prompts_dir / "user" / "test_node.md").write_text("用户输入：{input}", encoding="utf-8")

        result = load_prompt("test_node", prompts_dir=prompts_dir)

        assert isinstance(result, ChatPromptTemplate)

    def test_contains_system_and_human_messages(self, prompts_dir):
        (prompts_dir / "system" / "test_node.md").write_text("你是助手。", encoding="utf-8")
        (prompts_dir / "user" / "test_node.md").write_text("用户输入：{input}", encoding="utf-8")

        result = load_prompt("test_node", prompts_dir=prompts_dir)
        messages = result.format_messages(input="你好")

        assert len(messages) == 2
        assert messages[0].type == "system"
        assert messages[0].content == "你是助手。"
        assert messages[1].type == "human"
        assert messages[1].content == "用户输入：你好"

    def test_strips_whitespace_from_template(self, prompts_dir):
        (prompts_dir / "system" / "test_node.md").write_text("\n  你是助手。\n\n", encoding="utf-8")
        (prompts_dir / "user" / "test_node.md").write_text("\n用户输入：{input}\n", encoding="utf-8")

        result = load_prompt("test_node", prompts_dir=prompts_dir)
        messages = result.format_messages(input="你好")

        assert messages[0].content == "你是助手。"
        assert messages[1].content == "用户输入：你好"


class TestLoadPromptSystemOnly:
    """仅 system 模板存在。"""

    def test_returns_system_message_only(self, prompts_dir):
        (prompts_dir / "system" / "react_node.md").write_text("你是 ReAct agent。", encoding="utf-8")

        result = load_prompt("react_node", prompts_dir=prompts_dir)
        messages = result.format_messages()

        assert len(messages) == 1
        assert messages[0].type == "system"
        assert messages[0].content == "你是 ReAct agent。"


class TestLoadPromptUserOnly:
    """仅 user 模板存在。"""

    def test_returns_human_message_only(self, prompts_dir):
        (prompts_dir / "user" / "simple_node.md").write_text("请处理：{task}", encoding="utf-8")

        result = load_prompt("simple_node", prompts_dir=prompts_dir)
        messages = result.format_messages(task="分析代码")

        assert len(messages) == 1
        assert messages[0].type == "human"
        assert messages[0].content == "请处理：分析代码"


class TestLoadPromptNotFound:
    """system 和 user 模板均不存在。"""

    def test_raises_file_not_found_error(self, prompts_dir):
        with pytest.raises(FileNotFoundError, match="提示词模板不存在"):
            load_prompt("nonexistent", prompts_dir=prompts_dir)


class TestLoadBundledTemplates:
    """验证项目自带的模板文件可正常加载。"""

    def test_load_intent_prompt(self):
        result = load_prompt("intent")

        assert isinstance(result, ChatPromptTemplate)
        messages = result.format_messages(intent_list="1. 生成文档", user_input="帮我生成文档")
        assert len(messages) == 2
        assert messages[0].type == "system"
        assert messages[1].type == "human"

    def test_load_doc_gen_prompt(self):
        result = load_prompt("doc_gen")

        assert isinstance(result, ChatPromptTemplate)
        messages = result.format_messages(file_path="./handler/api.go")
        assert len(messages) == 2
        assert messages[0].type == "system"
        assert messages[1].type == "human"
        content = messages[0].content
        # Role unchanged
        assert "Go API documentation generator" in content
        # Task 1: Recursive context building with queue tracking
        assert "Resolved" in content
        assert "Unresolved" in content
        # Task 2: Execution flow analysis (new)
        assert "Execution Flow Analysis" in content
        assert "Happy Path" in content
        assert "Error Exits" in content
        # Task 3: Mermaid flowchart in template
        assert "flowchart TD" in content
        # Documentation template has Execution Flow section
        assert "## Execution Flow" in content
        # Validate brace escaping resolved correctly (no leftover {{ or }})
        assert "{{" not in content, "Unresolved double braces in system prompt"
        assert "}}" not in content, "Unresolved double braces in system prompt"


class TestModuleExport:
    """验证模块导出。"""

    def test_load_prompt_importable_from_package(self):
        from src.prompts import load_prompt as fn

        assert callable(fn)
