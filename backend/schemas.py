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


class CaseUpdate(BaseModel):
    """用例更新（只传需要改的字段；case_id 不可改，它是写回定位的行锁锚点）。"""

    module: str | None = None
    api_name: str | None = None
    case_desc: str | None = None
    priority: str | None = Field(default=None, description="P0~P5")
    run: bool | None = Field(default=None, description="是否执行（写回 Y/N）")
    method: str | None = Field(default=None, description="GET/POST/PUT/DELETE/PATCH")
    url: str | None = None
    headers: dict | None = None
    params: dict | None = None
    body: Any = None
    extract: dict | None = None
    asserts: list | None = Field(default=None, description="[[操作符, 取值路径, 期望值], ...]")
    timeout: float | None = Field(default=None, description="秒，正数；传 null 清空用 exclude 控制")


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
