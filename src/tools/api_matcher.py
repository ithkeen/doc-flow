"""API 名称匹配工具模块。

在 code_space_dir 下指定文件中，通过正则表达式的捕获组快速匹配 API 名称。
file_path 参数为相对于 code_space_dir 的路径，工具内部自动拼接为绝对路径。
"""

import re
from pathlib import Path

from langchain_core.tools import tool

from src.config import settings
from src.logs import get_logger
from src.tools.utils import fail, ok

logger = get_logger(__name__)


@tool
def match_api_name(file_path: str, pattern: str) -> str:
    """在 code_space_dir 下指定文件中，使用正则表达式匹配 API 名称。

    传入一个正则表达式（必须包含至少一个捕获组），工具会逐行扫描文件，
    返回第一个匹配的捕获组内容作为 API 名称。
    若正则包含多个捕获组，仅使用第一个捕获组（group(1)）。

    Args:
        file_path: 相对于 code_space_dir 的文件路径，如 "ubill-access-api/router.go"
        pattern: 正则表达式字符串，必须包含至少一个捕获组，第一个捕获组即为 API 名称

    Returns:
        JSON Envelope 格式的响应字符串：
        - 成功: {"success": true, "message": "...", "payload": {...}, "error": null}
        - 失败: {"success": false, "message": "...", "payload": null, "error": "..."}
    """
    try:
        return _match(file_path, pattern)
    except Exception as exc:
        logger.error("匹配过程发生意外错误: %s", exc, exc_info=True)
        return fail(f"匹配过程发生意外错误: {exc}")


def _match(file_path: str, pattern: str) -> str:
    """Internal implementation, wrapped by the tool function's catch-all."""

    # 1. Validate file_path
    if not file_path or not file_path.strip():
        return fail("文件路径不能为空")

    # 2. Validate pattern
    if not pattern or not pattern.strip():
        return fail("匹配模式不能为空")

    # 3. Compile regex
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        logger.error("无效的正则表达式: %s — %s", pattern, exc)
        return fail(f"无效的正则表达式: {exc}")

    # 4. Verify at least one capture group
    if compiled.groups < 1:
        logger.error("正则表达式缺少捕获组: %s", pattern)
        return fail("正则表达式必须包含至少一个捕获组")

    # 5. Build absolute path
    target = Path(settings.code_space_dir) / file_path

    # 6. Validate file exists and is a file
    if not target.exists():
        logger.error("文件不存在: %s", file_path)
        return fail(f"文件不存在: {file_path}")

    if not target.is_file():
        logger.error("%s 是目录，不是文件", file_path)
        return fail(f"{file_path} 是目录，不是文件")

    # 7. Read file content (UTF-8, fallback Latin-1)
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        logger.warning("文件编码回退: %s 非 UTF-8，使用 latin-1 重新读取", file_path)
        try:
            content = target.read_text(encoding="latin-1")
        except Exception as exc:
            logger.error("文件读取失败: %s — %s", file_path, exc)
            return fail(f"文件读取失败: {exc}")

    # 8. Line-by-line search — return first match
    for line_num, line in enumerate(content.splitlines(), 1):
        m = compiled.search(line)
        if m:
            api_name = m.group(1)
            logger.info("匹配到 API: %s（文件: %s, 第 %d 行）", api_name, file_path, line_num)
            return ok(
                message=f"匹配到 API: {api_name}（文件: {file_path}, 第 {line_num} 行）",
                payload={
                    "api_name": api_name,
                    "file": file_path,
                    "line": line_num,
                    "content": line.strip(),
                },
            )

    # 9. No match
    logger.info("文件 %s 中未匹配到符合模式的 API", file_path)
    return fail("文件中未匹配到符合模式的 API")
