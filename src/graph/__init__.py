"""图编排模块。

使用 LangGraph 构建 agent 工作流，编排意图识别与文档生成。

Usage::

    from src.graph import build_graph

    graph = build_graph()
    result = graph.invoke({"messages": [("human", "请为 ./handler 生成文档")]})
"""

from src.graph.graph import build_graph

__all__ = ["build_graph"]
