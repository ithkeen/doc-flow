"""Chainlit 聊天入口。

通过 `chainlit run src/app.py` 启动，提供浏览器聊天界面。
"""

import chainlit as cl
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from src.graph import build_graph
from src.logs import get_logger

logger = get_logger(__name__)

graph = build_graph()


@cl.on_chat_start
async def on_chat_start():
    """新会话开始时发送欢迎消息。"""
    await cl.Message(
        content="你好！我是 doc-flow，你可以让我为 Go 源码文件生成 API 文档，或者基于已有文档提问。"
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    """处理用户消息，流式输出 graph 结果。"""
    cb = cl.LangchainCallbackHandler(
        to_ignore=[
            "ChannelRead",
            "RunnableLambda",
            "ChannelWrite",
            "__start__",
            "_execute",
        ]
    )
    config = RunnableConfig(callbacks=[cb])
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
                and metadata["langgraph_node"] in ("doc_gen", "doc_qa")
            ):
                await answer.stream_token(msg.content)
    except Exception:
        logger.exception("graph 执行出错")
        answer.content = "抱歉，处理过程中出现错误，请稍后重试。"

    if not answer.content:
        answer.content = "抱歉，我目前支持文档生成和文档问答功能。你可以让我为某个文件生成文档，或者基于已有文档提问。"

    await answer.send()
