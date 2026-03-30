import pytest
from src.rag.chunker import chunk_markdown_doc, Chunk

def test_chunk_by_h2_headers():
    content = """# BuyResource

## 概述
这是概述内容。

## 错误码
| 错误码 | 描述 |

## 请求示例
```bash
curl ...
```"""
    chunks = chunk_markdown_doc(content, "ubill-access-api/order/BuyResource.md", "ubill-access-api", "order")
    assert len(chunks) == 3
    assert chunks[0].section == "overview"
    assert chunks[1].section == "error_codes"
    assert chunks[2].section == "examples"
    assert all(c.metadata["project"] == "ubill-access-api" for c in chunks)
    assert all(c.metadata["service"] == "order" for c in chunks)