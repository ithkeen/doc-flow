"""项目配置文件解析。

从 .docflow.yaml 加载并校验项目配置。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator


class DiscoveryPattern(BaseModel):
    """API 注册函数的正则模式。"""
    regex: str

    @field_validator("regex")
    @classmethod
    def validate_regex(cls, v: str) -> str:
        try:
            compiled = re.compile(v)
        except re.error as e:
            raise ValueError(f"无效的正则表达式 '{v}': {e}")
        if compiled.groups < 1:
            raise ValueError(f"正则表达式 '{v}' 必须包含至少一个捕获组")
        return v


class DiscoveryConfig(BaseModel):
    """API 发现配置。"""
    source_root: str
    patterns: list[DiscoveryPattern]

    @field_validator("patterns")
    @classmethod
    def validate_patterns_not_empty(cls, v: list[DiscoveryPattern]) -> list[DiscoveryPattern]:
        if not v:
            raise ValueError("patterns 至少需要包含一项")
        return v


class ModuleMapping(BaseModel):
    """模块映射规则。"""
    match: str
    module: str

    @field_validator("module")
    @classmethod
    def validate_module_name(cls, v: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]*$", v):
            raise ValueError(f"模块名 '{v}' 不合法，仅允许小写字母、数字和下划线，且必须以字母开头")
        return v


class BlacklistFunction(BaseModel):
    """按函数名跳过。"""
    name: str
    reason: str


class BlacklistFile(BaseModel):
    """按文件路径跳过。"""
    path: str
    reason: str


class BlacklistConfig(BaseModel):
    """黑名单配置。"""
    functions: list[BlacklistFunction] = []
    files: list[BlacklistFile] = []


class ProjectConfig(BaseModel):
    """项目配置（对应 .docflow.yaml）。"""
    discovery: DiscoveryConfig
    modules: list[ModuleMapping] = []
    blacklist: BlacklistConfig = BlacklistConfig()


def load_project_config(config_path: Path) -> ProjectConfig:
    """从 YAML 文件加载项目配置。"""
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    raw = config_path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ValueError(f"YAML 解析失败: {e}")
    if not isinstance(data, dict):
        raise ValueError(f"配置文件格式错误: 期望 dict，实际为 {type(data).__name__}")
    return ProjectConfig(**data)
