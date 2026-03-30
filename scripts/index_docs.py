"""批量文档索引脚本。

扫描 docs_space_dir 下的 .md 文件，做 embedding 后 upsert 到 Chroma。

Usage:
    python scripts/index_docs.py                              # 索引所有文档
    python scripts/index_docs.py --file proj/mod/Api.md       # 索引单个文件
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 将项目根目录加入 sys.path，确保能找到 src 模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_chroma import Chroma
from langchain_core.documents import Document

from src.config import settings
from src.rag.chunker import chunk_markdown_doc, chunks_to_documents
from src.rag.embeddings import get_embeddings


def collect_md_files(docs_dir: Path) -> list[Path]:
    """递归收集目录下所有 .md 文件。"""
    return sorted(docs_dir.rglob("*.md"))


def collect_single_file(relative_path: str, docs_dir: Path) -> Path:
    """获取单个文件的绝对路径，不存在则抛出异常。"""
    file_path = docs_dir / relative_path
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    return file_path


def build_metadata(file_path: Path, docs_dir: Path) -> dict[str, str]:
    """从文件路径提取元数据。"""
    relative = file_path.relative_to(docs_dir)
    parts = relative.parts

    return {
        "source": str(relative),
        "project": parts[0] if len(parts) > 0 else "unknown",
        "module": parts[1] if len(parts) > 1 else "unknown",
        "api_name": file_path.stem,
    }


def index_files(files: list[Path], docs_dir: Path) -> None:
    """将文件列表索引到 Chroma。"""
    embeddings = get_embeddings()

    vectorstore = Chroma(
        collection_name=settings.chroma.collection_name,
        persist_directory=settings.chroma.persist_dir,
        embedding_function=embeddings,
    )

    docs: list[Document] = []
    ids: list[str] = []

    for file_path in files:
        content = file_path.read_text(encoding="utf-8")
        metadata = build_metadata(file_path, docs_dir)
        project = metadata["project"]
        service = metadata["module"]

        # 分块索引
        chunks = chunk_markdown_doc(content, str(file_path.relative_to(docs_dir)), project, service)
        chunk_docs = chunks_to_documents(chunks)

        for chunk_doc in chunk_docs:
            doc_id = f"{chunk_doc.metadata['source']}#{chunk_doc.metadata['section']}"
            docs.append(chunk_doc)
            ids.append(doc_id)

    if docs:
        vectorstore.add_documents(documents=docs, ids=ids)
        print(f"索引完成: {len(docs)} 个文档已入库 {settings.chroma.collection_name}")
    else:
        print("未找到需要索引的文档")


def main() -> None:
    parser = argparse.ArgumentParser(description="批量索引 API 文档到 Chroma 向量库")
    parser.add_argument(
        "--file",
        type=str,
        help="索引单个文件（相对于 docs_space_dir 的路径）",
    )
    args = parser.parse_args()

    docs_dir = Path(settings.docs_space_dir)
    if not docs_dir.exists():
        print(f"文档目录不存在: {docs_dir}", file=sys.stderr)
        sys.exit(1)

    if args.file:
        file_path = collect_single_file(args.file, docs_dir)
        files = [file_path]
    else:
        files = collect_md_files(docs_dir)

    if not files:
        print("未找到 .md 文件")
        sys.exit(0)

    print(f"准备索引 {len(files)} 个文件...")
    index_files(files, docs_dir)


if __name__ == "__main__":
    main()
