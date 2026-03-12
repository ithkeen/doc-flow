"""graph 编排单元测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph


class TestBuildGraph:
    """build_graph 工厂函数测试。"""

    def test_returns_compiled_graph(self):
        from src.graph.graph import build_graph

        graph = build_graph()
        assert isinstance(graph, CompiledStateGraph)

    def test_graph_has_expected_nodes(self):
        from src.graph.graph import build_graph

        graph = build_graph()
        node_names = set(graph.nodes.keys())
        assert "intent_recognize" in node_names
        assert "doc_gen" in node_names
        assert "tools" in node_names

    def test_graph_has_doc_qa_and_qa_tools_nodes(self):
        from src.graph.graph import build_graph

        graph = build_graph()
        node_names = set(graph.nodes.keys())
        assert "doc_qa" in node_names
        assert "qa_tools" in node_names

    def test_graph_has_chat_node(self):
        from src.graph.graph import build_graph

        graph = build_graph()
        node_names = set(graph.nodes.keys())
        assert "chat" in node_names


class TestModuleExport:
    """验证模块导出。"""

    def test_build_graph_importable_from_package(self):
        from src.graph import build_graph as fn

        assert callable(fn)


class TestBuildGraphWithCheckpointer:
    """build_graph 传入 checkpointer 参数测试。"""

    def test_accepts_checkpointer_parameter(self):
        from langgraph.checkpoint.memory import MemorySaver
        from src.graph.graph import build_graph

        memory = MemorySaver()
        graph = build_graph(checkpointer=memory)
        assert isinstance(graph, CompiledStateGraph)

    def test_default_none_checkpointer_still_works(self):
        from src.graph.graph import build_graph

        graph = build_graph()
        assert isinstance(graph, CompiledStateGraph)

    @pytest.mark.asyncio
    @patch("src.graph.nodes.ChatOpenAI")
    async def test_multi_turn_preserves_history(self, mock_chat_cls):
        """同一 thread_id 第二次调用时，状态应包含第一次的消息历史。"""
        from langgraph.checkpoint.memory import MemorySaver
        from src.graph.graph import build_graph

        # Mock LLM: intent_recognize returns doc_qa, doc_qa returns simple answer
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=AIMessage(
                content='{"intent": "doc_qa", "confidence": 0.9, "params": {}}'
            )
        )
        mock_llm_with_tools = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm_with_tools
        mock_llm_with_tools.ainvoke = AsyncMock(
            return_value=AIMessage(content="回答")
        )
        mock_chat_cls.return_value = mock_llm

        memory = MemorySaver()
        graph = build_graph(checkpointer=memory)
        config = RunnableConfig(configurable={"thread_id": "test-thread"})

        # Turn 1
        await graph.ainvoke(
            {"messages": [HumanMessage(content="第一轮")]}, config=config
        )
        # Turn 2
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="第二轮")]}, config=config
        )

        # The messages list should contain messages from both turns
        contents = [m.content for m in result["messages"]]
        assert "第一轮" in contents
        assert "第二轮" in contents
