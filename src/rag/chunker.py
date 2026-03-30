"""Markdown 文档分块器。

按 ## / ### 标题切分文档，每个块为独立语义单元。
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from langchain_core.documents import Document

SECTION_MAP = {
    "概述": "overview",
    "请求参数": "parameters",
    "响应": "response",
    "执行流程": "flow",
    "错误码": "error_codes",
    "请求示例": "examples",
    "响应示例": "examples",
}

@dataclass
class Chunk:
    page_content: str
    metadata: dict
    section: str = ""

def chunk_markdown_doc(
    content: str,
    source_path: str,
    project: str,
    service: str,
) -> list[Chunk]:
    """按 Markdown 标题切分文档。

    Args:
        content: 文档原始内容
        source_path: 原始文档路径（用于 parent_doc_id）
        project: 项目名
        service: 服务/模块名

    Returns:
        Chunk 列表，按文档顺序排列
    """
    # 查找所有 ## / ### 标题及其位置
    header_pattern = r"(^#{2,3}\s+.+$)"
    headers = [(m.start(), m.group(1)) for m in re.finditer(header_pattern, content, re.MULTILINE)]

    chunks: list[Chunk] = []
    for idx, (start, header) in enumerate(headers):
        # 提取标题文本
        header_match = re.match(r"^#{2,3}\s+(.+)$", header)
        if not header_match:
            continue
        title = header_match.group(1).strip()

        # 查找下一个标题位置，确定本节内容范围
        if idx + 1 < len(headers):
            end = headers[idx + 1][0]
        else:
            end = len(content)

        body = content[start + len(header):end].strip()

        # 映射 section
        section = SECTION_MAP.get(title, "other")
        chunk_content = f"{header}\n\n{body}" if body else header

        chunks.append(Chunk(
            page_content=chunk_content,
            metadata={
                "source": source_path,
                "parent_doc_id": source_path,
                "project": project,
                "service": service,
                "api_name": source_path.split("/")[-1].replace(".md", ""),
                "section": section,
                "title": title,
            },
            section=section,
        ))

    # 如果没有任何标题匹配，整个文档作为一个块
    if not chunks:
        chunks.append(Chunk(
            page_content=content,
            metadata={
                "source": source_path,
                "parent_doc_id": source_path,
                "project": project,
                "service": service,
                "api_name": source_path.split("/")[-1].replace(".md", ""),
                "section": "all",
                "title": "",
            },
            section="all",
        ))
    return chunks

def chunks_to_documents(chunks: list[Chunk]) -> list[Document]:
    """将 Chunk 列表转换为 LangChain Document 列表。"""
    return [
        Document(page_content=c.page_content, metadata=c.metadata)
        for c in chunks
    ]