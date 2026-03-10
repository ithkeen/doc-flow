"""配置管理模块。

使用 Pydantic Settings 从环境变量和 .env 文件加载配置。
必填配置缺失时启动即报错（fail-fast）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env 文件路径：项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class LLMSettings(BaseSettings):
    """LLM API 配置。"""

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=_ENV_FILE,
        extra="ignore",
    )

    base_url: str = "https://api.openai.com/v1"
    api_key: str
    model: str = "gpt-4"


class LangSmithSettings(BaseSettings):
    """LangSmith 配置（可选，用于 tracing 和监控）。"""

    model_config = SettingsConfigDict(
        env_prefix="LANGSMITH_",
        env_file=_ENV_FILE,
        extra="ignore",
    )

    tracing: bool = True
    api_key: str | None = None
    project: str = "doc-flow"
    endpoint: str = "https://api.smith.langchain.com"


class LogSettings(BaseSettings):
    """日志配置。"""

    model_config = SettingsConfigDict(
        env_prefix="LOG_",
        env_file=_ENV_FILE,
        extra="ignore",
    )

    level: str = "INFO"
    dir: str = "logs/"
    backup_count: int = 7


class Settings(BaseSettings):
    """应用根配置。

    组合所有子配置组，提供统一的配置访问入口。
    LLM_API_KEY 为必填项，缺失时构造实例会抛出 ValidationError。
    """

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        extra="ignore",
    )

    docs_output_dir: str = "./docs"
    llm: LLMSettings = Field(default_factory=LLMSettings)
    langsmith: LangSmithSettings = Field(default_factory=LangSmithSettings)
    log: LogSettings = Field(default_factory=LogSettings)

    def __init__(self, **kwargs: Any) -> None:
        """构造 Settings，将 _env_file 传递给子配置。"""
        env_file = kwargs.get("_env_file", _ENV_FILE)

        # 如果调用方未显式提供子模型，则用相同的 _env_file 构建
        if "llm" not in kwargs:
            kwargs["llm"] = LLMSettings(_env_file=env_file)
        if "langsmith" not in kwargs:
            kwargs["langsmith"] = LangSmithSettings(_env_file=env_file)
        if "log" not in kwargs:
            kwargs["log"] = LogSettings(_env_file=env_file)

        super().__init__(**kwargs)
