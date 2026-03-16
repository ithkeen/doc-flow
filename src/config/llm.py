"""LLM 实例工厂。

根据节点名称返回对应配置的 ChatOpenAI 实例。
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from src.config import settings

_NODE_LLM_ATTR = {
    "intent": "intent_llm",
    "doc_gen": "doc_gen_llm",
    "doc_qa": "doc_qa_llm",
    "chat": "chat_llm",
}


def get_node_llm(node_name: str) -> ChatOpenAI:
    """根据节点名称返回对应配置的 ChatOpenAI 实例，未配置字段 fallback 到全局。"""
    attr = _NODE_LLM_ATTR.get(node_name)
    node_cfg = getattr(settings, attr, None) if attr else None

    base_url = (
        node_cfg.base_url
        if (node_cfg and node_cfg.base_url is not None)
        else settings.llm.base_url
    )
    api_key = (
        node_cfg.api_key
        if (node_cfg and node_cfg.api_key is not None)
        else settings.llm.api_key
    )
    model = (
        node_cfg.model
        if (node_cfg and node_cfg.model is not None)
        else settings.llm.model
    )

    return ChatOpenAI(base_url=base_url, api_key=api_key, model=model)
