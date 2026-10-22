"""UI 用例查询与写回接口：读写复用 backend.ui_case_store（校验后原子落 JSON）。

与 /api/cases 分轨：接口用例走 Excel，UI 用例走 JSON。项目 kind=ui 时前端把项目的
file（.json）透传给本组接口；权限直接复用 case:write / case:delete，执行/报告链路复用。
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from backend import authz, ui_case_store
from backend.schemas import (UiCaseCreate, UiCaseMove, UiCaseOut, UiCasePage,
                             UiCaseUpdate)
from backend.ui_case_store import UiCaseError

ROOT = Path(__file__).resolve().parents[2]  # 项目根（backend/routers/ 上溯两级）

router = APIRouter(prefix="/api/ui-cases", tags=["UI 用例"])

_ERROR_STATUS = {"invalid": 400, "not_found": 404, "conflict": 409, "locked": 409}


def _resolve_file(file: str) -> Path:
    """把相对路径解析为项目根下的 UI 用例 JSON 文件；非 .json 直接拒绝（防误写 Excel）。"""
    p = Path(file)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"UI 用例文件不存在: {file}")
    if p.is_dir() or p.suffix.lower() != ".json":
        raise HTTPException(status_code=400, detail="UI 用例接口只接受 .json 项目文件，接口用例请走 /api/cases")
    return p


def _raise(e: UiCaseError):
    raise HTTPException(status_code=_ERROR_STATUS.get(e.kind, 400), detail=str(e))


def _to_out(case: dict) -> UiCaseOut:
    """store 清洗后的 dict → 对外模型（steps/extract 元素已是 dict，直接喂 pydantic）。"""
    return UiCaseOut(**case)


@router.get("", response_model=UiCasePage, summary="UI 用例列表（支持筛选）")
def list_cases(
    file: str = Query(..., description="UI 项目的用例 JSON 路径（相对项目根）"),
    module: str | None = Query(default=None, description="模块名，包含匹配"),
    priority: str | None = Query(default=None, description="优先级，逗号分隔，如 P0,P1"),
    keyword: str | None = Query(default=None, description="编号/名称/描述 关键字"),
    run: bool | None = Query(default=None, description="是否启用"),
):
    path = _resolve_file(file)
    try:
        cases = ui_case_store.list_cases(path, module, priority, keyword, run)
    except UiCaseError as e:
        _raise(e)
    return UiCasePage(total=len(cases), items=[_to_out(c) for c in cases])


@router.get("/meta", summary="编辑用元数据（优先级/浏览器/模块/动作字典）")
def case_meta(file: str = Query(..., description="UI 项目的用例 JSON 路径（相对项目根）")):
    path = _resolve_file(file)
    try:
        return ui_case_store.meta(path)
    except UiCaseError as e:
        _raise(e)


@router.get("/variables", summary="全局变量名列表（值掩码，供步骤取值插入变量参考）")
def list_variables(file: str = Query(..., description="UI 项目的用例 JSON 路径（相对项目根）")):
    from core import excel_loader
    path = _resolve_file(file)
    try:
        cases = ui_case_store.load_cases(path)
    except UiCaseError as e:
        _raise(e)
    # UI 项目自身无全局变量表，变量来自环境配置 + 凭证 + 本批用例 extract 出的变量名
    extracted = sorted({e.get("var") for c in cases for e in (c.get("extract") or []) if e.get("var")})
    return {
        "excel_variables": extracted,
        "secret_variables": sorted(excel_loader.load_secret_vars(ROOT / "data" / "secret_vars.xlsx")),
    }


@router.get("/{case_id}", response_model=UiCaseOut, summary="UI 用例详情")
def get_case(case_id: str, file: str = Query(..., description="UI 项目的用例 JSON 路径（相对项目根）")):
    path = _resolve_file(file)
    try:
        case = ui_case_store.get_case(path, case_id)
    except UiCaseError as e:
        _raise(e)
    if case is None:
        raise HTTPException(status_code=404, detail=f"用例不存在: {case_id}")
    return _to_out(case)


@router.post("", response_model=UiCaseOut, summary="新增 UI 用例（追加到 JSON，校验通过才落盘）", status_code=201)
def create_case(body: UiCaseCreate, file: str = Query(..., description="UI 项目的用例 JSON 路径（相对项目根）"),
                _: dict = Depends(authz.require_perm("case:write"))):
    path = _resolve_file(file)
    try:
        case = ui_case_store.create_case(path, body.model_dump())
    except UiCaseError as e:
        _raise(e)
    return _to_out(case)


@router.put("/{case_id}", response_model=UiCaseOut, summary="更新 UI 用例（写回 JSON，校验通过才落盘）")
def update_case(case_id: str, body: UiCaseUpdate,
                file: str = Query(..., description="UI 项目的用例 JSON 路径（相对项目根）"),
                _: dict = Depends(authz.require_perm("case:write"))):
    path = _resolve_file(file)
    changes = body.model_dump(exclude_unset=True)
    try:
        case = ui_case_store.update_case(path, case_id, changes)
    except UiCaseError as e:
        _raise(e)
    return _to_out(case)


@router.delete("/{case_id}", summary="删除 UI 用例（校验通过才落盘）")
def delete_case(case_id: str, file: str = Query(..., description="UI 项目的用例 JSON 路径（相对项目根）"),
                _: dict = Depends(authz.require_perm("case:delete"))):
    path = _resolve_file(file)
    try:
        ui_case_store.delete_case(path, case_id)
    except UiCaseError as e:
        _raise(e)
    return {"deleted": case_id, "file": path.name}


@router.post("/{case_id}/move", summary="迁移 UI 用例到另一个 UI 项目（目标查重→写入目标→源删除）")
def move_case(case_id: str, body: UiCaseMove,
              file: str = Query(..., description="源 UI 项目的用例 JSON 路径（相对项目根）"),
              _: dict = Depends(authz.require_perm("case:write"))):
    src = _resolve_file(file)
    dst = _resolve_file(body.to_file)
    try:
        moved = ui_case_store.move_case(src, dst, case_id, body.new_module)
    except UiCaseError as e:
        _raise(e)
    return {
        "moved": case_id,
        "from_file": str(src.relative_to(ROOT)).replace("\\", "/"),
        "to_file": str(dst.relative_to(ROOT)).replace("\\", "/"),
        "case": _to_out(moved).model_dump(),
    }
