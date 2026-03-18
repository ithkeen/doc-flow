"""RAG 检索模块。

提供向量检索和文档格式化能力，供 doc_qa 节点使用。
"""

from src.rag.embeddings import get_embeddings
from src.rag.retriever import format_retrieved_docs, get_retriever

__all__ = ["get_embeddings", "get_retriever", "format_retrieved_docs"]
