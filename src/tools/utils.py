"""工具响应格式化工具模块。

本模块提供统一的工具响应格式（JSON Envelope 模式）。
所有工具的返回值都使用 ok() 或 fail() 包装，确保响应格式一致。

JSON Envelope 格式：
{
    "success": bool,      # 操作是否成功
    "message": str,       # 给 LLM 看的描述性消息
    "payload": Any,       # 实际数据（成功时）
    "error": str | None   # 错误信息（失败时）
}

这种格式的优势：
1. LLM 可以快速判断操作是否成功（通过 success 字段）
2. message 提供人类可读的描述
3. payload 包含结构化数据供后续处理
4. error 提供详细的错误信息用于调试
"""
import json
from typing import Any


def ok(message: str, payload: Any = None) -> str:
    """构建成功的 envelope 响应。

    用于工具执行成功时返回结果。message 描述操作结果，
    payload 包含实际数据（如文件内容、文件列表等）。

    Args:
        message: 描述性消息，告诉 LLM 操作成功的情况，如 "找到 3 个文件"
        payload: 可选的实际数据，可以是字符串、列表、字典等任意可序列化对象

    Returns:
        str: JSON 格式的响应字符串

    Example:
        >>> ok("找到 3 个文件", payload="file1.go\nfile2.go\nfile3.go")
        '{"success": true, "message": "找到 3 个文件", "payload": "...", "error": null}'
    """
    return json.dumps(
        {"success": True, "message": message, "payload": payload, "error": None},
        ensure_ascii=False,
    )


def fail(error: str, message: str | None = None) -> str:
    """构建失败的 envelope 响应。

    用于工具执行失败时返回错误信息。error 是详细的错误描述，
    message 是可选的简短说明（如果不提供，则使用 error 作为 message）。

    Args:
        error: 详细的错误信息，如 "文件不存在" 或 "权限不足"
        message: 可选的简短消息，如果不提供则使用 error

    Returns:
        str: JSON 格式的响应字符串

    Example:
        >>> fail("文件 test.go 不存在")
        '{"success": false, "message": "文件 test.go 不存在", "payload": null, "error": "..."}'
    """
    return json.dumps(
        {"success": False, "message": message or error, "payload": None, "error": error},
        ensure_ascii=False,
    )
