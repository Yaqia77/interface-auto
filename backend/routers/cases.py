"""用例查询接口：直接复用 core.excel_loader 解析存量 Excel。"""
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from backend.schemas import CaseOut, CasePage
from core import excel_loader
from core.excel_loader import ExcelFormatError

ROOT = Path(__file__).resolve().parents[2]  # 项目根（backend/routers/ 上溯两级）

router = APIRouter(prefix="/api/cases", tags=["用例管理"])

# 简单缓存：文件路径 -> (mtime, LoadResult)。Excel 改动后 mtime 变化即自动失效。
_cache: dict[str, tuple[float, object]] = {}


def _load_cached(path: Path):
    key = str(path)
    mtime = path.stat().st_mtime
    hit = _cache.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    result = excel_loader.load(path)
    _cache[key] = (mtime, result)
    return result


def _resolve_file(file: str) -> Path:
    p = Path(file)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"用例文件不存在: {file}")
    return p


def _filtered(cases: list, module: str | None, priority: str | None,
              keyword: str | None, run: bool | None) -> list:
    """筛选逻辑与 conftest 的命令行参数保持一致（平台/CLI 行为对齐）。"""
    out = cases
    if module:
        out = [c for c in out if module in c.module]
    if priority:
        wanted = {p.strip().upper() for p in priority.split(",") if p.strip()}
        out = [c for c in out if c.priority in wanted]
    if keyword:
        kw = keyword.strip().lower()
        out = [c for c in out if kw in " ".join(
            [c.case_id, c.api_name, c.case_desc, c.url]).lower()]
    if run is not None:
        out = [c for c in out if c.run is run]
    return out


@router.get("", response_model=CasePage, summary="用例列表（支持筛选）")
def list_cases(
    file: str = Query(default="data/api_cases.xlsx", description="用例文件或目录（相对项目根）"),
    module: str | None = Query(default=None, description="模块名，包含匹配"),
    priority: str | None = Query(default=None, description="优先级，逗号分隔，如 P0,P1"),
    keyword: str | None = Query(default=None, description="编号/接口名/描述/URL 关键字"),
    run: bool | None = Query(default=None, description="是否启用（Y/N 列）"),
):
    path = _resolve_file(file)
    try:
        result = _load_cached(path)
    except ExcelFormatError as e:
        # Excel 格式错误把 loader 的逐行定位信息原样透出，方便前端展示
        raise HTTPException(status_code=400, detail=str(e))
    cases = _filtered(result.cases, module, priority, keyword, run)
    return CasePage(total=len(cases), items=[CaseOut(**asdict(c)) for c in cases])


@router.get("/variables", summary="全局变量名列表（值做了掩码，不回显敏感内容）")
def list_variables(file: str = Query(default="data/api_cases.xlsx")):
    path = _resolve_file(file)
    try:
        result = _load_cached(path)
    except ExcelFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "excel_variables": sorted(result.variables),
        "secret_variables": sorted(excel_loader.load_secret_vars(ROOT / "data" / "secret_vars.xlsx")),
    }


@router.get("/{case_id}", response_model=CaseOut, summary="用例详情")
def get_case(case_id: str, file: str = Query(default="data/api_cases.xlsx")):
    path = _resolve_file(file)
    try:
        result = _load_cached(path)
    except ExcelFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    for c in result.cases:
        if c.case_id == case_id:
            return CaseOut(**asdict(c))
    raise HTTPException(status_code=404, detail=f"用例不存在: {case_id}")
