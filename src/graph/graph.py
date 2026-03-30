"""图编排。

构建并编译 LangGraph StateGraph，串联意图识别、文档问答、文档生成和自由聊天。
"""

from __future__ import annotations

from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import ToolNode

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from src.graph.nodes import (
    DOC_GEN_TOOLS,
    EXPLORE_TOOLS,
    State,
    chat,
    doc_gen,
    doc_gen_dispatcher,
    doc_qa,
    intent_recognize,
    project_explore,
    route_by_intent,
    route_doc_gen,
    route_project_explore,
    synthesize_overview,
)


def create_graph() -> CompiledStateGraph:
    """langgraph dev 入口：无参工厂函数，checkpointer 由 API Server 管理。"""
    return build_graph()


def build_graph(checkpointer=None) -> CompiledStateGraph:
    """构建并编译 agent 工作流图。

    Returns:
        编译后的 CompiledStateGraph，可直接 invoke。
    """
    graph = StateGraph(State)

    graph.add_node("intent_recognize", intent_recognize)
    graph.add_node("doc_qa", doc_qa)
    graph.add_node("doc_gen", doc_gen)
    graph.add_node("doc_gen_tools", ToolNode(tools=DOC_GEN_TOOLS))
    graph.add_node("chat", chat)
    graph.add_node("project_explore", project_explore)
    graph.add_node("explore_tools", ToolNode(tools=EXPLORE_TOOLS))
    graph.add_node("doc_gen_dispatcher", doc_gen_dispatcher)
    graph.add_node("synthesize_overview", synthesize_overview)

    graph.add_edge(START, "intent_recognize")
    graph.add_conditional_edges(
        "intent_recognize", route_by_intent, ["doc_qa", "doc_gen", "chat", "project_explore", "doc_gen_dispatcher", END]
    )
    graph.add_conditional_edges("doc_gen", route_doc_gen, ["doc_gen_tools", END])
    graph.add_edge("doc_gen_tools", "doc_gen")
    # project_explore ReAct loop: explore_tools → project_explore → ... → doc_gen_dispatcher
    graph.add_conditional_edges(
        "project_explore", route_project_explore, ["explore_tools", "doc_gen_dispatcher"]
    )
    graph.add_edge("explore_tools", "project_explore")
    # dispatcher 顺序派发任务，完成后直接汇总
    graph.add_edge("doc_gen_dispatcher", "synthesize_overview")
    graph.add_edge("synthesize_overview", END)
    graph.add_edge("doc_qa", END)
    graph.add_edge("chat", END)

    return graph.compile(checkpointer=checkpointer)
