"""图节点与状态定义。

定义 State 类型、节点函数和路由函数。
"""

from __future__ import annotations

import asyncio
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

_JSON_CODE_FENCE_RE = r"```(?:json)?\s*\n?(.*?)\n?\s*```"


def load_catalog() -> str:
    """加载 Catalog JSON 内容，供 query_planning 使用。"""
    catalog_path = Path(settings.docs_space_dir) / "catalog" / "index.json"
    try:
        return catalog_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "{}"


class State(TypedDict):
    """图的共享状态。"""

    messages: Annotated[list, add_messages]
    intent: str
    # batch_doc_gen standalone: 任务文件路径
    task_file_path: str
    """batch_doc_gen 模式下任务文件的原始路径（如 'proj/task.md'）。"""
    # project_explore dispatch fields
    task_file_paths: Annotated[list[str], operator.add]
    """待生成文档的源码文件路径列表（从 task.md 解析）。"""
    generated_doc_paths: Annotated[list[str], operator.add]
    """各 worker 生成的文档文件路径列表（累积）。"""
    retrieval_plan: Annotated[list, operator.add]
    """doc_qa 检索规划节点输出的结构化检索计划。"""


class DocGenWorkerState(TypedDict):
    """doc_gen_dispatcher 调用子图时的状态。"""

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
        task_file_path = parsed.get("task_file_path", "")
    except (json.JSONDecodeError, ValueError):
        logger.warning("意图识别结果解析失败，原始内容：%s", response.content)
        intent = "unknown"
        task_file_path = ""

    logger.info("意图识别完成：intent=%s, task_file_path=%s", intent, task_file_path)
    return {"intent": intent, "task_file_path": task_file_path}


