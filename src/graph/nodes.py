"""图节点与状态定义。

定义 State 类型、节点函数和路由函数。
"""

from __future__ import annotations

import json
import re
from typing import Annotated

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from typing_extensions import TypedDict
from langgraph.graph import END
from langgraph.graph.message import add_messages

from src.config.llm import get_llm
from src.logs import get_logger
from src.prompts import load_prompt
from src.rag import get_retriever, format_retrieved_docs
from src.tools import (
    find_files,
    find_function,
    find_struct,
    list_directory,
    load_docgen_config,
    match_api_name,
    query_api_index,
    read_file,
    save_api_index,
    write_file,
)

logger = get_logger(__name__)


class State(TypedDict):
    """图的共享状态。"""

    messages: Annotated[list, add_messages]
    intent: str


async def intent_recognize(state: State, config: RunnableConfig) -> dict:
    """意图识别节点。

    分析用户输入，判断意图类别，返回 intent。
    """
    prompt = load_prompt("intent")
    user_input = state["messages"][-1].content

    messages = prompt.format_messages(
        user_input=user_input,
    )

    llm = get_llm("intent")
    response = await llm.ainvoke(messages, config=config)

    raw = response.content
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw, re.DOTALL)
    if m:
        raw = m.group(1)

    try:
        parsed = json.loads(raw)
        intent = parsed.get("intent", "unknown")
    except (json.JSONDecodeError, ValueError):
        logger.warning("意图识别结果解析失败，原始内容：%s", response.content)
        intent = "unknown"

    logger.info("意图识别完成：intent=%s", intent)
    return {"intent": intent}


DOC_GEN_TOOLS = [
    load_docgen_config,
    match_api_name,
    query_api_index,
    read_file,
    find_function,
    find_struct,
    write_file,
    save_api_index,
]

EXPLORE_TOOLS = [
    list_directory,
    find_files,
    read_file,
    find_function,
    find_struct,
    load_docgen_config,
    write_file,
]


def _get_last_human_message(messages: list) -> str:
    """返回消息列表中最后一条 HumanMessage 的内容。"""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content
    return ""


async def doc_qa(state: State, config: RunnableConfig) -> dict:
    """文档问答节点。

    从 Chroma 向量库检索相关文档，注入 prompt 上下文，生成回答。
    """
    prompt = load_prompt("doc_qa")
    user_input = _get_last_human_message(state["messages"])

    # 向量检索（失败时降级为空上下文）
    try:
        retriever = get_retriever()
        docs = await retriever.ainvoke(user_input)
        context = format_retrieved_docs(docs)
    except Exception:
        logger.exception("文档检索失败，使用空上下文")
        context = ""

    # context 注入 prompt
    system_messages = prompt.format_messages(
        user_input=user_input,
        context=context,
    )

    llm = get_llm("doc_qa")

    all_messages = system_messages + state["messages"]
    response = await llm.ainvoke(all_messages, config=config)

    logger.info("文档问答节点调用完成")
    return {"messages": [response]}


async def chat(state: State, config: RunnableConfig) -> dict:
    """聊天节点。

    使用 chat 提示词与 LLM 进行自由对话，不绑定工具。
    通过 system prompt 柔和引导用户使用文档功能。
    """
    prompt = load_prompt("chat")
    user_input = _get_last_human_message(state["messages"])

    system_messages = prompt.format_messages(user_input=user_input)

    llm = get_llm("chat")

    all_messages = system_messages + state["messages"]
    response = await llm.ainvoke(all_messages, config=config)

    logger.info("聊天节点调用完成")
    return {"messages": [response]}


def route_by_intent(state: State) -> str:
    """根据意图识别结果路由到对应节点。"""
    if state["intent"] == "doc_qa":
        return "doc_qa"
    if state["intent"] == "doc_gen":
        return "doc_gen"
    if state["intent"] == "chat":
        return "chat"
    if state["intent"] == "project_explore":
        return "project_explore"
    return END


def _make_react_node(prompt_name: str, tools: list):
    """创建 ReAct 循环节点：加载 prompt、绑定工具、调用 LLM。"""

    async def node(state: State, config: RunnableConfig) -> dict:
        prompt = load_prompt(prompt_name)
        user_input = _get_last_human_message(state["messages"])
        system_messages = prompt.format_messages(user_input=user_input)
        llm = get_llm(prompt_name)
        llm_with_tools = llm.bind_tools(tools)
        all_messages = system_messages + state["messages"]
        response = await llm_with_tools.ainvoke(all_messages, config=config)
        logger.info("%s 节点调用完成", prompt_name)
        return {"messages": [response]}

    node.__name__ = prompt_name
    return node


doc_gen = _make_react_node("doc_gen", DOC_GEN_TOOLS)
project_explore = _make_react_node("project_explore", EXPLORE_TOOLS)


def _make_tool_router(tool_node_name: str):
    """创建工具路由函数：有 tool_calls 则路由到工具节点，否则结束。"""

    def router(state: State) -> str:
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return tool_node_name
        return END

    return router


route_doc_gen = _make_tool_router("doc_gen_tools")
route_project_explore = _make_tool_router("explore_tools")
