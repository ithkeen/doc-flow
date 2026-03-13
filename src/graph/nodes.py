"""图节点与状态定义。

定义 State 类型、节点函数和路由函数。
"""

from __future__ import annotations

import json
import re
from typing import Annotated

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from typing_extensions import TypedDict
from langgraph.graph import END
from langgraph.graph.message import add_messages

from src.config import settings
from src.logs import get_logger
from src.prompts import load_prompt

logger = get_logger(__name__)

_NODE_LLM_ATTR = {
    "intent": "intent_llm",
    "doc_gen": "doc_gen_llm",
    "doc_qa": "doc_qa_llm",
    "chat": "chat_llm",
}


def _get_node_llm(node_name: str) -> ChatOpenAI:
    """根据节点名称返回对应配置的 ChatOpenAI 实例，未配置字段 fallback 到全局。"""
    attr = _NODE_LLM_ATTR.get(node_name)
    node_cfg = getattr(settings, attr, None) if attr else None

    base_url = node_cfg.base_url if (node_cfg and node_cfg.base_url is not None) else settings.llm.base_url
    api_key = node_cfg.api_key if (node_cfg and node_cfg.api_key is not None) else settings.llm.api_key
    model = node_cfg.model if (node_cfg and node_cfg.model is not None) else settings.llm.model

    return ChatOpenAI(base_url=base_url, api_key=api_key, model=model)


class State(TypedDict):
    """图的共享状态。"""

    messages: Annotated[list, add_messages]
    intent: str
    confidence: float
    params: dict


INTENT_LIST = "doc_gen, doc_qa, chat"


async def intent_recognize(state: State, config: RunnableConfig) -> dict:
    """意图识别节点。

    分析用户输入，判断意图类别，返回 intent / confidence / params。
    """
    prompt = load_prompt("intent")
    user_input = state["messages"][-1].content

    messages = prompt.format_messages(
        user_input=user_input,
    )

    llm = ChatOpenAI(
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
        model=settings.llm.model,
    )
    response = await llm.ainvoke(messages, config=config)

    raw = response.content
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw, re.DOTALL)
    if m:
        raw = m.group(1)

    try:
        parsed = json.loads(raw)
        intent = parsed.get("intent", "unknown")
        confidence = float(parsed.get("confidence", 0.0))
        params = parsed.get("params", {})
    except (json.JSONDecodeError, ValueError):
        logger.warning("意图识别结果解析失败，原始内容：%s", response.content)
        intent = "unknown"
        confidence = 0.0
        params = {}

    logger.info("意图识别完成：intent=%s, confidence=%.2f", intent, confidence)
    return {"intent": intent, "confidence": confidence, "params": params}


from src.tools.code_scanner import scan_directory
from src.tools.file_reader import read_file
from src.tools.doc_storage import save_document, read_document, list_documents
from src.tools.code_search import find_function

TOOLS = [scan_directory, read_file, save_document, read_document, list_documents, find_function]

QA_TOOLS = [read_document, list_documents]


def _get_last_human_message(messages: list) -> str:
    """返回消息列表中最后一条 HumanMessage 的内容。"""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content
    return ""


async def doc_qa(state: State, config: RunnableConfig) -> dict:
    """文档问答节点。

    使用 doc_qa 提示词和绑定工具的 LLM 回答文档相关问题。
    与 qa_tools ToolNode 形成 ReAct 循环。
    """
    prompt = load_prompt("doc_qa")
    user_input = _get_last_human_message(state["messages"])

    system_messages = prompt.format_messages(user_input=user_input)

    llm = ChatOpenAI(
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
        model=settings.llm.model,
    )
    llm_with_tools = llm.bind_tools(QA_TOOLS)

    all_messages = system_messages + state["messages"]
    response = await llm_with_tools.ainvoke(all_messages, config=config)

    logger.info("文档问答节点调用完成")
    return {"messages": [response]}


async def doc_gen(state: State, config: RunnableConfig) -> dict:
    """文档生成节点。

    使用 doc_gen 提示词和绑定工具的 LLM 生成文档。
    与 ToolNode 形成 ReAct 循环。
    """
    prompt = load_prompt("doc_gen")
    file_path = state["params"].get("file_path", "")

    system_messages = prompt.format_messages(file_path=file_path)

    llm = ChatOpenAI(
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
        model=settings.llm.model,
    )
    llm_with_tools = llm.bind_tools(TOOLS)

    all_messages = system_messages + state["messages"]
    response = await llm_with_tools.ainvoke(all_messages, config=config)

    logger.info("文档生成节点调用完成")
    return {"messages": [response]}


async def chat(state: State, config: RunnableConfig) -> dict:
    """聊天节点。

    使用 chat 提示词与 LLM 进行自由对话，不绑定工具。
    通过 system prompt 柔和引导用户使用文档功能。
    """
    prompt = load_prompt("chat")
    user_input = _get_last_human_message(state["messages"])

    system_messages = prompt.format_messages(user_input=user_input)

    llm = ChatOpenAI(
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
        model=settings.llm.model,
    )

    all_messages = system_messages + state["messages"]
    response = await llm.ainvoke(all_messages, config=config)

    logger.info("聊天节点调用完成")
    return {"messages": [response]}


def route_by_intent(state: State) -> str:
    """根据意图识别结果路由到对应节点。"""
    if state["intent"] == "doc_gen":
        return "doc_gen"
    if state["intent"] == "doc_qa":
        return "doc_qa"
    if state["intent"] == "chat":
        return "chat"
    return END


def route_doc_gen(state: State) -> str:
    """根据 LLM 是否发起工具调用决定下一步。"""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END


def route_doc_qa(state: State) -> str:
    """根据 LLM 是否发起工具调用决定下一步。"""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "qa_tools"
    return END
