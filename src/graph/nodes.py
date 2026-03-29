"""图节点与状态定义。

定义 State 类型、节点函数和路由函数。
"""

from __future__ import annotations

import json
import operator
import re
from pathlib import Path
from typing import Annotated

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from typing_extensions import TypedDict
from langgraph.graph import END
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Send

from src.config import settings
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
    # project_explore dispatch fields
    task_file_paths: Annotated[list[str], operator.add]
    """待生成文档的源码文件路径列表（从 task.md 解析）。"""
    generated_doc_paths: Annotated[list[str], operator.add]
    """各 worker 生成的文档文件路径列表（累积）。"""


class DocGenWorkerState(TypedDict):
    """doc_gen_worker 子图专用状态。"""

    messages: Annotated[list, add_messages]
    """消息历史，ReAct 循环使用。"""
    intent: str
    """固定为 "doc_gen"。"""
    file_path: str
    """待生成文档的源码文件路径。"""
    generated_doc_path: str
    """生成的文档文件路径（单文件），由 doc_gen 工具写入后填充。"""


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


def _make_tool_router(tool_node_name: str, fallthrough: str = "doc_gen_dispatcher"):
    """创建工具路由函数：有 tool_calls 则路由到工具节点，否则路由到 fallthrough。"""

    def router(state: State) -> str:
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return tool_node_name
        return fallthrough

    return router


def _make_tool_router_end(tool_node_name: str):
    """创建工具路由函数：有 tool_calls 则路由到工具节点，否则结束。"""

    def router(state: State) -> str:
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return tool_node_name
        return END

    return router


route_doc_gen = _make_tool_router_end("doc_gen_tools")
route_project_explore = _make_tool_router("explore_tools", "doc_gen_dispatcher")


# ---------------------------------------------------------------------------
# project_explore → doc_gen parallel dispatch
# ---------------------------------------------------------------------------


def _read_task_file(project_name: str) -> tuple[str, list[str]]:
    """从 docs_space_dir 读取 task.md，返回 (原始内容, 源码文件路径列表)。

    解析 markdown 表格，从 API列表 / 定时任务列表 / 消息订阅列表 的处理文件列
    提取所有 .go/.py/.java/.ts/.js 源码文件路径。
    """
    task_path = Path(settings.docs_space_dir) / project_name / "task.md"
    if not task_path.exists():
        return "", []
    content = task_path.read_text(encoding="utf-8")

    file_paths: list[str] = []
    for line in content.splitlines():
        line = line.strip()
        # 跳过非表格行
        if not line or line.startswith("#") or line.startswith("---"):
            continue
        if line.startswith("|"):
            # 解析 markdown 表格行：| col1 | col2 | col3 | col4 |
            cols = [c.strip() for c in line.split("|")]
            # 去掉首尾空字符串（split 时两端产生的空列）
            cols = [c for c in cols if c]
            # 查找处理文件列（最后一个含 "/" 的列，通常是第 3 或 4 列）
            for col in cols:
                if "/" in col and any(ext in col for ext in (".go", ".py", ".java", ".ts", ".js")):
                    file_paths.append(col)
                    break
    return content, file_paths


async def doc_gen_dispatcher(state: State, config: RunnableConfig) -> dict:
    """读取 project_explore 输出的 task.md，提取源码文件路径写入 state。

    解析 task.md 提取所有源码文件路径，写入 task_file_paths 供后续 Send fan-out 使用。
    """
    logger.info("doc_gen_dispatcher 开始解析 task.md")

    # 从 project_explore 的 tool_calls 中找到写入的 task.md 路径
    task_file_path = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls"):
            for tc in msg.tool_calls or []:
                if tc["name"] == "write_file":
                    fp = tc["args"].get("file_path", "")
                    if "task.md" in fp:
                        task_file_path = fp
                        break
        if task_file_path:
            break

    if not task_file_path:
        logger.warning("未找到 task.md 写入记录，跳过 dispatch")
        return {"task_file_paths": []}

    # 提取项目名：task_file_path 格式 "{项目名}/task.md"
    project_name = task_file_path.replace("/task.md", "").split("/")[0]

    _, file_paths = _read_task_file(project_name)
    logger.info("从 task.md 解析到 %d 个待生成文件", len(file_paths))

    return {"task_file_paths": file_paths}


def route_doc_gen_dispatcher(state: State) -> list[Send]:
    """Send fan-out：有待处理文件时，为每个文件创建 Send 到 doc_gen_worker。无可处理文件时路由到 synthesize_overview。"""
    file_paths = state.get("task_file_paths", [])
    if not file_paths:
        return ["synthesize_overview"]
    return [Send("doc_gen_worker", {"file_path": fp}) for fp in file_paths]


