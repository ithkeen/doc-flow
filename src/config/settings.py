"""配置管理模块。

使用 Pydantic Settings 从环境变量和 .env 文件加载配置。
必填配置缺失时启动即报错（fail-fast）。
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env 文件路径：项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class LLMSettings(BaseSettings):
    """LLM API 配置。

    共享 base_url 和 api_key，按用途区分模型。
    """

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=_ENV_FILE,
        extra="ignore",
    )

    base_url: str
    api_key: str
    default_model: str
    doc_gen_model: str
    chat_model: str


class LangSmithSettings(BaseSettings):
    """LangSmith 配置，用于 tracing 和监控。"""

    model_config = SettingsConfigDict(
        env_prefix="LANGSMITH_",
        env_file=_ENV_FILE,
        extra="ignore",
    )

    tracing: bool
    api_key: str
    project: str
    endpoint: str


class LogSettings(BaseSettings):
    """日志配置。"""

    model_config = SettingsConfigDict(
        env_prefix="LOG_",
        env_file=_ENV_FILE,
        extra="ignore",
    )

    level: str
    dir: str
    backup_count: int


class DatabaseSettings(BaseSettings):
    """MySQL 数据库配置。"""

    model_config = SettingsConfigDict(
        env_prefix="DB_",
        env_file=_ENV_FILE,
        extra="ignore",
    )

    host: str
    port: int = 3306
    user: str
    password: str
    database: str


class Settings(BaseSettings):
    """应用根配置。

    组合所有子配置组，提供统一的配置访问入口。
    所有配置项均为必填，缺失时构造实例会抛出 ValidationError。
    """

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        extra="ignore",
    )

    code_space_dir: str
    docs_space_dir: str
    llm: LLMSettings = Field(default_factory=LLMSettings)
    langsmith: LangSmithSettings = Field(default_factory=LangSmithSettings)
    log: LogSettings = Field(default_factory=LogSettings)
    # 不使用 default_factory=DatabaseSettings，因为 DB_* 环境变量是可选的。
    # 未配置时 db 为 None，tool 内部会懒加载。
    db: DatabaseSettings | None = None