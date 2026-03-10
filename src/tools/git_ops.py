import subprocess
from pathlib import Path

from langchain.tools import tool

from src.tools.utils import fail, ok
from src.logs import get_logger

logger = get_logger(__name__)

LAST_COMMIT_FILE = ".last_commit"
GIT_TIMEOUT_SECONDS = 30


@tool
def git_diff(repo_path: str) -> str:
    """获取 Git 仓库自上次文档生成以来的代码变更文件列表。
    使用 git diff 对比上次记录的 commit hash 与当前 HEAD 之间的变更。

    Args:
        repo_path: Git 仓库的根目录路径

    Returns:
        JSON envelope，payload 为变更文件列表。
    """
    repo = Path(repo_path)

    if not (repo / ".git").exists():
        logger.error("Git diff 失败：%s 不是 Git 仓库", repo_path)
        return fail(f"{repo_path} 不是 Git 仓库")

    last_commit_path = repo / LAST_COMMIT_FILE
    if not last_commit_path.exists():
        logger.error("Git diff 失败：%s 不存在", last_commit_path)
        return fail("这是首次执行增量检测，没有历史 commit 记录作为基准")

    last_commit = last_commit_path.read_text(encoding="utf-8").strip()
    if not last_commit:
        logger.error("Git diff 失败：%s 内容为空", last_commit_path)
        return fail("这是首次执行增量检测，没有历史 commit 记录作为基准")

    try:
        result = subprocess.run(
            ["git", "diff", "--name-status", f"{last_commit}..HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        logger.error("Git diff 超时：%s（%d秒）", repo_path, GIT_TIMEOUT_SECONDS)
        return fail(f"Git 操作超时（{GIT_TIMEOUT_SECONDS}秒）")
    except FileNotFoundError:
        logger.error("Git diff 失败：未找到 git 命令")
        return fail("未找到 git 命令，请确认已安装 Git")

    if result.returncode != 0:
        logger.error("Git diff 失败：returncode=%d, stderr=%s", result.returncode, result.stderr.strip())
        return fail(f"Git 操作失败 - {result.stderr.strip()}")

    output = result.stdout.strip()
    if not output:
        return ok("没有检测到代码变更")

    status_map = {"A": "新增", "M": "修改", "D": "删除"}

    lines = []
    for line in output.split("\n"):
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) == 2:
            status, filepath = parts
            status_label = status_map.get(status, status)
            lines.append(f"  [{status_label}] {filepath}")

    change_list = "\n".join(lines)
    logger.info("Git diff 完成：%s 检测到 %d 个文件变更", repo_path, len(lines))
    return ok(f"检测到 {len(lines)} 个文件变更", payload=change_list)