def _route_doc_gen_end(state: DocGenWorkerState) -> str:
    """doc_gen 子图专用路由：有 tool_calls 则继续执行工具，否则结束。"""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "doc_gen_tools"
    return END


def build_doc_gen_react_graph() -> CompiledStateGraph:
    """构建 doc_gen ReAct 子图，供 doc_gen_worker 并行调用。"""
    from src.graph.graph import build_graph as _build_main_graph

    builder = StateGraph(DocGenWorkerState)
    builder.add_node("doc_gen", doc_gen)
    builder.add_node("doc_gen_tools", ToolNode(tools=DOC_GEN_TOOLS))
    builder.add_edge(START, "doc_gen")
    builder.add_conditional_edges("doc_gen", _route_doc_gen_end, ["doc_gen_tools", END])
    builder.add_edge("doc_gen_tools", "doc_gen")
    return builder.compile()


# 模块级缓存子图编译结果
_doc_gen_react_graph: CompiledStateGraph | None = None


def _get_doc_gen_react_graph() -> CompiledStateGraph:
    """返回单例 doc_gen ReAct 子图。"""
    global _doc_gen_react_graph
    if _doc_gen_react_graph is None:
        _doc_gen_react_graph = build_doc_gen_react_graph()
    return _doc_gen_react_graph


async def doc_gen_worker(state: State, config: RunnableConfig) -> dict:
    """单个文件生成文档 worker（由 Send 并行调用）。

    调用 doc_gen ReAct 子图处理单个文件，返回生成的文档路径供父状态累积。
    """
    file_path = state.get("file_path", "")  # type: ignore[index]
    if not file_path:
        return {"generated_doc_paths": []}

    user_input = f"生成 {file_path} 的文档"

    # 构造子图初始状态
    worker_initial: DocGenWorkerState = {
        "messages": [HumanMessage(content=user_input)],
        "intent": "doc_gen",
        "file_path": file_path,
        "generated_doc_path": "",
    }

    # 调用子图，执行完整 ReAct 循环
    sub_config: RunnableConfig = {"configurable": config.get("configurable", {})}
    sub_result = await _get_doc_gen_react_graph().ainvoke(worker_initial, sub_config)

    # 从子图结果提取生成的文档路径
    doc_path = sub_result.get("generated_doc_path", "")
    if not doc_path:
        # 兜底：从 messages 中查找 write_file 调用记录
        for msg in reversed(sub_result.get("messages", [])):
            if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls"):
                for tc in getattr(msg, "tool_calls", []) or []:
                    if tc.get("name") == "write_file":
                        fp = tc.get("args", {}).get("file_path", "")
                        if fp and fp.endswith(".md") and "task.md" not in fp:
                            doc_path = fp
                            break
            if doc_path:
                break

    logger.info("doc_gen_worker 完成：%s → %s", file_path, doc_path)
    return {"generated_doc_paths": [doc_path] if doc_path else []}


async def synthesize_overview(state: State, config: RunnableConfig) -> dict:
    """读取所有生成的文档，汇总写入项目级 overview.md。"""
    project_name = ""
    for fp in state.get("task_file_paths", []):
        if "/" in fp:
            project_name = fp.split("/")[0]
            break

    if not project_name:
        return {"messages": [AIMessage(content="项目概览生成失败：无法确定项目名称")]}

    overview_path = Path(settings.docs_space_dir) / project_name / "overview.md"
    sections: list[str] = [f"# {project_name} 项目概览\n"]

    # 读取 task.md 获取项目结构信息
    task_path = Path(settings.docs_space_dir) / project_name / "task.md"
    if task_path.exists():
        sections.append(task_path.read_text(encoding="utf-8"))
        sections.append("\n---\n\n## 已生成的文档列表\n")
    else:
        sections.append("\n## 已生成的文档列表\n")

    # 读取各生成的文档，提取标题
    for doc_fp in state.get("generated_doc_paths", []):
        full_path = Path(settings.docs_space_dir) / doc_fp
        if full_path.exists():
            content = full_path.read_text(encoding="utf-8")
            first_line = content.split("\n")[0].lstrip("# ").strip()
            sections.append(f"- [{first_line}]({doc_fp})\n")

    overview_content = "".join(sections)
    overview_path.parent.mkdir(parents=True, exist_ok=True)
    overview_path.write_text(overview_content, encoding="utf-8")

    logger.info("项目概览已生成：%s", overview_path)
    return {
        "messages": [
            AIMessage(
                content=f"项目文档已全部生成，共 {len(state.get('generated_doc_paths', []))} 个文件。"
                f"概览已保存至 {project_name}/overview.md"
            )
        ]
    }
