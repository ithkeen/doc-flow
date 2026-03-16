"""批量文档生成器 CLI 入口。

Usage:
    uv run python -m src.generator --project access
    uv run python -m src.generator --all
    uv run python -m src.generator --project access --api CreateOrder
    uv run python -m src.generator --project access --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from src.generator.runner import print_report, run_all_projects, run_project


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        prog="doc-flow generator",
        description="批量生成 Go API 接口文档",
    )

    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--project", help="指定项目名")
    target.add_argument("--all", action="store_true", help="遍历所有项目")

    parser.add_argument("--api", help="指定重新生成的单个 API 函数名")
    parser.add_argument("--api-file", help="精确指定源码文件路径（相对于 source_root）")
    parser.add_argument("--force", action="store_true", help="忽略索引，强制重新生成")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际生成")

    args = parser.parse_args(argv)

    if args.api and not args.project:
        parser.error("--api 必须与 --project 一起使用")
    if args.api_file and not args.api:
        parser.error("--api-file 必须与 --api 一起使用")
    if args.force and args.api:
        parser.error("--force 不能与 --api 同时使用")

    return args


async def main(args: argparse.Namespace) -> None:
    """主入口。"""
    if args.all:
        reports = await run_all_projects(force=args.force, dry_run=args.dry_run)
        for report in reports:
            print_report(report)
    else:
        report = await run_project(
            args.project,
            force=args.force,
            dry_run=args.dry_run,
            single_api=args.api,
            api_file=args.api_file,
        )
        print_report(report)


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args))
