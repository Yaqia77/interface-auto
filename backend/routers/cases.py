"""用例查询与写回接口：读取复用 core.excel_loader，更新走 backend.excel_writer（校验后原子落盘）。"""
import json
from collections import Counter
from dataclasses import asdict
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from backend import excel_writer
from backend.excel_writer import CaseWriteError
from backend.schemas import CaseCreate, CaseOut, CasePage, CaseUpdate
from core import excel_loader
from core.excel_loader import CASE_COLUMNS, ExcelFormatError

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


_ASSERT_OP_DESC = {
    "eq": "等于", "neq": "不等于", "contains": "包含", "gt": "大于", "ge": "大于等于",
    "lt": "小于", "le": "小于等于", "regex": "正则匹配", "not_null": "不为空", "len_eq": "长度等于",
}

# 基础请求头内置候选（用例中实际出现过的值会覆盖建议值；都排在候选列表最前）
_BUILTIN_HEADERS = {
    "Content-Type": "application/json",
    "Authorization": "Basic {{auth_token}}",
    "x-yun-api-version": "v2",
    "User-Agent": "interface-auto/1.0",
}


@router.get("/meta", summary="编辑用元数据（优先级/模块/请求头/断言操作符/变量候选）")
def case_meta(file: str = Query(default="data/api_cases.xlsx")):
    path = _resolve_file(file)
    try:
        result = _load_cached(path)
    except ExcelFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 请求头候选：聚合存量用例 —— key 按出现频次降序，建议值取该 key 最常见的完整值
    key_freq: Counter = Counter()
    kv_freq: Counter = Counter()
    for c in result.cases:
        for k, v in (c.headers or {}).items():
            key_freq[k] += 1
            kv_freq[(k, str(v))] += 1
    suggest: dict[str, str] = dict(_BUILTIN_HEADERS)
    for k in key_freq:  # 存量实测值覆盖内置默认建议（取出现频次最高的完整值）
        best_val = max((kv_freq[(k, vv)], vv) for (kk, vv) in kv_freq if kk == k)[1]
        suggest[k] = best_val
    # 排序：内置基础头在前，其余按出现频次降序
    ordered = sorted(suggest, key=lambda k: (k not in _BUILTIN_HEADERS, -key_freq.get(k, 0)))
    header_suggest = [{"key": k, "value": suggest[k], "used": key_freq.get(k, 0)} for k in ordered]

    return {
        "priorities": sorted(excel_loader.VALID_PRIORITIES),
        "methods": sorted(excel_loader.VALID_METHODS),
        "assert_ops": [{"op": o, "desc": _ASSERT_OP_DESC.get(o, o),
                        "need_expected": o in excel_loader.OPS_NEED_EXPECTED}
                       for o in sorted(excel_loader.ASSERT_OPS)],
        "modules": sorted({c.module for c in result.cases}),
        "header_suggest": header_suggest,
        "variables": sorted(set(result.variables) |
                            set(excel_loader.load_secret_vars(ROOT / "data" / "secret_vars.xlsx"))),
    }


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


@router.get("/export", summary="导出用例 xlsx（按筛选条件）")
def export_cases(
    file: str = Query(default="data/api_cases.xlsx"),
    module: str | None = None,
    priority: str | None = None,
    keyword: str | None = None,
    run: bool | None = None,
):
    path = _resolve_file(file)
    try:
        result = _load_cached(path)
    except ExcelFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    cases = _filtered(result.cases, module, priority, keyword, run)

    wb = Workbook()
    ws = wb.active
    ws.title = "用例"
    headers = list(CASE_COLUMNS.keys())
    ws.append(headers)

    fields = list(CASE_COLUMNS.values())
    for c in cases:
        row = []
        for f in fields:
            v = getattr(c, f, None)
            if f == "run":
                row.append("Y" if v else "N")
            elif f in ("headers", "params", "extract", "asserts"):
                row.append(json.dumps(v, ensure_ascii=False) if v else None)
            elif f == "body":
                if v is None:
                    row.append(None)
                elif isinstance(v, str):
                    row.append(v)
                else:
                    row.append(json.dumps(v, ensure_ascii=False))
            elif f == "timeout":
                row.append(float(v) if v else None)
            else:
                row.append(v)
        ws.append(row)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="cases_export.xlsx"'},
    )


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


