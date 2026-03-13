"""代码搜索工具模块。

提供在 Go 源码中按函数名精确定位函数定义的能力。
"""

import re
from pathlib import Path

from langchain.tools import tool

from src.config import settings
from src.logs import get_logger
from src.tools.utils import fail, ok

logger = get_logger(__name__)


@tool
def find_function(function_name: str, directory: str = ".") -> str:
    """在指定目录下查找 Go 函数的定义位置。
    仅当你需要定位一个具体的函数或方法的定义所在文件时使用此工具，
    不要用于通用代码搜索。
    传入函数名（不含 func 关键字），工具会自动匹配普通函数和方法定义。

    Args:
        function_name: 要查找的函数名，如 "buyResourcePostPaid"
        directory: 搜索起始目录，默认为 "."

    Returns:
        JSON envelope，payload 包含 file（文件路径）、line（行号）、content（该行内容）。
    """
    dir_path = Path(settings.agent_work_dir) / directory

    if not dir_path.exists():
        logger.error("搜索失败：目录 %s 不存在", directory)
        return fail(f"目录 {directory} 不存在，请确认路径是否正确")

    if not dir_path.is_dir():
        logger.error("搜索失败：%s 不是目录", directory)
        return fail(f"{directory} 不是一个目录")

    escaped_name = re.escape(function_name)
    pattern = re.compile(rf"^func\s+(\(.*?\)\s+)?{escaped_name}\s*\(")

    go_files = sorted(
        f for f in dir_path.rglob("*.go") if not f.name.endswith("_test.go")
    )

    for go_file in go_files:
        try:
            content = go_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = go_file.read_text(encoding="latin-1")
            except Exception:
                continue

        for line_num, line in enumerate(content.splitlines(), 1):
            if pattern.match(line):
                rel_path = str(go_file.relative_to(Path(settings.agent_work_dir)))
                logger.info("找到函数 %s 定义：%s:%d", function_name, rel_path, line_num)
                return ok(
                    "找到函数定义",
                    payload={"file": rel_path, "line": line_num, "content": line.strip()},
                )

    logger.info("未找到函数 %s 的定义", function_name)
    return fail(f"未找到函数 {function_name} 的定义")
