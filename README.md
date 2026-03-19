# doc-flow

基于 LangGraph 的 API 文档智能问答与生成系统。通过意图识别将用户查询路由到专业节点，支持 RAG 文档问答、ReAct 工具循环驱动的文档自动生成，以及日常对话。目标代码库为 Go 源码。

## 功能特性

- **文档问答 (doc_qa)** — 基于 RAG 检索已有文档，回答用户关于 API 文档的问题
- **文档生成 (doc_gen)** — 通过 ReAct 工具循环自动读取 Go 源码并生成 API 文档（含 Mermaid 流程图）
- **日常对话 (chat)** — 通用对话，引导用户使用文档相关功能
- **意图识别** — LLM 自动判断用户意图，路由到对应处理节点
- **向量检索** — Chroma 向量数据库存储文档嵌入，支持语义搜索
- **API 索引** — MySQL 持久化 API 索引记录，支持查询与更新

## 架构

```
START → intent_recognize → route_by_intent → doc_qa  → END
                                            → doc_gen ↔ doc_gen_tools (ReAct loop)
                                            → chat    → END
```

### 核心模块

| 模块 | 路径 | 说明 |
|------|------|------|
| 图定义 | `src/graph/` | StateGraph 构建、节点函数、路由逻辑 |
| 工具集 | `src/tools/` | 8 个工具：文件读写、Go 代码搜索、API 匹配、配置加载、索引管理 |
| 提示词 | `src/prompts/` | 4 组 system/user 提示词模板（intent、doc_qa、doc_gen、chat） |
| RAG | `src/rag/` | Chroma 向量检索器、嵌入模型封装 |
| 配置 | `src/config/` | Pydantic Settings 单例，LLM 工厂函数 |
| 日志 | `src/logs/` | JSON 格式日志，按天轮转 |
| 脚本 | `scripts/` | 文档批量索引到 Chroma |

### 工具列表

| 工具 | 功能 | 操作目录 |
|------|------|----------|
| `read_file` | 读取源码文件 | CODE_SPACE_DIR |
| `write_file` | 写入文档文件 | DOCS_SPACE_DIR |
| `find_function` | 查找 Go 函数定义 | CODE_SPACE_DIR |
| `find_struct` | 查找 Go 结构体定义 | CODE_SPACE_DIR |
| `match_api_name` | 正则匹配 API 名称 | CODE_SPACE_DIR |
| `load_docgen_config` | 读取文档生成配置 | DOCS_SPACE_DIR |
| `save_api_index` | 保存 API 索引到 MySQL | MySQL |
| `query_api_index` | 查询 MySQL API 索引 | MySQL |

## 快速开始

### 环境要求

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) 包管理器
- MySQL（可选，仅 API 索引功能需要）

### 安装

```bash
# 克隆仓库
git clone <repo-url>
cd doc-flow

# 安装依赖
uv sync

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入实际值
```

### 环境变量

| 变量 | 说明 | 必填 |
|------|------|------|
| `CODE_SPACE_DIR` | Go 源码根目录 | 是 |
| `DOCS_SPACE_DIR` | 文档输出根目录 | 是 |
| `LLM_BASE_URL` | OpenAI 兼容 API 地址 | 是 |
| `LLM_API_KEY` | LLM API 密钥 | 是 |
| `LLM_DEFAULT_MODEL` | 默认模型 | 是 |
| `LLM_DOC_GEN_MODEL` | 文档生成模型 | 是 |
| `LLM_CHAT_MODEL` | 对话模型 | 是 |
| `LLM_EMBED_MODEL` | 嵌入模型 | 是 |
| `CHROMA_PERSIST_DIR` | Chroma 持久化目录 | 是 |
| `LANGSMITH_*` | LangSmith 追踪配置 | 是 |
| `LOG_LEVEL` | 日志级别 | 是 |
| `LOG_DIR` | 日志目录 | 是 |
| `DB_*` | MySQL 连接配置 | 否 |

### 运行

```bash
# 启动 Chainlit 聊天界面
chainlit run app.py

# 或使用 LangGraph Studio
langgraph dev
```

### 索引文档

将已有 Markdown 文档索引到 Chroma 向量数据库，以启用 RAG 问答：

```bash
# 索引 DOCS_SPACE_DIR 下所有 .md 文件
python scripts/index_docs.py

# 索引单个文件
python scripts/index_docs.py --file proj/mod/Api.md
```

### 数据库初始化（可选）

如需使用 API 索引功能，执行建表 SQL：

```bash
mysql -u root -p doc_flow < schema/api_index.sql
```

## 开发

### 运行测试

```bash
# 全部测试
pytest

# 单个测试文件
pytest tests/graph/test_doc_qa.py

# 单个测试用例
pytest tests/graph/test_doc_qa.py::test_doc_qa_retrieves_docs_and_injects_context
```

### 项目结构

```
doc-flow/
├── app.py                  # Chainlit 入口
├── langgraph.json          # LangGraph Studio 配置
├── src/
│   ├── config/             # 配置管理（Settings 单例、LLM 工厂）
│   ├── graph/              # 图定义与节点
│   ├── logs/               # 日志模块
│   ├── prompts/            # 提示词模板（system/ + user/）
│   ├── rag/                # RAG 检索模块
│   └── tools/              # 8 个 LangGraph 工具
├── scripts/                # 文档索引脚本
├── schema/                 # 数据库 DDL
├── template/               # 文档生成配置模板
├── tests/                  # 测试用例
└── data/chroma/            # Chroma 持久化数据
```

### 文档生成配置

在 `DOCS_SPACE_DIR` 下放置 `.doc_gen.yaml` 配置文件，定义项目路径与模块映射。参考模板：`template/.doc_gen.yaml`。
