import pytest
from langchain_core.documents import Document
from src.rag.bm25_retriever import BM25Retriever

def test_bm25_retriever_basic():
    docs = [
        Document(page_content="## 概述\n这是概述内容。", metadata={"source": "a.md", "section": "overview"}),
        Document(page_content="## 错误码\n10001: 输入无效", metadata={"source": "b.md", "section": "error_codes"}),
        Document(page_content="## 请求示例\ncurl command", metadata={"source": "c.md", "section": "examples"}),
    ]
    retriever = BM25Retriever.from_documents(docs)
    results = retriever.invoke("错误码")
    assert len(results) == 1
    assert results[0].metadata["section"] == "error_codes"