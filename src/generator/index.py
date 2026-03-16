"""INDEX.md 索引管理。

使用正则行级解析器读写 Markdown 表格格式的索引文件。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from src.logs import get_logger

logger = get_logger(__name__)


@dataclass
class IndexEntry:
    api_name: str
    source_location: str
    doc_location: str
    generated_at: str


@dataclass
class BlacklistEntry:
    api_name: str
    source_location: str
    reason: str


def _escape_pipe(s: str) -> str:
    return s.replace("|", r"\|")


def _unescape_pipe(s: str) -> str:
    return s.replace(r"\|", "|")


def _split_table_cells(row_inner: str) -> list[str]:
    """Split table row content on unescaped pipe characters."""
    return [_unescape_pipe(c.strip()) for c in re.split(r"(?<!\\)\|", row_inner)]


_TABLE_ROW_RE = re.compile(r"^\|(.+)\|$")
_SEPARATOR_RE = re.compile(r"^\|[\s\-:|]+\|$")
_HEADING_RE = re.compile(r"^##\s+(.+)$")

_BLACKLIST_HEADING = "黑名单"


class Index:
    def __init__(self, index_path: Path, project_name: str = ""):
        self.index_path = index_path
        self.project_name = project_name
        self.entries: dict[str, list[IndexEntry]] = {}
        self.blacklist_entries: list[BlacklistEntry] = []

    def load(self) -> None:
        if not self.index_path.exists():
            return
        try:
            content = self.index_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("INDEX.md 读取失败: %s", e)
            return
        self._parse(content)

    def _parse(self, content: str) -> None:
        current_section: str | None = None
        in_table = False
        found_heading = False

        for line in content.splitlines():
            line = line.strip()
            heading_match = _HEADING_RE.match(line)
            if heading_match:
                current_section = heading_match.group(1).strip()
                in_table = False
                found_heading = True
                continue
            if _SEPARATOR_RE.match(line):
                in_table = True
                continue
            if not in_table:
                continue
            row_match = _TABLE_ROW_RE.match(line)
            if not row_match:
                in_table = False
                continue

            cells = _split_table_cells(row_match.group(1))

            if current_section == _BLACKLIST_HEADING:
                if len(cells) >= 3:
                    self.blacklist_entries.append(BlacklistEntry(api_name=cells[0], source_location=cells[1], reason=cells[2]))
            elif current_section:
                if len(cells) >= 4:
                    if current_section not in self.entries:
                        self.entries[current_section] = []
                    self.entries[current_section].append(IndexEntry(api_name=cells[0], source_location=cells[1], doc_location=cells[2], generated_at=cells[3]))

        if not found_heading and content.strip():
            logger.warning("INDEX.md 格式异常，未找到任何模块标题，视为空索引")

    def has_entry(self, api_name: str, source_location: str) -> bool:
        for entries in self.entries.values():
            for entry in entries:
                if entry.api_name == api_name and entry.source_location == source_location:
                    return True
        return False

    def add_or_replace_entry(self, module: str, entry: IndexEntry) -> None:
        if module not in self.entries:
            self.entries[module] = []
        entries = self.entries[module]
        for i, existing in enumerate(entries):
            if existing.api_name == entry.api_name and existing.source_location == entry.source_location:
                entries[i] = entry
                return
        entries.append(entry)

    def sync_blacklist(self, bl_entries: list[BlacklistEntry]) -> None:
        self.blacklist_entries = list(bl_entries)

    def save(self) -> None:
        lines: list[str] = []
        title = self.project_name or "项目"
        lines.append(f"# {title} 项目 API 文档索引\n")

        for module in sorted(self.entries.keys()):
            entries = self.entries[module]
            if not entries:
                continue
            lines.append(f"## {module}\n")
            lines.append("| API | 源码位置 | 文档位置 | 生成时间 |")
            lines.append("|-----|---------|---------|---------|")
            for e in entries:
                lines.append(f"| {_escape_pipe(e.api_name)} | {_escape_pipe(e.source_location)} | {_escape_pipe(e.doc_location)} | {_escape_pipe(e.generated_at)} |")
            lines.append("")

        if self.blacklist_entries:
            lines.append(f"## {_BLACKLIST_HEADING}\n")
            lines.append("| API | 源码位置 | 原因 |")
            lines.append("|-----|---------|------|")
            for bl in self.blacklist_entries:
                lines.append(f"| {_escape_pipe(bl.api_name)} | {_escape_pipe(bl.source_location)} | {_escape_pipe(bl.reason)} |")
            lines.append("")

        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text("\n".join(lines), encoding="utf-8")
