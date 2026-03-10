from pathlib import Path

from langchain.tools import tool

from src.config import settings
from src.logs import get_logger
from src.tools.utils import fail, ok

logger = get_logger(__name__)

MAX_FILE_SIZE_KB = 100


@tool
def read_file(file_path: str) -> str:
    """读取指定文件的完整内容。
    用于获取 Go 源代码文件的内容以分析接口定义，
    也可用于读取其他包中的结构体定义文件。

    Args:
        file_path: 要读取的文件路径，如 "./handler/user/create.go"
                   或 "./model/user.go"

    Returns:
        JSON envelope，payload 为文件的完整文本内容。
    """
    path = Path(settings.agent_work_dir) / file_path

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
