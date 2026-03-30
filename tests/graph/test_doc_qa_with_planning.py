"""Tests for the doc_qa node with query_planning retrieval plan."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

# Mock mysql.connector which is imported by src.tools.api_index
if "mysql" not in sys.modules:
    sys.modules["mysql"] = MagicMock()
    sys.modules["mysql.connector"] = MagicMock()


@pytest.mark.asyncio
async def test_query_planning_outputs_retrieval_plan():
    """query_planning 输出正确的 retrieval_plan 结构"""
    from src.graph.nodes import State, query_planning

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
                assert result["retrieval_plan"][0]["project"] == "ubill-access-api"
                assert result["retrieval_plan"][0]["service"] == "order"


@pytest.mark.asyncio
async def test_doc_qa_with_retrieval_plan():
    """doc_qa 使用 retrieval_plan 执行多路检索"""
    from src.graph.nodes import State, doc_qa

    state: State = {
        "messages": [HumanMessage(content="BuyResource API 报错了")],
        "intent": "doc_qa",
        "task_file_path": "",
        "task_file_paths": [],
        "generated_doc_paths": [],
        "retrieval_plan": [
            {
                "project": "ubill-access-api",
                "service": "order",
                "information_types": ["error_codes"],
                "search_strategy": "hybrid",
                "search_query": "BuyResource 错误码"
            }
        ],
    }
    config = {}

    with patch("src.graph.nodes.get_llm") as mock_get_llm:
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "根据文档，BuyResource 报错可能是因为..."
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm

        with patch("src.graph.nodes.load_prompt") as mock_prompt:
            mock_tmpl = MagicMock()
            mock_tmpl.format_messages.return_value = []
            mock_prompt.return_value = mock_tmpl

            with patch("src.rag.hybrid_retriever.HybridRetriever") as mock_hr:
                mock_instance = MagicMock()
                mock_instance.invoke.return_value = [
                    MagicMock(page_content="## 错误码\n10001: 输入无效", metadata={"source": "a.md", "section": "error_codes"})
                ]
                mock_hr.return_value = mock_instance

                result = await doc_qa(state, config)
                assert "messages" in result
                # HybridRetriever should have been called
                mock_instance.invoke.assert_called()


@pytest.mark.asyncio
async def test_doc_qa_fallback_empty_plan():
    """doc_qa 在 retrieval_plan 为空时 graceful fallback"""
    from src.graph.nodes import State, doc_qa

    state: State = {
        "messages": [HumanMessage(content="随便问点什么")],
        "intent": "doc_qa",
        "task_file_path": "",
        "task_file_paths": [],
        "generated_doc_paths": [],
        "retrieval_plan": [],  # 空
    }
    config = {}

    with patch("src.graph.nodes.get_llm") as mock_get_llm:
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "我没有足够的上下文来回答这个问题。"
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm

        with patch("src.graph.nodes.load_prompt") as mock_prompt:
            mock_tmpl = MagicMock()
            mock_tmpl.format_messages.return_value = []
            mock_prompt.return_value = mock_tmpl

            # Should NOT call HybridRetriever when plan is empty
            with patch("src.rag.hybrid_retriever.HybridRetriever") as mock_hr:
                result = await doc_qa(state, config)
                mock_hr.assert_not_called()
                assert "messages" in result
