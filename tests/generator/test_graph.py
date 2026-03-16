"""Tests for generator graph construction."""

from src.generator.graph import GenState, build_generator_graph


def test_gen_state_has_required_fields():
    state = GenState(
        messages=[],
        project="access",
        module="order",
        function_name="CreateOrder",
        source_file="access/order/logic/create.go",
        source_line=45,
    )
    assert state["project"] == "access"
    assert state["function_name"] == "CreateOrder"


def test_build_generator_graph_compiles():
    graph = build_generator_graph()
    assert graph is not None
    node_names = set(graph.get_graph().nodes.keys())
    assert "gen_doc" in node_names
    assert "gen_tools" in node_names
