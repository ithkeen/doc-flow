"""代码搜索工具模块。

提供在 code_space_dir 下的 Go 源码中按名称精确定位函数定义和结构体定义的能力。
directory 参数为相对于 code_space_dir 的路径，工具内部自动拼接为绝对路径。
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
    """在 code_space_dir 下指定目录中查找 Go 函数的定义位置。

    仅当你需要定位一个具体的函数或方法的定义所在文件时使用此工具，
    不要用于通用代码搜索。
    传入函数名（不含 func 关键字），工具会自动匹配普通函数和方法定义。

    Args:
        function_name: 要查找的函数名，如 "buyResourcePostPaid"
        directory: 相对于 code_space_dir 的搜索起始目录，一般传入项目名称，如 "ubill-access-api"，默认为 "."

    Returns:
        JSON Envelope 格式的响应字符串：
        - 成功: {"success": true, "message": "...", "payload": [匹配列表], "error": null}
        - 失败: {"success": false, "message": "...", "payload": null, "error": "..."}
    """
    if not function_name or not function_name.strip():
        return fail("函数名不能为空")

    dir_path = Path(settings.code_space_dir) / directory

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

    matches = []

    for go_file in go_files:
        try:
            content = go_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = go_file.read_text(encoding="latin-1")
            except Exception as e:
                logger.warning("文件 %s 读取失败，已跳过：%s", go_file, e)
                continue

        for line_num, line in enumerate(content.splitlines(), 1):
            if pattern.match(line):
                rel_path = str(go_file.relative_to(Path(settings.code_space_dir)))
                logger.info("找到函数 %s 定义：%s:%d", function_name, rel_path, line_num)
                matches.append({"file": rel_path, "line": line_num, "content": line.strip()})

    if not matches:
        logger.info("未找到函数 %s 的定义", function_name)
        return fail(f"未找到函数 {function_name} 的定义")

    logger.info("找到函数 %s 共 %d 处定义", function_name, len(matches))
    return ok(f"找到 {len(matches)} 处函数定义", payload=matches)


@tool
def find_struct(struct_name: str, directory: str = ".") -> str:
    """在 code_space_dir 下指定目录中查找 Go 结构体的定义位置。

    用于定位请求体、响应体等结构体定义所在的文件和行号，
    不要用于通用代码搜索。
    传入结构体名称（不含 type 和 struct 关键字），工具会自动匹配 type ... struct 定义。

    Args:
        struct_name: 要查找的结构体名称，如 "BuyResourceReq"
        directory: 相对于 code_space_dir 的搜索起始目录，一般传入项目名称，如 "ubill-access-api"，默认为 "."

    Returns:
        JSON Envelope 格式的响应字符串：
        - 成功: {"success": true, "message": "...", "payload": [匹配列表], "error": null}
        - 失败: {"success": false, "message": "...", "payload": null, "error": "..."}
    """
    if not struct_name or not struct_name.strip():
        return fail("结构体名称不能为空")

    dir_path = Path(settings.code_space_dir) / directory

    if not dir_path.exists():
        logger.error("搜索失败：目录 %s 不存在", directory)
        return fail(f"目录 {directory} 不存在，请确认路径是否正确")

    if not dir_path.is_dir():
        logger.error("搜索失败：%s 不是目录", directory)
        return fail(f"{directory} 不是一个目录")

    escaped_name = re.escape(struct_name)
    pattern = re.compile(rf"^type\s+{escaped_name}\s+struct\s*\{{")

    go_files = sorted(
        f for f in dir_path.rglob("*.go") if not f.name.endswith("_test.go")
    )

    matches = []

    for go_file in go_files:
        try:
            content = go_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = go_file.read_text(encoding="latin-1")
            except Exception as e:
                logger.warning("文件 %s 读取失败，已跳过：%s", go_file, e)
                continue

        for line_num, line in enumerate(content.splitlines(), 1):
            if pattern.match(line):
                rel_path = str(go_file.relative_to(Path(settings.code_space_dir)))
                logger.info("找到结构体 %s 定义：%s:%d", struct_name, rel_path, line_num)
                matches.append({"file": rel_path, "line": line_num, "content": line.strip()})

    if not matches:
        logger.info("未找到结构体 %s 的定义", struct_name)
        return fail(f"未找到结构体 {struct_name} 的定义")

    logger.info("找到结构体 %s 共 %d 处定义", struct_name, len(matches))
    return ok(f"找到 {len(matches)} 处结构体定义", payload=matches)
