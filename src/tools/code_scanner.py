from pathlib import Path

from langchain.tools import tool

from utils import fail, ok


@tool
def scan_directory(directory_path: str) -> str:
    """扫描指定目录下的所有 Go 源文件，返回文件列表。
    用于发现目录中有哪些 Go 代码文件，以便后续分析接口定义。

    Args:
        directory_path: 要扫描的目录路径，如 "./handler/user/"

    Returns:
        JSON envelope，payload 为该目录下所有 .go 文件的路径列表
        （排除 _test.go 测试文件），每个文件一行。
    """
    dir_path = Path(directory_path)

    if not dir_path.exists():
        return fail(f"目录 {directory_path} 不存在，请确认路径是否正确")

    if not dir_path.is_dir():
        return fail(f"{directory_path} 不是一个目录")

    go_files = sorted(
        f for f in dir_path.rglob("*.go") if not f.name.endswith("_test.go")
    )

    if not go_files:
        return ok("该目录下未发现 Go 源文件（已排除 _test.go 测试文件）")

    file_list = "\n".join(f"{i}. {f}" for i, f in enumerate(go_files, 1))
    return ok(f"找到 {len(go_files)} 个 Go 源文件", payload=file_list)
