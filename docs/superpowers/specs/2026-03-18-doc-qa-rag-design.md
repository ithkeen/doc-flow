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
- Collection 名称：通过 `settings.chroma.collection_name` 配置，默认 `ubill_docs`
- 持久化目录：通过 `settings.chroma.persist_dir` 配置（环境变量 `CHROMA_PERSIST_DIR`），默认 `./data/chroma`

### 2. RAG 模块 — `src/rag/`

新增模块封装向量检索能力。

**`src/rag/__init__.py`** — 模块入口

**`src/rag/retriever.py`** — 核心检索逻辑：
- `get_retriever(k=3)` → 返回 Chroma retriever 实例（使用模块级缓存避免重复初始化）
  - 初始化 Chroma client（持久化模式）
  - 获取 `settings.chroma.collection_name` collection
  - 返回 `as_retriever(search_kwargs={"k": k})`
- `format_retrieved_docs(docs: list[Document]) -> str` → 格式化检索结果
  - 输入：LangChain Document 列表
  - 输出：格式化的文本字符串，每个文档包含来源标注
  - 格式示例：
    ```
    文档 1 (来源: project_a/module_x/GetUser.md):
    [文档内容]

    文档 2 (来源: project_a/module_y/CreateUser.md):
    [文档内容]
    ```
  - 空列表处理：返回空字符串（由 prompt 指导 LLM 回答"文档库中暂无相关内容"）

**`src/rag/embeddings.py`** — Embedding 模型配置：
- `get_embeddings()` → 返回 `OpenAIEmbeddings` 实例
  - 复用 `settings.llm.base_url` 和 `settings.llm.api_key`
  - 使用 `settings.llm.embed_model` 指定模型

### 3. doc_qa 节点改造 — `src/graph/nodes.py`

**改造后逻辑：**
```python
async def doc_qa(state: State) -> dict:
    prompt_template = load_prompt("doc_qa")
    user_input = _get_last_human_message(state["messages"])

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

**`format_retrieved_docs(docs)`：** 定义在 `src/rag/retriever.py` 中，详见上方 RAG 模块设计。

### 4. Prompt 更新

**`src/prompts/system/doc_qa.md` 变更：**
- 移除对不存在的 `list_documents`、`read_document` 工具的引用
- 增加 `{context}` 占位符（放置在系统提示中，在指令之后）
- 指导 LLM 基于提供的文档上下文回答
- 保留"仅基于文档回答"的约束和中文回复要求
- 当 `{context}` 为空时，指导 LLM 回答"文档库中暂无相关内容"

**`src/prompts/user/doc_qa.md` 变更：**
- 保持现有 `{user_input}` 占位符不变

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

**LLM 配置（`src/config/llm.py`）：**
- 无需新增函数（`get_embeddings()` 放在 `src/rag/embeddings.py` 中）
- **注意：** `get_llm("doc_qa")` 继续使用 `default_model`（当前 model_map 中无 `doc_qa` 条目，有意使用默认模型）

**新增依赖：**
- `chromadb`
- `langchain-chroma`

## 边界情况处理

| 场景 | 处理方式 |
|------|---------|
| Chroma 未初始化 / collection 为空 | 检索返回空列表 → context 为空 → LLM 回答"文档库中暂无相关文档" |
| 检索结果相关度低 | 暂不设置 score threshold，作为后续优化项。首版使用 top-k 直接返回 |
| 文档编码问题 | 索引脚本统一使用 UTF-8 读取 |
| 持久化目录不存在 | 首次运行自动创建 |

## 测试策略

| 测试类型 | 测试内容 |
|---------|---------|
| 单元测试 | `format_retrieved_docs()` 的格式化逻辑（空列表、单文档、多文档） |
| 单元测试 | `get_retriever()` 的缓存机制（使用 mock Chroma client） |
| 集成测试 | `doc_qa` 节点的完整流程（mock retriever 返回预设文档） |
| 脚本测试 | `index_docs.py` 的索引功能（使用临时目录和测试文档） |

## 未来优化方向

| 优化项 | 说明 |
|--------|------|
| 实时索引 | doc_gen 生成文档后自动触发 embedding 入库 |
| 相关度阈值 | 引入 `similarity_score_threshold` 过滤低相关度结果 |
| 删除文档同步 | 索引脚本增加清理功能，移除已删除文件的 embedding |
| Embedding 端点兼容性验证 | 确认 `settings.llm.base_url` 支持 `/v1/embeddings` API |

## 文件变更清单

| 操作 | 文件 |
|------|------|
| 新增 | `scripts/index_docs.py` |
| 新增 | `src/rag/__init__.py` |
| 新增 | `src/rag/retriever.py` |
| 新增 | `src/rag/embeddings.py` |
| 修改 | `src/graph/nodes.py` — doc_qa 节点增加检索逻辑 |
| 修改 | `src/prompts/system/doc_qa.md` — 移除工具引用，增加 context 占位符 |
| 修改 | `src/config/settings.py` — 新增 embedding 和 chroma 配置 |
| 修改 | `.env.example` — 新增环境变量 |
| 修改 | `pyproject.toml` 或 `requirements.txt` — 新增依赖 |
