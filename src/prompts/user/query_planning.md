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
