"""配置模块。

提供全局 settings 单例，应用启动时加载一次，后续 import 即用。

Usage::

    from src.config import settings

    settings.llm.api_key
    settings.llm.model
    settings.docs_output_dir
    settings.langsmith.tracing
"""

from src.config.settings import Settings

settings = Settings()

__all__ = ["settings", "Settings"]
