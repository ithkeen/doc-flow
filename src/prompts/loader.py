"""提示词模板加载器。

从 system/ 和 user/ 子目录读取 .md 模板文件，
组装为 LangChain ChatPromptTemplate。
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate

_DEFAULT_PROMPTS_DIR = Path(__file__).resolve().parent


def load_prompt(
    name: str,
    *,
    prompts_dir: Path = _DEFAULT_PROMPTS_DIR,
) -> ChatPromptTemplate:
    """按节点名称加载提示词，返回 ChatPromptTemplate。

    从 prompts_dir/system/{name}.md 和 prompts_dir/user/{name}.md
    读取模板内容。两者均为可选，但至少需要存在一个。

    Args:
        name: 提示词名称，对应模板文件名（不含扩展名）。
        prompts_dir: 提示词根目录，默认为本模块所在目录。

    Returns:
        组装好的 ChatPromptTemplate。

    Raises:
        FileNotFoundError: system 和 user 模板均不存在时抛出。
    """
    system_path = prompts_dir / "system" / f"{name}.md"
    user_path = prompts_dir / "user" / f"{name}.md"

    messages: list[tuple[str, str]] = []

    if system_path.exists():
        messages.append(("system", system_path.read_text(encoding="utf-8").strip()))
    if user_path.exists():
        messages.append(("human", user_path.read_text(encoding="utf-8").strip()))

    if not messages:
        raise FileNotFoundError(
            f"提示词模板不存在: 至少需要 system/{name}.md 或 user/{name}.md 其中之一"
        )

    return ChatPromptTemplate.from_messages(messages)
