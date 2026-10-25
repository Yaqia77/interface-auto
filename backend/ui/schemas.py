"""UI 自动化请求/响应模型（自动生成 OpenAPI 文档的类型契约）。"""
from typing import Any

from pydantic import BaseModel, Field


# ==================== UI 用例（JSON 载体，结构化步骤） ====================


class UiStep(BaseModel):
    """一个 UI 步骤：动作 + 定位器 + 取值（三者必要性由动作决定，见 ui_case_store.ACTIONS）。"""

    action: str = Field(description="动作：goto/click/fill/press/select/check/hover/wait_for/screenshot/expect_visible/expect_text/expect_url")
    locator: str | None = Field(default=None, description="定位器：css=(缺省)/xpath=/text=/role= 前缀")
    value: Any = Field(default=None, description="取值/期望值（支持 {{var}} 变量）")
    desc: str = Field(default="", description="步骤备注")


class UiExtract(BaseModel):
    """变量提取：source 形如 text|<locator> / input_value|<locator> / cookie:<name>。"""

    var: str = Field(description="变量名")
    source: str = Field(description="提取来源表达式")


class UiCaseOut(BaseModel):
    """一条 UI 用例（对应 ui_case_store.validate_case 清洗后的结构）。"""

    case_id: str
    module: str
    name: str
    desc: str = ""
    priority: str
    run: bool
    browser: str = "chromium"
    headless: bool = True
    steps: list[UiStep]
    extract: list[UiExtract] = Field(default_factory=list)
    pre_scripts: list[str] = Field(default_factory=list)
    post_scripts: list[str] = Field(default_factory=list)


class UiCasePage(BaseModel):
    total: int
    items: list[UiCaseOut]


class UiCaseCreate(BaseModel):
    """新增 UI 用例（编号唯一；steps 至少一步）。"""

    case_id: str = Field(description="用例编号（唯一）")
    steps: list[UiStep] = Field(description="步骤列表（至少一步）")
    name: str = Field(default="新建UI用例", description="用例名称")
    module: str = Field(default="未分类", description="模块名")
    desc: str = Field(default="", description="用例描述")
    priority: str = Field(default="P2", description="P0~P5")
    run: bool = Field(default=True, description="是否执行")
    browser: str = Field(default="chromium", description="chromium/firefox/webkit")
    headless: bool = Field(default=True, description="无头模式")
    extract: list[UiExtract] = Field(default_factory=list)
    pre_scripts: list[str] = Field(default_factory=list)
    post_scripts: list[str] = Field(default_factory=list)


class UiCaseUpdate(BaseModel):
    """更新 UI 用例（只传需改字段；case_id 不可改）。"""

    name: str | None = None
    module: str | None = None
    desc: str | None = None
    priority: str | None = None
    run: bool | None = None
    browser: str | None = None
    headless: bool | None = None
    steps: list[UiStep] | None = None
    extract: list[UiExtract] | None = None
    pre_scripts: list[str] | None = None
    post_scripts: list[str] | None = None


class UiCaseMove(BaseModel):
    """迁移 UI 用例到另一个 UI 项目：目标查重 → 写入目标 → 源删除。"""

    to_file: str = Field(description="目标 UI 项目的用例 JSON 路径（相对项目根）")
    new_module: str | None = Field(default=None, description="迁移后归入的模块名（留空=保留原模块）")
