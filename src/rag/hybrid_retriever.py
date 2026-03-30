"""混合检索器。

并行执行向量检索 + BM25 检索，合并去重后返回。
"""
from __future__ import annotations

from typing import Any
import functools

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from src.config import settings
from src.rag.embeddings import get_embeddings
from src.rag.bm25_retriever import BM25Retriever

_TOP_K = 5


@functools.lru_cache(maxsize=1)
def _get_chroma_collection():
    """返回 Chroma collection（缓存）。"""
    from langchain_chroma import Chroma
    return Chroma(
        collection_name=settings.chroma.collection_name,
        persist_directory=settings.chroma.persist_dir,
        embedding_function=get_embeddings(),
    )


@functools.lru_cache(maxsize=1)
def _get_bm25_retriever() -> BM25Retriever:
    """从 Chroma 中加载所有文档，构建 BM25 索引。"""
    collection = _get_chroma_collection()
    docs = collection.get(include=["documents", "metadatas"])
    documents = [
        Document(page_content=doc, metadata=meta)
        for doc, meta in zip(docs["documents"], docs["metadatas"])
    ]
    return BM25Retriever.from_documents(documents, k=_TOP_K)


class HybridRetriever(BaseRetriever):
    """混合检索器：向量 + BM25。"""

    def __init__(self, top_k: int = _TOP_K):
        self._top_k = top_k

    def _vector_search(
        self,
        query: str,
        project: str | None = None,
        service: str | None = None,
    ) -> list[Document]:
        collection = _get_chroma_collection()
        filter_dict: dict[str, Any] = {}
        if project:
            filter_dict["project"] = project
        if service:
            filter_dict["service"] = service

        return collection.as_retriever(
            search_kwargs={
                "k": self._top_k,
                "filter": filter_dict if filter_dict else None,
            }
        ).invoke(query)

    def _bm25_search(
        self,
        query: str,
        project: str | None = None,
        service: str | None = None,
    ) -> list[Document]:
        retriever = _get_bm25_retriever()
        all_results = retriever.invoke(query)
        if project or service:
            filtered = []
            for doc in all_results:
                if project and doc.metadata.get("project") != project:
                    continue
                if service and doc.metadata.get("service") != service:
                    continue
                filtered.append(doc)
            return filtered
        return all_results

    def _get_relevant_documents(
        self,
        query: str,
        project: str | None = None,
        service: str | None = None,
        strategy: str = "hybrid",
    ) -> list[Document]:
        """BaseRetriever 抽象方法实现，委托给 invoke。"""
        return self.invoke(query, project, service, strategy)

    def invoke(
        self,
        query: str,
        project: str | None = None,
        service: str | None = None,
        strategy: str = "hybrid",
    ) -> list[Document]:
        """执行检索。

        Args:
            query: 检索词
            project: 项目名过滤
            service: 服务名过滤
            strategy: semantic | keyword | hybrid
        """
        if strategy == "semantic":
            return self._vector_search(query, project, service)
        if strategy == "keyword":
            return self._bm25_search(query, project, service)

        # hybrid: 并行执行，合并去重
        vector_results = self._vector_search(query, project, service)
        bm25_results = self._bm25_search(query, project, service)

        # 按 page_content[:50] + source 去重
        seen: set[str] = set()
        merged: list[Document] = []
        for doc in vector_results + bm25_results:
            key = doc.page_content[:50] + doc.metadata.get("source", "")
            if key not in seen:
                seen.add(key)
                merged.append(doc)

        return merged[:self._top_k]