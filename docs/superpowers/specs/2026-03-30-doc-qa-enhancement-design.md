# doc_qa 节点增强设计

## 背景

当前 `doc_qa` 节点是单步检索：用户问题 → Chroma top-3 向量检索 → LLM 生成回答。

存在三个痛点：
1. **检索结果不准确** — 整文件检索，噪声多
2. **回答质量不够高** — 无上下文规划，检索盲目
3. **覆盖场景太单一** — 无法处理跨项目、需多步推理的复杂问题

## 目标

将 `doc_qa` 从单步检索升级为**两阶段子图**：
1. `query_planning` — 分析用户问题，结合 Catalog 生成检索计划
2. `doc_qa` — 按检索计划执行检索，生成回答

## Catalog 结构

Catalog 是项目的元数据索引，作为 `query_planning` 的参考依据，按项目分块。

```json
{
  "catalog": [
    {
      "project": {
        "name": "ubill-access-api",
        "description": "统一计费访问层，提供订单、资源购买等 API 接口"
      },
      "services": [
        {
          "name": "order",
          "description": "订单处理模块，负责订单的创建、查询、取消等操作",
          "match_rules": [
            {
              "type": "keywords",
              "values": ["订单", "创建订单", "取消订单", "order"]
            },
            {
              "type": "semantic",
              "description": "订单创建、查询、取消相关业务"
            }
          ],
          "typical_queries": [
            "如何创建订单",
            "订单状态如何流转",
            "订单取消后如何退款"
          ]
        },
        {
          "name": "transaction",
          "description": "交易事务模块，处理支付、退款等事务",
          "match_rules": [
            {
              "type": "keywords",
              "values": ["交易", "退款", "支付", "transaction"]
            },
            {
              "type": "semantic",
              "description": "支付、退款、事务相关"
            }
          ],
          "typical_queries": [
            "如何申请退款",
            "支付失败了怎么办"
          ]
        }
      ]
    }
  ]
}
```

### Catalog 字段说明

| 层级 | 字段 | 说明 |
|------|------|------|
| project | name | 项目名称，唯一标识 |
| project | description | 项目整体介绍 |
| service | name | 服务/模块名称 |
| service | description | 模块功能详细介绍 |
| service | match_rules | 检索匹配规则，含 keywords 和 semantic 两种 |
| service | typical_queries | 典型问题示例，用于规则兜底 |

### Catalog 持久化

- 存储位置：`DOCS_SPACE_DIR/catalog/index.json`
- 索引时加载到内存，供 `query_planning` 实时引用
- 后续可扩展为独立向量库检索（目前先读文件）

## query_planning 节点

### 职责

接收用户原始问题，输出结构化的**检索计划**（retrieval_plan），供后续 doc_qa 执行。

### 实现方式

纯提示词驱动 LLM 输出 JSON，Catalog 作为上下文注入。

### prompt 设计

```
你是一个文档检索规划助手。
根据用户问题和 Catalog 信息，生成检索计划。

## Catalog
{catalog_content}

## 用户问题
{user_question}

## 约束
- 只能检索 catalog 中已存在的项目和服务
- 每个检索单元对应一次独立的检索操作
- search_query 用自然语言描述要检索什么，长度 5-15 字
- information_types 可选值：overview, parameters, response, error_codes, examples, flow, all
- search_strategy 可选值：semantic（向量检索）, keyword（BM25）, hybrid（混合）

## 输出格式
返回 JSON：
{
  "retrieval_plan": [
    {
      "project": "项目名",
      "service": "服务名",
      "information_types": ["error_codes"],
      "search_strategy": "hybrid",
      "search_query": "BuyResource 错误码"
    }
  ]
}
```

### 输出结构

```json
{
  "retrieval_plan": [
    {
      "project": "ubill-access-api",
      "service": "order",
      "information_types": ["error_codes", "overview"],
      "search_strategy": "hybrid",
      "search_query": "BuyResource API 报错原因"
    },
    {
      "project": "ubill-worker",
      "service": "cron",
      "information_types": ["overview"],
      "search_strategy": "semantic",
      "search_query": "定时任务执行失败"
    }
  ],
  "original_question": "BuyResource API 报错了是什么原因"
}
```

### 检索单元字段

| 字段 | 作用 |
|------|------|
| project | 限定项目范围，用于元数据过滤 |
| service | 限定服务范围，用于元数据过滤 |
| information_types | 决定返回哪些章节（后续用于结果过滤/排序） |
| search_strategy | 决定用哪种检索方式 |
| search_query | 实际检索词，直接执行检索 |

## 文档分块策略

### 分块原则

索引时按 Markdown 标题（`##`/`###`）切分，每个块为独立语义单元，保留 `parent_doc_id` 关联原始文档。

### 块元数据

```json
{
  "page_content": "## 错误码\n\n| 错误码 | 触发条件 | 描述 |\n...",
  "metadata": {
    "source": "ubill-access-api/order/BuyResource.md",
    "project": "ubill-access-api",
    "service": "order",
    "api_name": "BuyResource",
    "section": "error_codes",
    "parent_doc_id": "ubill-access-api/order/BuyResource.md"
  }
}
```

### section 映射

| 章节 | section 值 |
|------|-----------|
| 概述 | overview |
| 请求参数 | parameters |
| 响应 | response |
| 执行流程 | flow |
| 错误码 | error_codes |
| 请求示例 | examples |
| 响应示例 | examples |

## 检索执行（doc_qa 子图）

### 流程

1. 读取 `retrieval_plan`
2. 对每个检索单元：
   - 根据 `project`、`service` 做元数据过滤
   - 根据 `search_query` 执行对应策略的检索
   - 根据 `information_types` 对结果进行章节级别的过滤/排序
3. 合并所有检索单元的结果
4. 注入上下文，LLM 生成回答

### 混合检索实现

```
retrieval_results = parallel(
    vector_search(query, top-k),
    bm25_search(query, top-k)
)
merged = merge_and_deduplicate(retrieval_results)
filtered = filter_by_section_priority(merged, information_types)
```

### Top-k 配置

统一配置 `TOP_K`，不对每个检索单元分别设置。

默认值：`TOP_K = 5`

### 信息类型优先级

`information_types` 用于对检索结果过滤/排序：
- 用户指定特定类型（如 error_codes）时，该章节的块排在最前
- 未指定时，整文档召回

## 图结构变更

```
START → intent_recognize → route_by_intent → [doc_qa]
                                        ↓
                              query_planning
                                        ↓
                              doc_qa_with_plan
                                        ↓
                                       END
```

或保持 doc_qa 名字，内部拆分为两个节点：
- `doc_qa_planning` — query_planning 逻辑
- `doc_qa_retrieve` — 实际检索 + 回答

## 索引脚本更新

`scripts/index_docs.py` 需改造：

1. **分块索引**：按标题切分文档，每块单独入库
2. **元数据丰富**：提取 project、service、api_name、section 等字段
3. **Catalog 生成**：可选项，从项目结构自动生成 catalog 草稿

## 测试计划

1. 简单问题（单项目单服务）→ retrieval_plan 正确
2. 跨项目问题 → 多个检索单元
3. 无匹配项目时 → graceful fallback
4. 检索结果质量对比旧版

## 已确认

- **Catalog 维护方式**：手动编辑，模版见 `docs/catalog-template.json`
- **Rerank**：不引入交叉编码器重排
- **Top-k**：统一配置，默认 TOP_K=5
