"""图节点与状态定义。

定义 State 类型、节点函数和路由函数。
"""

from __future__ import annotations

import json
import re
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from typing_extensions import TypedDict
from langgraph.graph import END
from langgraph.graph.message import add_messages

from src.config import settings
from src.logs import get_logger
from src.prompts import load_prompt

logger = get_logger(__name__)


class State(TypedDict):
    """图的共享状态。"""

    messages: Annotated[list, add_messages]
    intent: str
    confidence: float
    params: dict


INTENT_LIST = "doc_gen"


async def intent_recognize(state: State, config: RunnableConfig) -> dict:
    """意图识别节点。

    分析用户输入，判断意图类别，返回 intent / confidence / params。
    """
    prompt = load_prompt("intent")
    user_input = state["messages"][-1].content

    messages = prompt.format_messages(
        intent_list=INTENT_LIST,
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

TOOLS = [scan_directory, read_file, save_document, read_document, list_documents]


async def doc_gen(state: State, config: RunnableConfig) -> dict:
    """文档生成节点。

    使用 doc_gen 提示词和绑定工具的 LLM 生成文档。
    与 ToolNode 形成 ReAct 循环。
    """
    prompt = load_prompt("doc_gen")
    directory_path = state["params"].get("directory_path", "")

    system_messages = prompt.format_messages(directory_path=directory_path)

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


def route_by_intent(state: State) -> str:
    """根据意图识别结果路由到对应节点。"""
    if state["intent"] == "doc_gen":
        return "doc_gen"
    return END


def route_doc_gen(state: State) -> str:
    """根据 LLM 是否发起工具调用决定下一步。"""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END
