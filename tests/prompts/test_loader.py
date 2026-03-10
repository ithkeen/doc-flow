"""load_prompt 单元测试。"""

from pathlib import Path

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
