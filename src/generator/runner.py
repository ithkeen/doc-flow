"""批量生成主编排模块。

加载配置 → 发现 API → 过滤 → 模块分配 → 串行生成 → 更新索引 → 输出报告。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src.config import settings
from src.generator.config import (
    BlacklistConfig,
    ProjectConfig,
    load_project_config,
)
from src.generator.discovery import DiscoveredAPI, discover_apis, resolve_module
from src.generator.graph import GenState, build_generator_graph
from src.generator.index import BlacklistEntry, Index, IndexEntry
from src.logs import get_logger

logger = get_logger(__name__)


@dataclass
class GenerationResult:
    """单个 API 的生成结果。"""
    api_name: str
    module: str
    success: bool
    error: str | None = None
    duration_seconds: float = 0.0


@dataclass
class ProjectReport:
    """项目级生成报告。"""
    project: str
    total: int = 0
    generated: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped_existing: int = 0
    skipped_blacklist: int = 0
    results: list[GenerationResult] = field(default_factory=list)


def _print(msg: str) -> None:
    """输出带 [doc-flow] 前缀的消息。"""
    print(f"[doc-flow] {msg}")


def filter_apis(
    apis: list[DiscoveredAPI],
    blacklist: BlacklistConfig,
    index: Index,
    *,
    force: bool = False,
) -> list[DiscoveredAPI]:
    """过滤 API 列表：去掉黑名单和已有索引条目。"""
    bl_func_names = {f.name for f in blacklist.functions}
    bl_file_paths = {f.path for f in blacklist.files}

    filtered = []
    for api in apis:
        if api.function_name in bl_func_names:
            continue
        if api.source_file in bl_file_paths:
            continue
        if not force:
            source_loc = f"{api.source_file}:{api.source_line}"
            if index.has_entry(api.function_name, source_loc):
                continue
        filtered.append(api)

    return filtered


def build_blacklist_entries(
    blacklist: BlacklistConfig,
    all_apis: list[DiscoveredAPI],
) -> list[BlacklistEntry]:
    """从配置和发现的 API 构建黑名单索引条目。"""
    entries: list[BlacklistEntry] = []
    bl_func_names = {f.name: f.reason for f in blacklist.functions}
    bl_file_paths = {f.path: f.reason for f in blacklist.files}

    for api in all_apis:
        if api.function_name in bl_func_names:
            entries.append(
                BlacklistEntry(
                    api_name=api.function_name,
                    source_location=f"{api.source_file}:{api.source_line}",
                    reason=bl_func_names[api.function_name],
                )
            )
        elif api.source_file in bl_file_paths:
            entries.append(
                BlacklistEntry(
                    api_name=api.function_name,
                    source_location=f"{api.source_file}:{api.source_line}",
                    reason=bl_file_paths[api.source_file],
                )
            )

    return entries


def _count_blacklisted(apis: list[DiscoveredAPI], blacklist: BlacklistConfig) -> int:
    """统计被黑名单过滤的 API 数量。"""
    bl_func_names = {f.name for f in blacklist.functions}
    bl_file_paths = {f.path for f in blacklist.files}
    count = 0
    for api in apis:
        if api.function_name in bl_func_names or api.source_file in bl_file_paths:
            count += 1
    return count


def _find_function_in_source(
    function_name: str,
    source_root: Path,
    api_file: str | None = None,
) -> list[DiscoveredAPI]:
    """在源码中查找函数定义（复用 find_function 的正则逻辑）。

    NOTE: 有意复制 src/tools/code_search.py 中 find_function 的正则逻辑，
    因为 find_function 是 @tool 装饰器包装的函数，返回 JSON 字符串，
    不适合在编排层直接调用。
    """
    escaped = re.escape(function_name)
    pattern = re.compile(rf"^func\s+(\(.*?\)\s+)?{escaped}\s*\(")

    results: list[DiscoveredAPI] = []

    if api_file:
        target = source_root / api_file
        if not target.exists():
            return results
        go_files = [target]
    else:
        go_files = sorted(
            f for f in source_root.rglob("*.go") if not f.name.endswith("_test.go")
        )

    for go_file in go_files:
        try:
            content = go_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = go_file.read_text(encoding="latin-1")
            except Exception:
                continue

        for line_num, line in enumerate(content.splitlines(), start=1):
            if pattern.match(line):
                rel_path = str(go_file.relative_to(source_root))
                results.append(
                    DiscoveredAPI(
                        function_name=function_name,
                        source_file=rel_path,
                        source_line=line_num,
                    )
                )

    return results


async def generate_single_api(
    graph,
    api: DiscoveredAPI,
    project: str,
    module: str,
    source_root_rel: str,
) -> GenerationResult:
    """调用生成图为单个 API 生成文档。"""
    source_file_full = f"{source_root_rel}/{api.source_file}" if source_root_rel != "." else api.source_file

    initial_state: GenState = {
        "messages": [],
        "project": project,
        "module": module,
        "function_name": api.function_name,
        "source_file": source_file_full,
        "source_line": api.source_line,
    }

    start_time = time.time()
    try:
        await graph.ainvoke(initial_state)
        duration = time.time() - start_time
        return GenerationResult(
            api_name=api.function_name, module=module, success=True, duration_seconds=duration,
        )
    except Exception as e:
        duration = time.time() - start_time
        logger.error("生成失败: %s.%s - %s", module, api.function_name, e, exc_info=True)
        return GenerationResult(
            api_name=api.function_name, module=module, success=False, error=str(e), duration_seconds=duration,
        )


async def run_project(
    project: str,
    *,
    force: bool = False,
    dry_run: bool = False,
    single_api: str | None = None,
    api_file: str | None = None,
) -> ProjectReport:
    """为单个项目执行批量文档生成。"""
    report = ProjectReport(project=project)

    docs_base = Path(settings.agent_work_dir) / settings.docs_output_dir
    config_path = docs_base / project / ".docflow.yaml"
    _print(f"加载项目配置: {project}")

    try:
        config = load_project_config(config_path)
    except Exception as e:
        _print(f"配置加载失败: {e}")
        raise

    source_root = Path(settings.agent_work_dir) / config.discovery.source_root

    index_path = docs_base / project / "INDEX.md"
    index = Index(index_path, project_name=project)
    index.load()

    if single_api:
        return await _run_single_api(project, config, source_root, index, index_path, single_api, api_file, report)

    all_apis = discover_apis(source_root, config.discovery.patterns)
    report.total = len(all_apis)
    _print(f"发现 {len(all_apis)} 个 API 函数")

    blacklist_count = _count_blacklisted(all_apis, config.blacklist)
    to_generate = filter_apis(all_apis, config.blacklist, index, force=force)

    skipped_existing = report.total - blacklist_count - len(to_generate)
    if not force:
        report.skipped_existing = max(0, skipped_existing)
    report.skipped_blacklist = blacklist_count
    report.generated = len(to_generate)

    _print(f"跳过 {blacklist_count} 个黑名单函数")
    if not force:
        _print(f"跳过 {report.skipped_existing} 个已有文档")
    _print(f"待生成: {len(to_generate)} 个 API")

    if dry_run:
        _print("预览模式，不实际生成")
        for api in to_generate:
            module = resolve_module(api.source_file, config.modules)
            _print(f"  - {module}.{api.function_name} ({api.source_file}:{api.source_line})")
        return report

    graph = build_generator_graph()
    for i, api in enumerate(to_generate, 1):
        module = resolve_module(api.source_file, config.modules)
        _print(f"[{i}/{len(to_generate)}] 生成中: {module}.{api.function_name} ...")

        result = await generate_single_api(graph, api, project, module, config.discovery.source_root)
        report.results.append(result)

        if result.success:
            report.succeeded += 1
            _print(f"[{i}/{len(to_generate)}] ✓ {module}.{api.function_name} ({result.duration_seconds:.0f}s)")
            source_loc = f"{api.source_file}:{api.source_line}"
            doc_loc = f"{module}/{api.function_name}.md"
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            index.add_or_replace_entry(module, IndexEntry(api.function_name, source_loc, doc_loc, now))
            index.save()
        else:
            report.failed += 1
            _print(f"[{i}/{len(to_generate)}] ✗ {module}.{api.function_name} (错误: {result.error})")

    bl_entries = build_blacklist_entries(config.blacklist, all_apis)
    index.sync_blacklist(bl_entries)
    index.save()
    _print(f"索引已更新: {index_path}")

    return report


async def _run_single_api(
    project: str,
    config: ProjectConfig,
    source_root: Path,
    index: Index,
    index_path: Path,
    single_api: str,
    api_file: str | None,
    report: ProjectReport,
) -> ProjectReport:
    """处理 --api 单个 API 重新生成。"""
    matches = _find_function_in_source(single_api, source_root, api_file)

    if not matches:
        _print(f"未找到函数: {single_api}")
        raise SystemExit(1)

    if len(matches) > 1 and api_file is None:
        _print(f"函数 {single_api} 有多个定义:")
        for m in matches:
            _print(f"  - {m.source_file}:{m.source_line}")
        _print("请使用 --api-file 指定具体文件路径")
        raise SystemExit(1)

    api = matches[0]
    report.total = 1
    report.generated = 1

    bl_func_names = {f.name for f in config.blacklist.functions}
    if api.function_name in bl_func_names:
        reason = next(f.reason for f in config.blacklist.functions if f.name == api.function_name)
        _print(f"警告: 该函数在黑名单中，原因: {reason}")

    module = resolve_module(api.source_file, config.modules)
    _print(f"[1/1] 生成中: {module}.{api.function_name} ...")

    graph = build_generator_graph()
    result = await generate_single_api(graph, api, project, module, config.discovery.source_root)
    report.results.append(result)

    if result.success:
        report.succeeded += 1
        _print(f"[1/1] ✓ {module}.{api.function_name} ({result.duration_seconds:.0f}s)")
        source_loc = f"{api.source_file}:{api.source_line}"
        doc_loc = f"{module}/{api.function_name}.md"
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        index.add_or_replace_entry(module, IndexEntry(api.function_name, source_loc, doc_loc, now))
        index.save()
        _print(f"索引已更新: {index_path}")
    else:
        report.failed += 1
        _print(f"[1/1] ✗ {module}.{api.function_name} (错误: {result.error})")

    return report


def print_report(report: ProjectReport) -> None:
    """输出生成报告。"""
    print(f"\n=== 生成报告: {report.project} ===")
    print(
        f"总计: {report.total} | 成功: {report.succeeded} | 失败: {report.failed} "
        f"| 跳过(已有): {report.skipped_existing} | 跳过(黑名单): {report.skipped_blacklist}"
    )
    failed = [r for r in report.results if not r.success]
    if failed:
        print("失败列表:")
        for r in failed:
            print(f"  - {r.module}.{r.api_name}: {r.error}")


async def run_all_projects(*, force: bool = False, dry_run: bool = False) -> list[ProjectReport]:
    """遍历所有项目执行批量生成。"""
    docs_base = Path(settings.agent_work_dir) / settings.docs_output_dir
    reports: list[ProjectReport] = []

    if not docs_base.exists():
        _print(f"文档目录不存在: {docs_base}")
        return reports

    project_dirs = sorted(d for d in docs_base.iterdir() if d.is_dir() and (d / ".docflow.yaml").exists())

    if not project_dirs:
        _print("未找到包含 .docflow.yaml 的项目")
        return reports

    _print(f"发现 {len(project_dirs)} 个项目")

    for project_dir in project_dirs:
        project = project_dir.name
        try:
            report = await run_project(project, force=force, dry_run=dry_run)
            reports.append(report)
        except SystemExit:
            raise
        except Exception as e:
            _print(f"项目 {project} 处理失败: {e}")
            reports.append(ProjectReport(project=project))

    return reports
