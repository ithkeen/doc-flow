"""RAG 检索器。

封装 Chroma 向量检索和文档格式化。
"""

from __future__ import annotations

import functools
import logging

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from src.config import settings
from src.rag.embeddings import get_embeddings

logger = logging.getLogger(__name__)

_TOP_K = 3


@functools.lru_cache(maxsize=1)
def get_retriever() -> BaseRetriever:
    """返回 Chroma retriever 实例（缓存复用）。

    Returns:
        配置好的 BaseRetriever。
    """
    try:
        vectorstore = Chroma(
            collection_name=settings.chroma.collection_name,
            persist_directory=settings.chroma.persist_dir,
            embedding_function=get_embeddings(),
        )
        return vectorstore.as_retriever(search_kwargs={"k": _TOP_K})
    except Exception:
        logger.exception("Chroma 初始化失败")
        raise


def format_retrieved_docs(docs: list[Document]) -> str:
    """将检索到的 Document 列表格式化为带来源标注的文本。

    Args:
        docs: LangChain Document 列表。

    Returns:
        格式化的文本。空列表返回空字符串。
    """
    if not docs:
        return ""

    parts: list[str] = []
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "unknown")
        parts.append(f"文档 {i} (来源: {source}):\n{doc.page_content}")

    return "\n\n".join(parts)
