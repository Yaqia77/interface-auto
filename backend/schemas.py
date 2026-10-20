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


class CaseCreate(BaseModel):
    """新增用例（整行写入 Excel 末行；编号唯一）。"""

    case_id: str = Field(description="用例编号（唯一，写回定位的行锁锚点）")
    api_name: str = Field(description="接口名称（必填）")
    url: str = Field(description="请求路径（必填）")
    method: str = Field(description="GET/POST/PUT/DELETE/PATCH")
    asserts: list | None = Field(default=None, description="[[操作符, 取值路径, 期望值], ...]，至少一条")
    module: str = "未分类"
    case_desc: str = "新建用例"
    priority: str = Field(default="P2", description="P0~P5")
    run: bool = Field(default=True, description="是否执行（写回 Y/N）")
    headers: dict | None = None
    params: dict | None = None
    body: Any = None
    extract: dict | None = None
    timeout: float | None = None


class RunCreate(BaseModel):
    """发起一次执行批次。"""

    env: str | None = Field(default=None, description="环境名，留空用 config.yaml 的 default_env")
    module: str | None = Field(default=None, description="按模块筛选（包含匹配）")
    priority: str | None = Field(default=None, description="按优先级筛选，逗号分隔，如 P0,P1")
    keyword: str | None = Field(default=None, description="关键字筛选（编号/接口名/描述/URL）")
    cases: list[str] | None = Field(default=None, description="按用例编号精确选择（优先于 module/priority/keyword）")
    vars: dict[str, Any] | None = Field(default=None, description="运行前变量覆盖（键值映射，覆盖同名 secret/Excel/YAML 变量）")
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


class EnvItem(BaseModel):
    """单个环境的可编辑配置（写回 config.yaml 的 env 段）。"""

    name: str = Field(description="环境名（唯一，YAML key）")
    base_url: str = Field(description="基础 URL，必须以 http(s):// 开头")
    timeout: float | None = Field(default=None, description="秒，正数；留空用框架默认")
    verify_ssl: bool = Field(default=True, description="是否校验 TLS 证书")
    default_headers: dict | None = Field(default=None, description="环境默认请求头（用例头优先）")


class EnvsUpdate(BaseModel):
    """整体覆盖式保存环境配置（镜像当前 env 段，含默认环境）。"""

    default_env: str = Field(description="默认环境名，必须是 envs 之一")
    envs: list[EnvItem] = Field(description="完整环境列表（至少一个）")


class PlanCreate(BaseModel):
    """新建测试场景。"""

    name: str = Field(description="场景名称")
    desc: str = Field(default="", description="场景描述")
    case_ids: list[str] = Field(description="用例编号列表（至少一条）")
    env: str = Field(default="", description="偏好环境名（空则用默认环境）")


class PlanUpdate(BaseModel):
    """更新场景（只传需要修改的字段）。"""

    name: str | None = None
    desc: str | None = None
    case_ids: list[str] | None = None
    env: str | None = None


class PlanOut(BaseModel):
    """场景对外视图。"""

    id: str
    name: str
    desc: str
    case_ids: list[str]
    env: str
    created_at: str
    updated_at: str
    last_run_id: str | None = None
    last_run_at: str | None = None
