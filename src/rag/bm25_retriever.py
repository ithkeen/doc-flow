"""BM25 关键词检索器。

基于 rank_bm25 实现，配合 Chroma 向量检索做混合检索。
"""
from __future__ import annotations

from typing import Any
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from rank_bm25 import BM25Okapi
import re

class BM25Retriever(BaseRetriever):
    """BM25 检索器。"""

    def __init__(self, docs: list[Document], k: int = 5):
        self._docs = docs
        self._k = k
        self._tokenized_docs = [self._tokenize(d.page_content) for d in docs]
        self._bm25 = BM25Okapi(self._tokenized_docs)

    @classmethod
    def from_documents(cls, documents: list[Document], k: int = 5) -> "BM25Retriever":
        return cls(documents, k)

    def _tokenize(self, text: str) -> list[str]:
        """简单中英文分词（按空格和特殊字符分割）。"""
        tokens = re.findall(r"[\w]+", text.lower())
        return tokens

    def _get_scores(self, query: str) -> list[float]:
        tokenized_query = self._tokenize(query)
        return self._bm25.get_scores(tokenized_query)

    def _get_relevant_documents(self, query: str) -> list[Document]:
        scores = self._get_scores(query)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:self._k]
        return [self._docs[i] for i in top_indices if scores[i] > 0]

    def invoke(self, query: str) -> list[Document]:
        return self._get_relevant_documents(query)

    def add_documents(self, documents: list[Document]) -> None:
        new_tokenized = [self._tokenize(d.page_content) for d in documents]
        self._docs.extend(documents)
        self._tokenized_docs.extend(new_tokenized)
        self._bm25 = BM25Okapi(self._tokenized_docs)