"""图编排。

构建并编译 LangGraph StateGraph，串联意图识别、文档生成和工具执行。
"""

from __future__ import annotations

from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode

from src.graph.nodes import (
    TOOLS,
    State,
    doc_gen,
    intent_recognize,
    route_by_intent,
    route_doc_gen,
)


def build_graph() -> StateGraph:
    """构建并编译 agent 工作流图。

    Returns:
        编译后的 CompiledStateGraph，可直接 invoke。
    """
    graph = StateGraph(State)

    graph.add_node("intent_recognize", intent_recognize)
    graph.add_node("doc_gen", doc_gen)
    graph.add_node("tools", ToolNode(tools=TOOLS))

    graph.add_edge(START, "intent_recognize")
    graph.add_conditional_edges("intent_recognize", route_by_intent, ["doc_gen", "__end__"])
    graph.add_conditional_edges("doc_gen", route_doc_gen, ["tools", "__end__"])
    graph.add_edge("tools", "doc_gen")

    return graph.compile()
