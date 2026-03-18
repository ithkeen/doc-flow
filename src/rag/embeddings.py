"""Embedding 模型工厂。

复用 LLM 配置中的 base_url 和 api_key，仅切换模型名称。
"""

from langchain_openai import OpenAIEmbeddings

from src.config import settings


def get_embeddings() -> OpenAIEmbeddings:
    """返回配置好的 OpenAIEmbeddings 实例。"""
    return OpenAIEmbeddings(
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
        model=settings.llm.embed_model,
    )
