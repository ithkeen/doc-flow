# 提示词模块设计文档

## 概述

为 doc-flow 项目实现提示词管理模块，将提示词内容与代码逻辑分离，通过模板文件管理系统提示词和用户提示词，使用 LangChain 原生 `ChatPromptTemplate` 加载。

## 需求总结

| 项目 | 决策 |
|------|------|
| 用途 | 为各 LangGraph 节点提供提示词模板 |
| 模板格式 | `.md` 文件，LangChain `{variable}` 占位符 |
| 目录结构 | `system/` 和 `user/` 两个子目录，文件名对应节点名 |
| Python API | `load_prompt(name)` 工厂函数，返回 `ChatPromptTemplate` |
| 模板可选性 | system 和 user 均可选，但至少存在一个 |
| 外部依赖 | 仅 `langchain_core`（已有） |

## 模块结构

```
src/prompts/
├── __init__.py          # 导出 load_prompt
├── loader.py            # 加载逻辑
├── system/
│   ├── intent.md        # 意图识别 - 系统提示词
│   └── doc_gen.md       # 文档生成 - 系统提示词
└── user/
    ├── intent.md        # 意图识别 - 用户提示词
    └── doc_gen.md       # 文档生成 - 用户提示词（可选，ReAct 场景可能不需要）
```

## 加载器 API

### load_prompt(name)

按节点名称加载提示词，返回 `ChatPromptTemplate`。

```python
from pathlib import Path
from langchain_core.prompts import ChatPromptTemplate

_PROMPTS_DIR = Path(__file__).resolve().parent

def load_prompt(name: str) -> ChatPromptTemplate:
    """按节点名称加载提示词，返回 ChatPromptTemplate。

    Args:
        name: 提示词名称，对应 system/{name}.md 和 user/{name}.md

    Raises:
        FileNotFoundError: system 和 user 模板均不存在时抛出
    """
    system_path = _PROMPTS_DIR / "system" / f"{name}.md"
    user_path = _PROMPTS_DIR / "user" / f"{name}.md"

    messages = []
    if system_path.exists():
        messages.append(("system", system_path.read_text(encoding="utf-8").strip()))
    if user_path.exists():
        messages.append(("human", user_path.read_text(encoding="utf-8").strip()))

    if not messages:
        raise FileNotFoundError(
            f"提示词模板不存在: 至少需要 system/{name}.md 或 user/{name}.md 其中之一"
        )

    return ChatPromptTemplate.from_messages(messages)
```

### _read_template(role, name)

私有函数，读取单个模板文件内容。已内联到 `load_prompt` 中，外部无需关心。

### __init__.py

```python
from src.prompts.loader import load_prompt

__all__ = ["load_prompt"]
```

## 模板文件格式

模板文件为纯文本 Markdown，内容即提示词，变量使用 `{variable}` 占位符。

### 示例：system/intent.md

```markdown
你是一个智能代码文档生成助手的意图识别模块。

你的任务是分析用户的输入，判断其意图属于以下哪一类：
{intent_list}

请以 JSON 格式输出你的判断结果。
```

### 示例：user/intent.md

```markdown
用户输入：{user_input}
```

## 使用方式

### 在 LangGraph 节点中使用

```python
from src.prompts import load_prompt

# 意图识别节点 — 使用 system + user 模板
prompt = load_prompt("intent")
chain = prompt | llm
result = chain.invoke({"user_input": "帮我生成用户模块的接口文档", "intent_list": "..."})

# 文档生成节点（ReAct）— 可能只使用 system 模板
prompt = load_prompt("doc_gen")
```

## ReAct 场景说明

文档生成节点使用 ReAct 模式，agent 循环调用工具（扫描目录、读取文件、分析、生成、存储）。此场景下：

- `system/doc_gen.md` — 定义 agent 角色、行为规则、工具使用指南
- `user/doc_gen.md` — 可选，ReAct 循环中的 human message 通常来自实际用户输入

## 扩展性

新增节点只需：
1. 在 `system/` 和/或 `user/` 下新建对应的 `.md` 文件
2. 在节点代码中调用 `load_prompt("新节点名")`

无需修改 loader 代码或注册配置。

## 技术决策

- **模板文件分离**：提示词内容与代码逻辑解耦，非开发人员也可编辑提示词
- **工厂函数模式**：与项目现有风格一致（`get_logger(name)`、`ok()`/`fail()`）
- **LangChain 原生 PromptTemplate**：`{variable}` 占位符，与 LangChain 生态无缝集成
- **双可选设计**：system 和 user 模板均可选，适配不同节点类型（普通节点、ReAct agent）
