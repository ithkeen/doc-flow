# doc_qa 节点增强实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 doc_qa 从单步检索升级为两阶段子图（query_planning + 检索执行），支持 Catalog 路由、混合检索（向量+BM25）、按章节分块索引。

**Architecture:**
- 新增 `query_planning` 节点：接收用户问题，参考 Catalog 输出 retrieval_plan
- 新增 `hybrid_retriever`：并行执行向量检索 + BM25 检索，合并去重
- 文档索引改為按 Markdown 标题分块，元数据含 project/service/section
- doc_qa 节点接收 retrieval_plan，按计划执行多路检索后生成回答

**Tech Stack:** rank_bm25（BM25 算法）, Chroma（向量库）, LangGraph（编排）

---

## 文件结构

### 新建文件

| 文件 | 职责 |
|------|------|
| `src/rag/chunker.py` | 按 Markdown 标题分块 |
| `src/rag/bm25_retriever.py` | BM25 关键词检索 |
| `src/rag/hybrid_retriever.py` | 向量+BM25 混合检索 |
| `src/prompts/system/query_planning.md` | query_planning 系统提示词 |
| `src/prompts/user/query_planning.md` | query_planning 用户提示词模板 |
| `tests/rag/test_chunker.py` | 分块器测试 |
| `tests/rag/test_bm25_retriever.py` | BM25 检索器测试 |
| `tests/graph/test_query_planning.py` | query_planning 节点测试 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `src/rag/retriever.py` | 新增 `hybrid_search` 方法，支持 `search_query` + 元数据过滤 |
| `src/graph/nodes.py` | 新增 `query_planning` 节点；修改 `doc_qa` 接收 `retrieval_plan` |
| `src/graph/graph.py` | doc_qa 路由改为：intent → query_planning → doc_qa → END |
| `scripts/index_docs.py` | 改为分块索引，元数据含 project/service/section |
| `src/config/settings.py` | 新增 `catalog_dir` 配置项 |
| `src/config/__init__.py` | 导出新配置 |

---

## 实现任务

### Task 1: 文档分块器 `src/rag/chunker.py`

**Files:**
- Create: `src/rag/chunker.py`
- Test: `tests/rag/test_chunker.py`

- [ ] **Step 1: 写失败的测试**

```python
# tests/rag/test_chunker.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/rag/test_chunker.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: 实现 chunker**

```python
# src/rag/chunker.py
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
    # 按 ## 或 ### 分割，保留标题和内容
    pattern = r"(^#{2,3}\s+.+$)"
    parts = re.split(pattern, content, flags=re.MULTILINE)
    parts = [p for p in parts if p.strip()]  # 去掉空字符串

    chunks: list[Chunk] = []
    for i in range(0, len(parts) - 1, 2):
        header = parts[i]
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""

        # 提取标题文本
        header_match = re.match(r"^#{2,3}\s+(.+)$", header)
        if not header_match:
            continue
        title = header_match.group(1).strip()

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
        ))
    return chunks

