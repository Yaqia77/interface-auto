"""Pydantic 请求/响应模型（自动生成 OpenAPI 文档的类型契约）。"""
from typing import Any

from pydantic import BaseModel, Field


class CaseOut(BaseModel):
    """一条用例（对应 core.models.TestCase 的对外视图）。"""

    case_id: str
    module: str
    api_name: str
    case_desc: str
    priority: str
    run: bool
    method: str
    url: str
    headers: dict | None = None
    params: dict | None = None
    body: Any = None
    extract: dict | None = None
    asserts: list | None = None
    timeout: float | None = None
    source: str = Field(description="来源 Excel 文件名")
    row: int = Field(description="来源 Excel 行号")


class CasePage(BaseModel):
    total: int
    items: list[CaseOut]


class RunCreate(BaseModel):
    """发起一次执行批次。"""

    env: str | None = Field(default=None, description="环境名，留空用 config.yaml 的 default_env")
    module: str | None = Field(default=None, description="按模块筛选（包含匹配）")
    priority: str | None = Field(default=None, description="按优先级筛选，逗号分隔，如 P0,P1")
    keyword: str | None = Field(default=None, description="关键字筛选（编号/接口名/描述/URL）")
    file: str = Field(default="data/api_cases.xlsx", description="用例文件或目录（相对项目根）")


class RunOut(BaseModel):
    run_id: str
    status: str = Field(description="pending / running / passed / failed / error")
    source: str = Field(default="api", description="api=后端发起，cli=历史本地运行")
    args: dict | None = None
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    report_dir: str | None = Field(default=None, description="报告目录（相对项目根）")
    log_tail: str | None = None


class HealthOut(BaseModel):
    status: str
    default_env: str | None = None
    cases_file_exists: bool
