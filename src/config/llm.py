"""LLM 工厂函数。

根据模型类型返回配置好的 ChatOpenAI 实例。
"""
from langchain_openai import ChatOpenAI

from src.config import settings


def get_llm(model_type: str = "default") -> ChatOpenAI:
    """根据模型类型返回 ChatOpenAI 实例。

    Args:
        model_type: 模型类型，可选 "default" | "chat" | "doc_gen"

    Returns:
        配置好的 ChatOpenAI 实例
    """
    model_map = {
        "default": settings.llm.default_model,
        "chat": settings.llm.chat_model,
        "doc_gen": settings.llm.doc_gen_model,
    }
    model_name = model_map.get(model_type, settings.llm.default_model)

    return ChatOpenAI(
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
        model=model_name,
    )