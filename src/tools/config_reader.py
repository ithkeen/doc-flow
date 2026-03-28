"""读取并校验 .doc_gen.yaml 项目配置。

本模块提供 Pydantic 数据模型和一个 LangChain Tool 函数，用于从
docs_space_dir 下加载文档生成配置文件（.doc_gen.yaml），校验其结构完整性后
返回结构化配置。config_path 参数为相对于 docs_space_dir 的路径。

工具与编程语言无关，适用于任何包含 .doc_gen.yaml 的项目。

Models:
    ModuleEntry       — 单个模块条目（名称 + 类型）
    ModulesConfig     — 路径到模块条目的映射
    SearchRulesConfig — 函数与结构体定义识别的正则模式
    DocgenConfig      — 顶层配置，组合以上两个子模型

Tool:
    load_docgen_config — 读取指定路径的 .doc_gen.yaml 并返回配置字典

Usage::

    from src.tools.config_reader import load_docgen_config

    # LLM Agent 通过 tool 调用
    result = load_docgen_config.invoke({
        "config_path": "ubill-access-api/.doc_gen.yaml"
    })

Example .doc_gen.yaml::

    modules:
      mapping:
        "ubill-access-api/ubill-order/logic":
          name: "order"
          type: "api"
        "ubill-access-api/ubill-cron/handler":
          name: "sync"
          type: "cron"
    search_rules:
      function_patterns:
        - 'http\\.HandlerFunc\\(\\s*([a-zA-Z_][a-zA-Z0-9_]*)\\s*\\)'
      struct_patterns:
        - 'type\\s+([a-zA-Z_][a-zA-Z0-9_]*)\\s+struct\\s*\\{'
"""

from __future__ import annotations

from pathlib import Path

import yaml
from langchain_core.tools import tool
from pydantic import BaseModel, ValidationError, field_validator

from src.config import settings
from src.logs import get_logger
from src.tools.utils import fail, ok


# ---------------------------------------------------------------------------
# Pydantic configuration models
# ---------------------------------------------------------------------------


class ModuleEntry(BaseModel):
    """单个模块条目。

    Attributes:
        name: 模块名称。
        type: 处理函数类型，如 "api"、"cron"、"mq"。默认为 "api"。
    """

    name: str
    type: str = "api"


class ModulesConfig(BaseModel):
    """模块映射配置。

    Attributes:
        mapping: 扫描路径到模块条目的映射字典，至少包含一项。
                 值可以是 ModuleEntry 对象或纯字符串（向后兼容，自动转为 type="api"）。
    """

    mapping: dict[str, ModuleEntry]

    @field_validator("mapping", mode="before")
    @classmethod
    def normalize_mapping_values(cls, v: dict) -> dict:
        """将纯字符串值归一化为 ModuleEntry 格式。"""
        if not isinstance(v, dict):
            return v
        normalized = {}
        for key, val in v.items():
            if isinstance(val, str):
                normalized[key] = {"name": val, "type": "api"}
            else:
                normalized[key] = val
        return normalized

    @field_validator("mapping")
    @classmethod
    def mapping_must_not_be_empty(cls, v: dict[str, ModuleEntry]) -> dict[str, ModuleEntry]:
        """确保 mapping 至少包含一项。"""
        if not v:
            raise ValueError("mapping 不能为空")
        return v


class SearchRulesConfig(BaseModel):
    """API 搜索规则配置。

    Attributes:
        function_patterns: 用于匹配 API 函数的正则表达式列表，至少包含一项。
        struct_patterns: 用于匹配结构体定义（如请求/响应体）的正则表达式列表，至少包含一项。
    """

    function_patterns: list[str]
    struct_patterns: list[str]

    @field_validator("function_patterns")
    @classmethod
    def function_patterns_must_not_be_empty(cls, v: list[str]) -> list[str]:
        """确保 function_patterns 至少包含一项。"""
        if not v:
            raise ValueError("function_patterns 不能为空")
        return v

    @field_validator("struct_patterns")
    @classmethod
    def struct_patterns_must_not_be_empty(cls, v: list[str]) -> list[str]:
        """确保 struct_patterns 至少包含一项。"""
        if not v:
            raise ValueError("struct_patterns 不能为空")
        return v


class DocgenConfig(BaseModel):
    """文档生成顶层配置。

    组合 modules、search_rules 两个子配置，
    对应 .doc_gen.yaml 的完整结构。

    Attributes:
        modules: 模块映射配置。
        search_rules: API 搜索规则。
    """

    modules: ModulesConfig
    search_rules: SearchRulesConfig


logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# LangChain Tool
# ---------------------------------------------------------------------------


@tool
def load_docgen_config(config_path: str) -> str:
    """读取 docs_space_dir 下指定路径的 .doc_gen.yaml 配置文件，返回完整的文档生成配置。

    根据相对路径拼接 {docs_space_dir}/{config_path}，
    解析 YAML 内容并通过 Pydantic 模型校验结构完整性。

    Args:
        config_path: 相对于 docs_space_dir 的配置文件路径，如 "ubill-access-api/.doc_gen.yaml"。

    Returns:
        JSON Envelope 格式的响应字符串：
        - 成功: {"success": true, "message": "...", "payload": {配置字典}, "error": null}
        - 失败: {"success": false, "message": "...", "payload": null, "error": "..."}
    """
    target_path = Path(settings.docs_space_dir) / config_path

    # 1. 检查文件是否存在
    if not target_path.is_file():
        logger.warning("配置文件不存在: %s", target_path)
        return fail(error=f"配置文件不存在: {target_path}，请检查路径是否正确")

    # 2. 读取并解析 YAML
    try:
        raw_text = target_path.read_text(encoding="utf-8")
        raw_config = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        logger.error("YAML 解析失败: %s — %s", target_path, exc)
        return fail(error=f"YAML 解析失败: {exc}")

    # 3. Pydantic 校验
    try:
        config = DocgenConfig(**raw_config)
    except ValidationError as exc:
        logger.error("配置校验失败: %s — %s", target_path, exc)
        return fail(error=f"配置校验失败: {exc}")

    logger.info("成功加载配置: %s", target_path)
    return ok(message=f"配置加载成功: {target_path}", payload=config.model_dump())