def chunks_to_documents(chunks: list[Chunk]) -> list[Document]:
    """将 Chunk 列表转换为 LangChain Document 列表。"""
    return [
        Document(page_content=c.page_content, metadata=c.metadata)
        for c in chunks
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/rag/test_chunker.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/rag/chunker.py tests/rag/test_chunker.py
git commit -m "feat(rag): add markdown document chunker"
```

---

### Task 2: BM25 检索器 `src/rag/bm25_retriever.py`

**Files:**
- Create: `src/rag/bm25_retriever.py`
- Test: `tests/rag/test_bm25_retriever.py`

> **Note:** 需要安装 `rank_bm25` 库：
> `uv add rank_bm25`

- [ ] **Step 1: 写失败的测试**

```python
# tests/rag/test_bm25_retriever.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/rag/test_bm25_retriever.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: 实现 BM25Retriever**

```python
# src/rag/bm25_retriever.py
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
        return cls(docs, k)

    def _tokenize(self, text: str) -> list[str]:
        """简单中英文分词（按空格和特殊字符分割）。"""
        tokens = re.findall(r"[\w]+", text.lower())
        return tokens

    def _get_scores(self, query: str) -> list[float]:
        tokenized_query = self._tokenize(query)
        return self._bm25.get_scores(tokenized_query)

    def invoke(self, query: str) -> list[Document]:
        scores = self._get_scores(query)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:self._k]
        return [self._docs[i] for i in top_indices if scores[i] > 0]

    def add_documents(self, documents: list[Document]) -> None:
        new_tokenized = [self._tokenize(d.page_content) for d in documents]
        self._docs.extend(documents)
        self._tokenized_docs.extend(new_tokenized)
        self._bm25 = BM25Okapi(self._tokenized_docs)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/rag/test_bm25_retriever.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/rag/bm25_retriever.py tests/rag/test_bm25_retriever.py
git commit -m "feat(rag): add BM25 keyword retriever"
```

---

### Task 3: 混合检索器 `src/rag/hybrid_retriever.py`

**Files:**
- Create: `src/rag/hybrid_retriever.py`

> **Note:** 将向量检索和 BM25 检索并行执行，合并去重。

- [ ] **Step 1: 实现混合检索类**

```python
# src/rag/hybrid_retriever.py
"""混合检索器。

并行执行向量检索 + BM25 检索，合并去重后返回。
"""
from __future__ import annotations

from typing import Annotated
import functools

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnableConfig

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
        # 按元数据过滤
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

        # 按 page_content + source 去重
        seen: set[str] = set()
        merged: list[Document] = []
        for doc in vector_results + bm25_results:
            key = doc.page_content[:50] + doc.metadata.get("source", "")
            if key not in seen:
                seen.add(key)
                merged.append(doc)

        return merged[:self._top_k]
```

- [ ] **Step 2: Commit**

```bash
git add src/rag/hybrid_retriever.py
git commit -m "feat(rag): add hybrid retriever (vector + BM25)"
```

---

### Task 4: query_planning 提示词

**Files:**
- Create: `src/prompts/system/query_planning.md`
- Create: `src/prompts/user/query_planning.md`

- [ ] **Step 1: 写 system prompt**

```markdown
# src/prompts/system/query_planning.md

你是一个文档检索规划助手。

根据用户问题和 Catalog 信息，生成检索计划。

## Catalog
{catalog_content}

## 约束
- 只能检索 catalog 中已存在的项目和服务
- 每个检索单元对应一次独立的检索操作
- search_query 用自然语言描述要检索什么，长度 5-15 字
- information_types 可选值：overview, parameters, response, error_codes, examples, flow, all
- search_strategy 可选值：semantic（向量检索）, keyword（BM25）, hybrid（混合）
- 如果用户问题与 catalog 中任何项目都不匹配，返回空的 retrieval_plan
```

- [ ] **Step 2: 写 user prompt**

```markdown
# src/prompts/user/query_planning.md

用户问题：{user_question}

请根据以上问题，从 Catalog 中选择需要检索的项目和服务，生成检索计划。

返回 JSON：
{
  "retrieval_plan": [
    {
      "project": "项目名",
      "service": "服务名",
      "information_types": ["error_codes"],
      "search_strategy": "hybrid",
      "search_query": "检索词"
    }
  ]
}
```

- [ ] **Step 3: Commit**

```bash
git add src/prompts/system/query_planning.md src/prompts/user/query_planning.md
git commit -m "feat(prompts): add query_planning prompt templates"
```

---

### Task 5: query_planning 节点 `src/graph/nodes.py`

**Files:**
- Modify: `src/graph/nodes.py`

- [ ] **Step 1: 添加 import 和 Catalog 加载函数**

在 `from src.prompts import load_prompt` 后添加：

```python
import json
from pathlib import Path

def load_catalog() -> str:
    """加载 Catalog JSON 内容，供 query_planning 使用。"""
    catalog_path = Path(settings.docs_space_dir) / "catalog" / "index.json"
    if not catalog_path.exists():
        return "{}"
    return catalog_path.read_text(encoding="utf-8")
```

- [ ] **Step 2: 添加 query_planning 节点**

```python
async def query_planning(state: State, config: RunnableConfig) -> dict:
    """检索规划节点。

    分析用户问题，参考 Catalog，输出结构化 retrieval_plan。
    """
    prompt = load_prompt("query_planning")
    user_input = _get_last_human_message(state["messages"])
    catalog_content = load_catalog()

    system_messages = prompt.format_messages(
        user_question=user_input,
        catalog_content=catalog_content,
    )

    llm = get_llm("intent")
    response = await llm.ainvoke(system_messages, config=config)

    raw = response.content
    # 解析 JSON
    try:
        # 尝试从 markdown code fence 中提取
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw, re.DOTALL)
        if m:
            raw = m.group(1)
        parsed = json.loads(raw)
        retrieval_plan = parsed.get("retrieval_plan", [])
    except (json.JSONDecodeError, ValueError):
        logger.warning("retrieval_plan 解析失败，原始内容：%s", response.content)
        retrieval_plan = []

    logger.info("query_planning 完成，retrieval_plan 条目数：%d", len(retrieval_plan))
    return {"retrieval_plan": retrieval_plan}
```

- [ ] **Step 3: 修改 doc_qa 节点**

更新 `doc_qa` 函数，接收 `retrieval_plan` 并执行多路检索：

```python
async def doc_qa(state: State, config: RunnableConfig) -> dict:
    """文档问答节点。

    按 retrieval_plan 执行多路混合检索，生成回答。
    """
    from src.rag.hybrid_retriever import HybridRetriever

    prompt = load_prompt("doc_qa")
    user_input = _get_last_human_message(state["messages"])
    retrieval_plan = state.get("retrieval_plan", [])

    # 无 retrieval_plan 时 fallback 到空检索（graceful degradation）
    if not retrieval_plan:
        context = ""
    else:
        retriever = HybridRetriever(top_k=_TOP_K)
        all_docs: list[Document] = []
        for unit in retrieval_plan:
            docs = retriever.invoke(
                query=unit.get("search_query", user_input),
                project=unit.get("project"),
                service=unit.get("service"),
                strategy=unit.get("search_strategy", "hybrid"),
            )
            all_docs.extend(docs)

        # 按 source + section 去重，保持顺序
        seen: set[str] = set()
        unique_docs: list[Document] = []
        for doc in all_docs:
            key = doc.metadata.get("source", "") + doc.metadata.get("section", "")
            if key not in seen:
                seen.add(key)
                unique_docs.append(doc)

        context = format_retrieved_docs(unique_docs)

    system_messages = prompt.format_messages(
        user_input=user_input,
        context=context,
    )

    llm = get_llm("doc_qa")
    all_messages = system_messages + state["messages"]
    response = await llm.ainvoke(all_messages, config=config)

    logger.info("文档问答节点调用完成")
    return {"messages": [response]}
```

- [ ] **Step 4: Commit**

```bash
git add src/graph/nodes.py
git commit -m "feat(nodes): add query_planning node and update doc_qa with retrieval_plan"
```

---

### Task 6: 图结构变更 `src/graph/graph.py`

**Files:**
- Modify: `src/graph/graph.py`

- [ ] **Step 1: 更新图结构**

在 `build_graph` 函数中，将 doc_qa 的路由改为经过 query_planning：

```python
graph.add_node("query_planning", query_planning)

# doc_qa 路由：intent → query_planning → doc_qa → END
graph.add_edge("intent_recognize", "query_planning")
graph.add_edge("query_planning", "doc_qa")
graph.add_edge("doc_qa", END)
```

删除原来的 `graph.add_edge("intent_recognize", route_by_intent, ...)` 中的 doc_qa 相关逻辑中的直接连接（需在 `route_by_intent` 返回值中增加 query_planning 入口）。

实际上，因为 doc_qa 现在需要先经过 query_planning，路由逻辑需要调整：

```python
# 在 route_by_intent 中，doc_qa 意图改为指向 query_planning
if state["intent"] == "doc_qa":
    return "query_planning"
# ... 其他不变

# query_planning 之后固定路由到 doc_qa
graph.add_edge("query_planning", "doc_qa")
```

- [ ] **Step 2: Commit**

```bash
git add src/graph/graph.py
git commit -m "feat(graph): route doc_qa through query_planning node"
```

---

### Task 7: 索引脚本更新 `scripts/index_docs.py`

**Files:**
- Modify: `scripts/index_docs.py`

- [ ] **Step 1: 更新索引脚本**

主要改动：
1. 用 `chunker.py` 替代整文件入库
2. 元数据提取 project/service/api_name/section
3. 文档 ID 使用 `source#section` 格式

```python
# 在 index_files 函数中修改：

from src.rag.chunker import chunk_markdown_doc, chunks_to_documents

# ...

for file_path in files:
    content = file_path.read_text(encoding="utf-8")
    metadata = build_metadata(file_path, docs_dir)
    project = metadata["project"]
    service = metadata["module"]

    # 分块
    chunks = chunk_markdown_doc(content, str(file_path.relative_to(docs_dir)), project, service)
    chunk_docs = chunks_to_documents(chunks)

    for chunk_doc in chunk_docs:
        doc_id = f"{chunk_doc.metadata['source']}#{chunk_doc.metadata['section']}"
        docs.append(chunk_doc)
        ids.append(doc_id)
```

- [ ] **Step 2: Commit**

```bash
git add scripts/index_docs.py
git commit -m "feat(index): use chunked indexing with section metadata"
```

---

### Task 8: Catalog 配置和目录

**Files:**
- Modify: `src/config/settings.py`
- Modify: `src/config/__init__.py`

- [ ] **Step 1: 添加 catalog_dir 到 ChromaSettings**

```python
class ChromaSettings(BaseSettings):
    # ... existing fields ...
    persist_dir: str = "./data/chroma"
    collection_name: str = "ubill_docs"
    # catalog 不需要单独配置，直接用 docs_space_dir/catalog
```

catalog 路径直接通过 `settings.docs_space_dir / "catalog" / "index.json"` 访问，不需要额外配置。

- [ ] **Step 2: Commit**

实际上 catalog 路径已经在 `load_catalog()` 函数里通过 `docs_space_dir` 构造，不需要改配置。跳过此步。

---

### Task 9: 端到端测试

**Files:**
- Create: `tests/graph/test_doc_qa_with_planning.py`

- [ ] **Step 1: 写端到端测试**

验证 query_planning + doc_qa 完整流程：

```python
# tests/graph/test_doc_qa_with_planning.py
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from langchain_core.messages import HumanMessage
from src.graph.nodes import State, query_planning, doc_qa

@pytest.mark.asyncio
async def test_query_planning_outputs_retrieval_plan():
    state: State = {
        "messages": [HumanMessage(content="BuyResource API 报错了是什么原因")],
        "intent": "doc_qa",
        "task_file_path": "",
        "task_file_paths": [],
        "generated_doc_paths": [],
        "retrieval_plan": [],
    }
    config = {}

    with patch("src.graph.nodes.get_llm") as mock_get_llm:
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"retrieval_plan":[{"project":"ubill-access-api","service":"order","information_types":["error_codes"],"search_strategy":"hybrid","search_query":"BuyResource 错误码"}]}'
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm

        with patch("src.graph.nodes.load_prompt") as mock_prompt:
            mock_tmpl = MagicMock()
            mock_tmpl.format_messages.return_value = []
            mock_prompt.return_value = mock_tmpl

            with patch("src.graph.nodes.load_catalog", return_value="{}"):
                result = await query_planning(state, config)
                assert "retrieval_plan" in result
                assert len(result["retrieval_plan"]) == 1
```

- [ ] **Step 2: Run test**

Run: `pytest tests/graph/test_doc_qa_with_planning.py -v`

- [ ] **Step 3: Commit**

```bash
git add tests/graph/test_doc_qa_with_planning.py
git commit -m "test: add end-to-end test for query_planning + doc_qa flow"
```

---

## 自检清单

- [ ] spec 覆盖：每个设计需求都有对应任务实现
- [ ] 无 placeholder：没有 TBD/TODO/不完整的步骤
- [ ] 类型一致性：Chunk.metadata 字段在各任务中保持一致
- [ ] Top-k 配置：统一使用 `_TOP_K = 5`
- [ ] 依赖正确：`rank_bm25` 需添加到 `pyproject.toml`

## 依赖更新

在 `pyproject.toml` 中添加：

```toml
[dependency-groups]
rag = ["rank_bm25"]
```