async def query_planning(state: State, config: RunnableConfig) -> dict:
    """检索规划节点。

    分析用户问题，参考 Catalog，输出结构化 retrieval_plan。
    """
    prompt = load_prompt("query_planning")
    user_input = _get_last_human_message(state["messages"])
    catalog_content = load_catalog()

    system_messages = prompt.format_messages(
        user_question=user_input,
        catalog_content=catalog_content,
    )

    llm = get_llm("intent")
    response = await llm.ainvoke(system_messages, config=config)

    raw = response.content
    # 解析 JSON
    try:
        # 尝试从 markdown code fence 中提取
        m = re.search(_JSON_CODE_FENCE_RE, raw, re.DOTALL)
        if m:
            raw = m.group(1)
        parsed = json.loads(raw)
        retrieval_plan = parsed.get("retrieval_plan", [])
    except (json.JSONDecodeError, ValueError):
        logger.warning("retrieval_plan 解析失败，原始内容：%s", response.content)
        retrieval_plan = []

    logger.info("query_planning 完成，retrieval_plan 条目数：%d", len(retrieval_plan))
    return {"retrieval_plan": retrieval_plan}


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

    按 retrieval_plan 执行多路混合检索，生成回答。
    """
    from langchain_core.documents import Document
    from src.rag.hybrid_retriever import HybridRetriever

    prompt = load_prompt("doc_qa")
    user_input = _get_last_human_message(state["messages"])
    retrieval_plan = state.get("retrieval_plan", [])
    logger.info("retrieval_plan 内容：%s", retrieval_plan)

    # 无 retrieval_plan 时 fallback 到空检索（graceful degradation）
    if not retrieval_plan:
        context = ""
    else:
        retriever = HybridRetriever(top_k=5)
        all_docs: list[Document] = []
        try:
            for unit in retrieval_plan:
                docs = retriever.invoke(
                    query=unit.get("search_query", user_input),
                    project=unit.get("project"),
                    service=unit.get("service"),
                    strategy=unit.get("search_strategy", "hybrid"),
                )
                all_docs.extend(docs)
        except Exception:
            logger.exception("检索失败，使用空上下文")
            all_docs = []

        # 按 source + section 去重，保持顺序
        seen: set[str] = set()
        unique_docs: list[Document] = []
        for doc in all_docs:
            key = doc.metadata.get("source", "") + doc.metadata.get("section", "")
            if key not in seen:
                seen.add(key)
                unique_docs.append(doc)

        context = format_retrieved_docs(unique_docs)

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
        return "query_planning"
    if state["intent"] == "doc_gen":
        return "doc_gen"
    if state["intent"] == "chat":
        return "chat"
    if state["intent"] == "project_explore":
        return "project_explore"
    if state["intent"] == "batch_doc_gen":
        return "doc_gen_dispatcher"
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


def _make_tool_router(tool_node_name: str, fallthrough: str = END):
    """创建工具路由函数：有 tool_calls 则路由到工具节点，否则路由到 fallthrough。"""

    def router(state: State) -> str:
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return tool_node_name
        return fallthrough

    return router


route_doc_gen = _make_tool_router("doc_gen_tools")
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
    """读取 project_explore 输出的 task.md，顺序派发文档生成任务（间隔 5s）。

    支持两种模式：
    1. Standalone：从 state["task_file_path"] 读取（intent_recognize 写入门）
    2. Graph flow：从 project_explore 的 tool_calls 中找到写入的 task.md 路径
    """
    logger.info("doc_gen_dispatcher 开始解析 task.md")

    # 优先从 state 读取（standalone 模式，intent_recognize 写入）
    task_file_path = state.get("task_file_path", "")
    if task_file_path:
        logger.info("从 state 读取到 task_file_path=%s", task_file_path)

    # 如果 state 中没有，尝试从 messages 中查找（graph flow 模式）
    if not task_file_path:
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
        logger.warning("未找到 task.md，跳过 dispatch")
        return {"generated_doc_paths": []}

    # 提取项目名：task_file_path 格式 "{项目名}/{task_file_name}"
    # project_name 是 task_file_path 的第二层目录（从右数第二段）
    parts = task_file_path.split("/")
    project_name = parts[-2] if len(parts) >= 2 else parts[0]
    logger.info("task_file_path=%s, project_name=%s", task_file_path, project_name)

    _, file_paths = _read_task_file(project_name)
    logger.info("从 task.md 解析到 %d 个待生成文件", len(file_paths))

    if not file_paths:
        return {"generated_doc_paths": []}

    # 顺序调用子图生成文档，间隔 5 秒
    all_doc_paths: list[str] = []
    sub_config: RunnableConfig = {"configurable": config.get("configurable", {})}

    for i, fp in enumerate(file_paths):
        logger.info("正在生成文档 [%d/%d]: %s", i + 1, len(file_paths), fp)
        user_input = f"生成 {fp} 的文档"
        worker_initial: DocGenWorkerState = {
            "messages": [HumanMessage(content=user_input)],
            "intent": "doc_gen",
            "file_path": fp,
            "generated_doc_path": "",
        }
        sub_result = await _get_doc_gen_react_graph().ainvoke(worker_initial, sub_config)
        doc_path = sub_result.get("generated_doc_path", "")
        if not doc_path:
            for msg in reversed(sub_result.get("messages", [])):
                if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls"):
                    for tc in getattr(msg, "tool_calls", []) or []:
                        if tc["name"] == "write_file":
                            fp = tc["args"].get("file_path", "") or ""
                            if fp and fp.endswith(".md") and "task.md" not in fp:
                                doc_path = fp
                                break
                if doc_path:
                    break
        if doc_path:
            all_doc_paths.append(doc_path)
        # 间隔 5 秒，避免频繁请求
        if i < len(file_paths) - 1:
            await asyncio.sleep(5)

    logger.info("doc_gen_dispatcher 完成，共生成 %d 个文档", len(all_doc_paths))
    return {"generated_doc_paths": all_doc_paths}


def _route_doc_gen_end(state: DocGenWorkerState) -> str:
    """doc_gen 子图专用路由：有 tool_calls 则继续执行工具，否则结束。"""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "doc_gen_tools"
    return END


def build_doc_gen_react_graph() -> CompiledStateGraph:
    """构建 doc_gen ReAct 子图，供 doc_gen_dispatcher 顺序调用。"""
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
