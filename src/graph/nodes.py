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
    find_function,
    find_struct,
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
    return END


async def doc_gen(state: State, config: RunnableConfig) -> dict:
    """文档生成节点。

    使用 doc_gen 提示词和绑定 8 个工具的 LLM 生成 API 文档。
    与 doc_gen_tools ToolNode 形成 ReAct 循环。
    """
    prompt = load_prompt("doc_gen")
    user_input = _get_last_human_message(state["messages"])

    system_messages = prompt.format_messages(user_input=user_input)

    llm = get_llm("doc_gen")
    llm_with_tools = llm.bind_tools(DOC_GEN_TOOLS)

    all_messages = system_messages + state["messages"]
    response = await llm_with_tools.ainvoke(all_messages, config=config)

    logger.info("文档生成节点调用完成")
    return {"messages": [response]}


def route_doc_gen(state: State) -> str:
    """根据 LLM 是否发起工具调用决定下一步。"""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "doc_gen_tools"
    return END
