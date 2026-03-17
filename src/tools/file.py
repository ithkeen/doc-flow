"""文件读写工具模块。

本模块提供 LangChain Tool 函数，用于读写文件。
- write_file: 写入到 docs_space_dir 下（文档输出目录）
- read_file:  读取 code_space_dir 下的文件（源码目录）

file_path 参数为相对路径，工具内部自动拼接为绝对路径。

Models:
    WriteFileInput — 文件写入输入参数

Tools:
    write_file — 写入文件到 docs_space_dir
    read_file  — 读取 code_space_dir 下的文件

Usage::

    from src.tools.file import write_file, read_file

    # 写入
    result = write_file.invoke({
        "file_path": "src/logic/xxx.md",
        "content": "# Title\\n\\nContent..."
    })

    # 读取
    result = read_file.invoke({
        "file_path": "src/logic/xxx.md"
    })

Example output::

    {"success": true, "message": "文件写入成功: src/logic/xxx.md", "payload": "src/logic/xxx.md", "error": null}
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool
from pydantic import BaseModel, ValidationError, field_validator

from src.config import settings
from src.logs import get_logger
from src.tools.utils import fail, ok

MAX_FILE_SIZE_KB = 100


# ---------------------------------------------------------------------------
# Pydantic input model
# ---------------------------------------------------------------------------


class WriteFileInput(BaseModel):
    """文件写入输入参数。

    Attributes:
        file_path: 相对于 docs_space_dir 的文件路径，如 "src/logic/xxx.md"，不可为空。
        content: 文件内容，不可为空。
    """

    file_path: str
    content: str

    @field_validator("file_path")
    @classmethod
    def file_path_must_be_valid(cls, v: str) -> str:
        """确保文件路径非空且不为目录。"""
        if not v.strip():
            raise ValueError("file_path 不能为空")
        if v.endswith("/") or v.endswith("\\"):
            raise ValueError("file_path 不能是目录路径")
        return v

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, v: str) -> str:
        """确保 content 非空白。"""
        if not v.strip():
            raise ValueError("content 不能为空")
        return v


logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# LangChain Tool
# ---------------------------------------------------------------------------


@tool
def write_file(file_path: str, content: str) -> str:
    """写入文件到 docs_space_dir 下的指定路径。

    将内容写入到 {docs_space_dir}/{file_path}。如果父目录不存在会自动创建。

    Args:
        file_path: 相对于 docs_space_dir 的文件路径，如 "src/logic/xxx.md"。
        content: 文件内容。

    Returns:
        JSON Envelope 格式的响应字符串：
        - 成功: {"success": true, "message": "...", "payload": "文件路径", "error": null}
        - 失败: {"success": false, "message": "...", "payload": null, "error": "..."}
    """
    # 1. 校验输入
    try:
        validated = WriteFileInput(
            file_path=file_path,
            content=content
        )
    except ValidationError as exc:
        logger.error("输入校验失败: %s", exc)
        return fail(error=f"输入校验失败: {exc}")

    # 2. 拼接绝对路径
    target_path = Path(settings.docs_space_dir) / validated.file_path

    # 3. 创建父目录
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.error("创建目录失败: %s", exc)
        return fail(error=f"创建目录失败: {exc}")

    # 4. 写入文件
    try:
        target_path.write_text(validated.content, encoding="utf-8")
    except Exception as exc:
        logger.error("写入文件失败: %s", exc)
        return fail(error=f"写入文件失败: {exc}")

    logger.info("成功写入文件: %s", validated.file_path)
    return ok(message=f"文件写入成功: {validated.file_path}", payload=validated.file_path)


@tool
def read_file(file_path: str) -> str:
    """读取 code_space_dir 下指定文件的完整内容。

    用于获取源代码文件的内容以分析接口定义，
    也可用于读取其他文件。

    Args:
        file_path: 相对于 code_space_dir 的文件路径，如 "src/logic/auth/login.go"。

    Returns:
        JSON Envelope 格式的响应字符串：
        - 成功: {"success": true, "message": "...", "payload": "文件内容", "error": null}
        - 失败: {"success": false, "message": "...", "payload": null, "error": "..."}
    """
    path = Path(settings.code_space_dir) / file_path

    if not path.exists():
        logger.error("文件读取失败：%s 不存在", file_path)
        return fail(f"文件 {file_path} 不存在")

    if not path.is_file():
        logger.error("文件读取失败：%s 不是文件", file_path)
        return fail(f"{file_path} 不是一个文件")

    file_size_kb = path.stat().st_size / 1024

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        logger.warning("文件编码回退：%s 非 UTF-8，使用 latin-1 重新读取", file_path)
        try:
            content = path.read_text(encoding="latin-1")
        except Exception as e:
            logger.error("文件读取失败：%s", file_path, exc_info=True)
            return fail(f"文件 {file_path} 读取失败 - {e}")

    if file_size_kb > MAX_FILE_SIZE_KB:
        truncated = content[: MAX_FILE_SIZE_KB * 1024]
        logger.info("文件已读取（截断）：%s（%.0fKB，截取前 %dKB）", file_path, file_size_kb, MAX_FILE_SIZE_KB)
        return ok(
            f"文件 {file_path} 较大（{file_size_kb:.0f}KB），已截取前 {MAX_FILE_SIZE_KB}KB 内容",
            payload=truncated,
        )

    logger.info("文件已读取：%s（%.1fKB）", file_path, file_size_kb)
    return ok(f"已读取文件 {file_path}", payload=content)