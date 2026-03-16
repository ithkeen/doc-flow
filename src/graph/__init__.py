"""图编排模块。

使用 LangGraph 构建 agent 工作流，编排意图识别、文档问答与自由聊天。

Usage::

    from src.graph import build_graph

    graph = build_graph()
    result = graph.invoke({"messages": [("human", "handler 模块有哪些接口？")]})
"""

from src.graph.graph import build_graph

__all__ = ["build_graph"]
