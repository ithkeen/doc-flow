# doc_qa RAG 检索设计

## 概述

完善 doc_qa 模块，引入基于 Chroma 向量数据库的 RAG（检索增强生成）能力，使 doc_qa 能够从已生成的 API 文档中检索相关内容并回答用户问题。

## 现状分析

doc_qa 当前是一个纯 LLM 调用节点：
- 系统提示引用了 `list_documents` 和 `read_document` 工具，但这两个工具**不存在**
- 节点未绑定任何工具，图中无 ReAct 循环
- LLM 只能凭自身知识回答或拒绝回答

## 架构设计

### 整体流程

```
┌─────────────────────────────────────────────────┐
│                   doc-flow                       │
│                                                  │
│  ┌──────────────┐     ┌───────────────────────┐ │
│  │  批量索引脚本  │     │      doc_qa 节点       │ │
│  │              │     │                       │ │
│  │ 扫描 docs_   │     │ 用户提问               │ │
│  │ space_dir    │     │   ↓                   │ │
│  │   ↓          │     │ Chroma 向量检索 top-k  │ │
│  │ 读取 .md     │     │   ↓                   │ │
│  │   ↓          │     │ 相关文档注入 prompt    │ │
│  │ embedding    │     │   ↓                   │ │
│  │   ↓          │     │ LLM 生成回答          │ │
│  │ upsert       │     │   ↓                   │ │
│  │ Chroma       │     │ 返回结果              │ │
│  └──────┬───────┘     └───────────────────────┘ │
│         │                       ↑                │
│         └───────→ Chroma DB ────┘                │
│                (本地持久化)                        │
└─────────────────────────────────────────────────┘
```

### 关键决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 向量数据库 | Chroma（本地持久化） | 轻量、内嵌、无需外部服务，适合内部工具 |
| Embedding 模型 | 远程 API（复用 LLM 端点） | 与现有基础设施一致，仅需新增模型名称配置 |
| 检索模式 | 经典 RAG（检索+生成） | 单次检索 + LLM 生成，流程确定，延迟低 |
| 分块策略 | 整文档嵌入 | 每个接口一个 .md 文件，文档不大，无需分块 |
| 入库时机 | 批量索引脚本（优先） | 与 doc_gen 解耦，开发简单 |
| 图结构 | 不变（doc_qa → END） | 检索在节点内部完成，无需工具循环 |

## 模块设计

### 1. 批量索引脚本 — `scripts/index_docs.py`

**职责：** 扫描 `docs_space_dir` 下的 .md 文件，做 embedding 后 upsert 到 Chroma。

**流程：**
1. 递归扫描 `docs_space_dir` 下所有 `.md` 文件
2. 对每个文件：读取 UTF-8 内容，从目录结构提取元数据
3. 以文件相对路径为 document ID，调用 `collection.upsert()`
4. 打印处理统计

**元数据设计：**
```python
{
    "source": "project_a/module_x/GetUser.md",  # 相对路径，即 doc ID
    "project": "project_a",                       # 路径第一级
    "module": "module_x",                         # 路径第二级
    "api_name": "GetUser",                        # 文件名（去 .md）
}
```

**使用方式：**
```bash
python scripts/index_docs.py                                # 索引所有文档
python scripts/index_docs.py --file project_a/mod/Api.md    # 索引单个文件（相对于 docs_space_dir）
```

**Chroma 配置：**
- Collection 名称：`ubill_docs`
- 持久化目录：环境变量 `CHROMA_PERSIST_DIR`，默认 `./data/chroma`

### 2. RAG 模块 — `src/rag/`

新增模块封装向量检索能力。

**`src/rag/__init__.py`** — 模块入口

**`src/rag/retriever.py`** — 核心检索逻辑：
- `get_retriever(k=3)` → 返回 Chroma retriever 实例
  - 初始化 Chroma client（持久化模式）
  - 获取 `ubill_docs` collection
  - 返回 `as_retriever(search_kwargs={"k": k})`

**`src/rag/embeddings.py`** — Embedding 模型配置：
- `get_embeddings()` → 返回 `OpenAIEmbeddings` 实例
  - 复用 `settings.llm.base_url` 和 `settings.llm.api_key`
  - 使用 `settings.llm.embed_model` 指定模型

### 3. doc_qa 节点改造 — `src/graph/nodes.py`

**改造后逻辑：**
```python
async def doc_qa(state: State) -> dict:
    prompt_template = load_prompt("doc_qa")
    user_input = _get_last_human_message(state)

    # 向量检索
    retriever = get_retriever()
    docs = await retriever.ainvoke(user_input)
    context = format_retrieved_docs(docs)

    # context 注入 prompt
    formatted = prompt_template.format_messages(
        user_input=user_input,
        context=context
    )

    llm = get_llm("doc_qa")
    response = await llm.ainvoke(formatted + state["messages"])
    return {"messages": [response]}
```

**`format_retrieved_docs(docs)`：** 将检索到的 Document 列表格式化为带来源标注的文本，供 prompt 使用。

### 4. Prompt 更新 — `src/prompts/system/doc_qa.md`

**变更：**
- 移除对不存在的 `list_documents`、`read_document` 工具的引用
- 增加 `{context}` 占位符
- 指导 LLM 基于提供的文档上下文回答
- 保留"仅基于文档回答"的约束和中文回复要求

### 5. 配置扩展

**新增环境变量：**
```
LLM_EMBED_MODEL=text-embedding-3-small
CHROMA_PERSIST_DIR=./data/chroma
```

**Settings 扩展（`src/config/settings.py`）：**
- `LLMSettings` 新增 `embed_model: str` 字段
- 新增 `ChromaSettings` 配置类（`persist_dir`, `collection_name="ubill_docs"`）
- `Settings` 新增 `chroma: ChromaSettings` 字段

**LLM 配置扩展（`src/config/llm.py`）：**
- 新增 `get_embeddings()` 函数

**新增依赖：**
- `chromadb`
- `langchain-chroma`

## 边界情况处理

| 场景 | 处理方式 |
|------|---------|
| Chroma 未初始化 / collection 为空 | 检索返回空列表 → context 为空 → LLM 回答"文档库中暂无相关文档" |
| 检索结果相关度低 | 可设置 score threshold 过滤 |
| 文档编码问题 | 索引脚本统一使用 UTF-8 读取 |
| 持久化目录不存在 | 首次运行自动创建 |

## 文件变更清单

| 操作 | 文件 |
|------|------|
| 新增 | `scripts/index_docs.py` |
| 新增 | `src/rag/__init__.py` |
| 新增 | `src/rag/retriever.py` |
| 新增 | `src/rag/embeddings.py` |
| 修改 | `src/graph/nodes.py` — doc_qa 节点增加检索逻辑 |
| 修改 | `src/prompts/system/doc_qa.md` — 移除工具引用，增加 context |
| 修改 | `src/prompts/user/doc_qa.md` — 可能需要调整模板变量 |
| 修改 | `src/config/settings.py` — 新增 embedding 和 chroma 配置 |
| 修改 | `src/config/llm.py` — 新增 get_embeddings() |
| 修改 | `.env.example` — 新增环境变量 |
| 修改 | `pyproject.toml` 或 `requirements.txt` — 新增依赖 |
