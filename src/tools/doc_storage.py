import re
from pathlib import Path

from langchain_core.tools import tool

from .utils import fail, ok

DOCS_BASE_DIR = "docs"

_MODULE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def _validate_module_name(module_name: str) -> str | None:
    """校验模块名称，返回错误信息或 None。"""
    if not module_name:
        return "模块名称不能为空"
    if not _MODULE_NAME_PATTERN.match(module_name):
        return f"模块名称 '{module_name}' 不合法，仅允许小写字母、数字和下划线，且必须以字母开头"
    return None


def _get_doc_path(module_name: str, api_name: str) -> Path:
    """构建文档文件路径：docs/{module_name}/{api_name}.md"""
    return Path(DOCS_BASE_DIR) / module_name / f"{api_name}.md"


@tool
def save_document(module_name: str, api_name: str, content: str) -> str:
    """将生成的接口文档保存为 Markdown 文件。
    文件按模块分目录存储，文件名为接口名称。

    Args:
        module_name: 模块名称，如 "user"、"order"，仅允许小写字母、数字和下划线
        api_name: 接口名称，如 "CreateUser"，直接用作文件名
        content: 要保存的 Markdown 文档内容

    Returns:
        JSON envelope，payload 为保存的文件路径。
    """
    if not api_name:
        return fail("接口名称不能为空")
    if not content:
        return fail("文档内容不能为空")

    error = _validate_module_name(module_name)
    if error:
        return fail(error)

    doc_path = _get_doc_path(module_name, api_name)

    try:
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_text(content, encoding="utf-8")
    except Exception as e:
        return fail(f"文档保存失败 - {e}")

    return ok(f"文档已保存到 {doc_path}", payload=str(doc_path))


@tool
def read_document(module_name: str, api_name: str) -> str:
    """读取已有的接口文档文件内容。
    用于查看或对比已有的文档。

    Args:
        module_name: 模块名称，如 "user"
        api_name: 接口名称，如 "CreateUser"

    Returns:
        JSON envelope，payload 为文档的 Markdown 内容。
    """
    if not api_name:
        return fail("接口名称不能为空")

    error = _validate_module_name(module_name)
    if error:
        return fail(error)

    doc_path = _get_doc_path(module_name, api_name)

    if not doc_path.exists():
        return fail("该接口的文档尚未生成")

    try:
        content = doc_path.read_text(encoding="utf-8")
    except Exception as e:
        return fail(f"文档读取失败 - {e}")

    return ok(f"已读取 {module_name}/{api_name} 的文档", payload=content)


@tool
def list_documents(module_name: str | None = None) -> str:
    """列出已有的接口文档文件。
    如果指定模块名，只列出该模块的文档；否则列出所有文档。

    Args:
        module_name: 可选的模块名称。如果不指定，列出所有模块的文档。

    Returns:
        JSON envelope，payload 为文档文件列表（按模块分组）。
    """
    base = Path(DOCS_BASE_DIR)

    if not base.exists():
        if module_name:
            return ok(f"模块 {module_name} 下没有已生成的文档")
        return ok("当前没有已生成的文档")

    if module_name:
        error = _validate_module_name(module_name)
        if error:
            return fail(error)

        module_dir = base / module_name
        if not module_dir.exists() or not module_dir.is_dir():
            return ok(f"模块 {module_name} 下没有已生成的文档")

        md_files = sorted(f.name for f in module_dir.iterdir() if f.suffix == ".md")
        if not md_files:
            return ok(f"模块 {module_name} 下没有已生成的文档")

        listing = f"{module_name} 模块：\n" + "\n".join(f"  - {name}" for name in md_files)
        return ok(f"模块 {module_name} 下有 {len(md_files)} 个文档", payload=listing)

    # List all modules
    modules: dict[str, list[str]] = {}
    for module_dir in sorted(base.iterdir()):
        if not module_dir.is_dir():
            continue
        md_files = sorted(f.name for f in module_dir.iterdir() if f.suffix == ".md")
        if md_files:
            modules[module_dir.name] = md_files

    if not modules:
        return ok("当前没有已生成的文档")

    lines = []
    total = 0
    for mod_name, files in modules.items():
        lines.append(f"{mod_name} 模块：")
        for name in files:
            lines.append(f"  - {name}")
        total += len(files)

    return ok(f"共有 {total} 个文档，分布在 {len(modules)} 个模块", payload="\n".join(lines))
