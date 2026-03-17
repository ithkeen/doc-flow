"""API 文档索引的 MySQL 读写工具。

提供 LangChain Tool 函数，用于管理 t_api_index 表中的 API 索引信息。

- save_api_index — 写入单条 API 索引记录（upsert 语义）
- query_api_index — 按 api / project 查询索引记录

Models:
    ToolResult — Tool 执行结果（success + message / data）

Usage::

    from src.tools.api_index import save_api_index, query_api_index

    # 写入
    result = save_api_index.invoke({
        "api": "HandleLogin",
        "project": "ubill-access-api",
        "source": "src/logic/auth/login.go",
        "doc": "ubill-access-api/HandleLogin.md",
    })

    # 查询
    result = query_api_index.invoke({
        "project": "ubill-access-api",
    })
"""

from __future__ import annotations

import mysql.connector
from langchain_core.tools import ToolException, tool
from pydantic import BaseModel

from src.config import settings
from src.config.settings import DatabaseSettings
from src.logs import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class ToolResult(BaseModel):
    """Tool 执行结果。"""

    success: bool
    message: str


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_UPSERT_SQL = """\
INSERT INTO t_api_index (api, project, source, doc)
VALUES (%s, %s, %s, %s) AS new
ON DUPLICATE KEY UPDATE source = new.source, doc = new.doc
"""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _get_db_config() -> DatabaseSettings:
    """获取数据库配置，支持懒加载。"""
    if settings.db is not None:
        return settings.db
    try:
        return DatabaseSettings()  # type: ignore[call-arg]
    except Exception as exc:
        raise ToolException("数据库未配置，请设置 DB_* 环境变量") from exc


# ---------------------------------------------------------------------------
# LangChain Tool
# ---------------------------------------------------------------------------


@tool
def save_api_index(api: str, project: str, source: str, doc: str) -> dict:
    """将 API 文档索引信息写入数据库。

    在文档生成完成后调用，记录 API 函数名、所属项目、源码路径和文档路径。
    如果该 API 在同一项目中已有记录，则更新路径信息。

    Args:
        api: API 函数名（如 "HandleLogin"）
        project: 项目名称（如 "ubill-access-api"）
        source: 源码路径，相对于 codespace 根目录
        doc: 文档路径，相对于 docspace 根目录

    Returns:
        包含 success 和 message 的结果字典

    Raises:
        ToolException: 参数校验失败、数据库未配置、连接或写入失败时抛出，
            错误信息会通过 handle_tool_error 传递给 LLM。
    """
    # 1. 输入校验并去除首尾空白
    if not api or not api.strip():
        raise ToolException("参数错误: api 不能为空")
    if not project or not project.strip():
        raise ToolException("参数错误: project 不能为空")
    api = api.strip()
    project = project.strip()

    # 2. 获取数据库配置
    db_cfg = _get_db_config()

    # 3. 连接
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(
            host=db_cfg.host,
            port=db_cfg.port,
            user=db_cfg.user,
            password=db_cfg.password,
            database=db_cfg.database,
        )
    except Exception as exc:
        logger.error("数据库连接失败: %s", exc)
        raise ToolException(f"数据库连接失败: {exc}") from exc

    # 4. 执行 upsert
    try:
        cursor = conn.cursor()
        cursor.execute(_UPSERT_SQL, (api, project, source, doc))
        conn.commit()

        # rowcount: 1=inserted, 2=updated, 0=matched but no change
        if cursor.rowcount == 1:
            action = "新增"
        elif cursor.rowcount == 2:
            action = "更新"
        else:
            action = "无变化"

        result = ToolResult(
            success=True,
            message=f"API 索引已{action}: {api} @ {project}",
        )
        logger.info("API 索引写入成功: api=%s, project=%s, action=%s", api, project, action)
        return result.model_dump()

    except Exception as exc:
        logger.error("数据库写入失败: %s", exc)
        raise ToolException(f"写入失败: {exc}") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


# 启用错误处理：ToolException 消息会作为 tool message 返回给 LLM，
# 而不是导致 Agent 执行中断。
save_api_index.handle_tool_error = True


# ---------------------------------------------------------------------------
# SQL — 查询
# ---------------------------------------------------------------------------

_QUERY_SQL_BASE = """\
SELECT api, project, source, doc FROM t_api_index WHERE 1=1\
"""


# ---------------------------------------------------------------------------
# LangChain Tool — 查询
# ---------------------------------------------------------------------------


@tool
def query_api_index(api: str = "", project: str = "") -> dict:
    """从数据库中查询 API 文档索引记录。

    根据 api 函数名和/或 project 项目名进行筛选，
    两个参数均可选，为空时不作为过滤条件（全部为空则返回所有记录）。

    Args:
        api: API 函数名（如 "HandleLogin"），为空则不过滤
        project: 项目名称（如 "ubill-access-api"），为空则不过滤

    Returns:
        包含 success、message 和 data 的结果字典，
        data 为匹配记录的列表，每条记录包含 api、project、source、doc 字段

    Raises:
        ToolException: 数据库未配置、连接或查询失败时抛出，
            错误信息会通过 handle_tool_error 传递给 LLM。
    """
    # 1. 构建动态 SQL
    sql = _QUERY_SQL_BASE
    params: list[str] = []

    if api and api.strip():
        sql += " AND api = %s"
        params.append(api.strip())
    if project and project.strip():
        sql += " AND project = %s"
        params.append(project.strip())

    # 2. 获取数据库配置
    db_cfg = _get_db_config()

    # 3. 连接
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(
            host=db_cfg.host,
            port=db_cfg.port,
            user=db_cfg.user,
            password=db_cfg.password,
            database=db_cfg.database,
        )
    except Exception as exc:
        logger.error("数据库连接失败: %s", exc)
        raise ToolException(f"数据库连接失败: {exc}") from exc

    # 4. 执行查询
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params)
        rows = cursor.fetchall()

        result = ToolResult(
            success=True,
            message=f"查询完成，共 {len(rows)} 条记录",
        )
        resp = result.model_dump()
        resp["data"] = rows
        logger.info("API 索引查询成功: 条件 api=%s, project=%s, 结果数=%d", api, project, len(rows))
        return resp

    except Exception as exc:
        logger.error("数据库查询失败: %s", exc)
        raise ToolException(f"查询失败: {exc}") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


query_api_index.handle_tool_error = True