"""API 发现模块。

扫描 Go 源码文件，使用正则匹配注册调用，提取 API 函数名。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from src.generator.config import DiscoveryPattern, ModuleMapping
from src.logs import get_logger

logger = get_logger(__name__)


@dataclass
class DiscoveredAPI:
    """发现的 API 函数。"""
    function_name: str
    source_file: str  # 相对于 source_root
    source_line: int


def discover_apis(source_root: Path, patterns: list[DiscoveryPattern]) -> list[DiscoveredAPI]:
    """扫描源码目录，匹配注册模式，返回发现的 API 列表。"""
    compiled = [re.compile(p.regex) for p in patterns]
    apis: list[DiscoveredAPI] = []

    if not source_root.exists():
        logger.warning("源码目录不存在: %s", source_root)
        return apis

    go_files = sorted(f for f in source_root.rglob("*.go") if not f.name.endswith("_test.go"))

    for go_file in go_files:
        rel_path = str(go_file.relative_to(source_root))
        try:
            content = go_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = go_file.read_text(encoding="latin-1")
            except Exception:
                logger.warning("无法读取文件: %s", go_file)
                continue

        for line_num, line in enumerate(content.splitlines(), start=1):
            for regex in compiled:
                for match in regex.finditer(line):
                    func_name = match.group(1)
                    if not func_name:
                        logger.warning("正则匹配到注册调用但捕获组为空: %s:%d", rel_path, line_num)
                        continue
                    apis.append(DiscoveredAPI(function_name=func_name, source_file=rel_path, source_line=line_num))

    logger.info("发现 %d 个 API 函数", len(apis))
    return apis


def resolve_module(source_file: str, mappings: list[ModuleMapping]) -> str:
    """根据模块映射规则确定源码文件对应的模块名。"""
    for mapping in mappings:
        if fnmatch(source_file, mapping.match):
            return mapping.module
    parts = Path(source_file).parts
    if len(parts) <= 1:
        return "_root"
    return parts[0]
