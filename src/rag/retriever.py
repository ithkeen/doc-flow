"""RAG 检索器。

封装 Chroma 向量检索和文档格式化。
"""

from __future__ import annotations

from langchain_core.documents import Document


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
