"""生成专用图。

独立的 LangGraph StateGraph，用于单个 API 的文档生成 ReAct 循环。
"""

from __future__ import annotations

from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from src.config.llm import get_node_llm
from src.logs import get_logger
from src.prompts import load_prompt
from src.tools.code_search import find_function
from src.tools.doc_storage import save_document
from src.tools.file_reader import read_file

logger = get_logger(__name__)

GEN_TOOLS = [read_file, find_function, save_document]


class GenState(TypedDict):
    """生成图的状态。"""

    messages: Annotated[list, add_messages]
    project: str
    module: str
    function_name: str
    source_file: str
    source_line: int


async def gen_doc(state: GenState, config: RunnableConfig) -> dict:
    """文档生成节点。"""
    prompt = load_prompt("batch_doc_gen")
    system_messages = prompt.format_messages(
        project=state["project"],
        module=state["module"],
        function_name=state["function_name"],
        source_file=state["source_file"],
        source_line=state["source_line"],
    )
    llm = get_node_llm("doc_gen")
    llm_with_tools = llm.bind_tools(GEN_TOOLS)
    all_messages = system_messages + state["messages"]
    response = await llm_with_tools.ainvoke(all_messages, config=config)
    logger.info("生成节点调用完成: %s", state["function_name"])
    return {"messages": [response]}


def route_gen_doc(state: GenState) -> str:
    """根据 LLM 是否发起工具调用决定下一步。"""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "gen_tools"
    return END


def build_generator_graph():
    """构建生成专用图。"""
    graph = StateGraph(GenState)
    graph.add_node("gen_doc", gen_doc)
    graph.add_node("gen_tools", ToolNode(tools=GEN_TOOLS))
    graph.add_edge(START, "gen_doc")
    graph.add_conditional_edges("gen_doc", route_gen_doc, ["gen_tools", "__end__"])
    graph.add_edge("gen_tools", "gen_doc")
    return graph.compile()
