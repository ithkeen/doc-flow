"""graph 编排单元测试。"""

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


class TestModuleExport:
    """验证模块导出。"""

    def test_build_graph_importable_from_package(self):
        from src.graph import build_graph as fn

        assert callable(fn)