_ERROR_STATUS = {"invalid": 400, "not_found": 404, "conflict": 409, "locked": 409}


@router.post("", response_model=CaseOut, summary="新增用例（追加行写回 Excel）", status_code=201)
def create_case(body: CaseCreate, file: str = Query(default="data/api_cases.xlsx")):
    path = _resolve_file(file)
    if path.is_dir():
        raise HTTPException(status_code=400, detail="目录模式下无法确定新增目标文件，请指定具体 xlsx")
    data = body.model_dump()
    try:
        excel_writer.append_case(path, data)
    except CaseWriteError as e:
        raise HTTPException(status_code=_ERROR_STATUS[e.kind], detail=str(e))
    fresh = next((c for c in _load_cached(path).cases if c.case_id == body.case_id), None)
    if fresh is None:
        raise HTTPException(status_code=500, detail="新增后未能重新读到用例")
    return CaseOut(**asdict(fresh))


@router.post("/import", summary="导入用例 xlsx（追加不重复的 case_id）")
async def import_cases(
    uploaded_file: UploadFile = File(..., description="xlsx 文件，格式与导出一致"),
    file: str = Query(default="data/api_cases.xlsx", description="目标用例文件"),
):
    # 校验目标
    path = _resolve_file(file)
    if path.is_dir():
        raise HTTPException(status_code=400, detail="目录模式下无法确定导入目标文件，请指定具体 xlsx")
    # 检查上传文件扩展名
    if not (uploaded_file.filename or "").endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 文件")

    # 保存到临时文件
    tmp = path.with_name(f"~$import_tmp_{uploaded_file.filename}")
    try:
        content = await uploaded_file.read()
        tmp.write_bytes(content)

        # 解析导入文件
        try:
            import_result = excel_loader.load(tmp)
        except ExcelFormatError as e:
            raise HTTPException(status_code=400, detail=f"导入文件格式错误: {e}")
        except FileNotFoundError:
            raise HTTPException(status_code=400, detail="导入文件为空或无法读取")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"无法解析 xlsx: {e!r}")

        # 批量追加
        try:
            summary = excel_writer.bulk_append(path, import_result.cases)
        except CaseWriteError as e:
            raise HTTPException(status_code=_ERROR_STATUS.get(e.kind, 400), detail=str(e))

        return summary
    finally:
        tmp.unlink(missing_ok=True)


@router.delete("/{case_id}", summary="删除用例（Excel 整行删除，校验通过才落盘）")
def delete_case(case_id: str, file: str = Query(default="data/api_cases.xlsx")):
    path = _resolve_file(file)
    try:
        result = _load_cached(path)
    except ExcelFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    target = next((c for c in result.cases if c.case_id == case_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"用例不存在: {case_id}")
    target_file = (path / target.source) if path.is_dir() else path
    try:
        excel_writer.delete_case(target_file, case_id, target.row)
    except CaseWriteError as e:
        raise HTTPException(status_code=_ERROR_STATUS[e.kind], detail=str(e))
    return {"deleted": case_id, "file": target_file.name}


@router.put("/{case_id}", response_model=CaseOut, summary="更新用例（写回 Excel，校验通过才落盘）")
def update_case(case_id: str, body: CaseUpdate, file: str = Query(default="data/api_cases.xlsx")):
    path = _resolve_file(file)
    try:
        result = _load_cached(path)
    except ExcelFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    target = next((c for c in result.cases if c.case_id == case_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"用例不存在: {case_id}")

    # 真实写入文件：目录模式下用用例自身的 source 定位到具体 xlsx
    target_file = (path / target.source) if path.is_dir() else path
    changes = body.model_dump(exclude_unset=True)
    try:
        excel_writer.apply_update(target_file, case_id, target.row, changes)
    except CaseWriteError as e:
        raise HTTPException(status_code=_ERROR_STATUS[e.kind], detail=str(e))

    # 文件 mtime 已变，缓存自动失效；重读返回最新视图
    fresh = next((c for c in _load_cached(path).cases if c.case_id == case_id), None)
    if fresh is None:  # 理论不可达：写回前后都过了 loader 校验
        raise HTTPException(status_code=500, detail="写回后未能重新读到用例")
    return CaseOut(**asdict(fresh))
