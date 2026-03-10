"""提示词模块。

从模板文件加载提示词，返回 LangChain ChatPromptTemplate。

Usage::

    from src.prompts import load_prompt

    prompt = load_prompt("intent")
    chain = prompt | llm
    result = chain.invoke({"user_input": "...", "intent_list": "..."})
"""

from src.prompts.loader import load_prompt

__all__ = ["load_prompt"]
