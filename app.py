"""Chainlit 聊天入口。

通过 `chainlit run app.py` 启动，提供浏览器聊天界面。
"""

from uuid import uuid4

import chainlit as cl
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver

from src.graph import build_graph
from src.logs import get_logger

logger = get_logger(__name__)

# Module-level: persists across requests within the Chainlit process
memory = MemorySaver()
graph = build_graph(checkpointer=memory)


@cl.on_chat_start
async def on_chat_start():
    """新会话开始时生成 thread_id 并发送欢迎消息。"""
    cl.user_session.set("thread_id", str(uuid4()))
    await cl.Message(
        content="你好！我是 doc-flow，你可以让我为 Go 源码文件生成 API 文档，或者基于已有文档提问。"
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    """处理用户消息，流式输出 graph 结果。"""
    thread_id = cl.user_session.get("thread_id")

    cb = cl.LangchainCallbackHandler(
        to_ignore=[
            "ChannelRead",
            "RunnableLambda",
            "ChannelWrite",
            "__start__",
            "_execute",
        ]
    )
    config = RunnableConfig(
        callbacks=[cb],
        configurable={"thread_id": thread_id},
    )
    answer = cl.Message(content="")

    try:
        async for msg, metadata in graph.astream(
            {"messages": [HumanMessage(content=message.content)]},
            stream_mode="messages",
            config=config,
        ):
            if (
                msg.content
                and not isinstance(msg, HumanMessage)
                and metadata["langgraph_node"] in ("doc_gen", "doc_qa", "chat")
            ):
                await answer.stream_token(msg.content)
    except Exception:
        logger.exception("graph 执行出错")
        answer.content = "抱歉，处理过程中出现错误，请稍后重试。"

    if not answer.content:
        answer.content = "抱歉，我暂时无法理解你的意思。你可以让我进行文档生成、文档问答，也可以和我自由聊天。"

    await answer.send()
