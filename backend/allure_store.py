"""allure-results 目录解析 + 敏感信息掩码（平台原生报告页数据源）。

安全约定：任何请求/响应/错误文本离开后端前必须过 mask_*，
绝不把真实 Authorization、长数字 ID、对象存储签名透给前端。
"""
import json
import re
from pathlib import Path

# ---------- 掩码 ----------

# Authorization 头的值（JSON/文本两种形态）
_AUTH_RE = re.compile(r"((?:Authorization|X-Auth|Cookie)[\"']?\s*[:=]\s*[\"']?)([A-Za-z0-9+/=_.,-]{14,})", re.I)
# 对象存储预签名参数
_SIG_RE = re.compile(r"(X-Amz-(?:Signature|Credential)=)[^&\"'\s]+", re.I)
# 15 位以上连续数字（userId/手机号类标识）
_LONG_DIGITS_RE = re.compile(r"\d{15,}")
_SENSITIVE_KEYS = {"authorization", "cookie", "x-auth", "password", "token"}


def _short(value: str) -> str:
    if len(value) <= 12:
        return value
    return value[:8] + "****" + value[-4:] if len(value) <= 40 else value[:8] + f"****（{len(value)} 位已隐藏）"


def mask_text(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text
    text = _AUTH_RE.sub(lambda m: m.group(1) + _short(m.group(2)), text)
    text = _SIG_RE.sub(lambda m: m.group(1) + "****", text)
    text = _LONG_DIGITS_RE.sub(lambda m: m.group(0)[:4] + "****" + m.group(0)[-2:], text)
    return text


def mask_obj(obj):
    """递归掩码 dict/list：敏感键整体短掩码，字符串值走文本规则。"""
    if isinstance(obj, dict):
        return {
            k: (_short(str(v)) if k.lower() in _SENSITIVE_KEYS else mask_obj(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [mask_obj(x) for x in obj]
    if isinstance(obj, str):
        return mask_text(obj)
    return obj


# ---------- allure-results 解析 ----------

_PRIORITY_RE = re.compile(r"\[(P\d)\]")
_CASE_ID_RE = re.compile(r"case_id='([^']+)'")
_BODY_LIMIT = 4000  # 响应体截断长度，报告页排障够用，避免吐超大对象


def _load_results(results_dir: Path) -> list[dict]:
    items = []
    for f in sorted(results_dir.glob("*-result.json")):
        try:
            with open(f, encoding="utf-8") as fp:
                items.append(json.load(fp))
        except (json.JSONDecodeError, OSError):
            continue
    items.sort(key=lambda x: x.get("start") or 0)
    return items


def _find_attachment(result: dict, keyword: str) -> str | None:
    for a in result.get("attachments", []):
        if keyword in (a.get("name") or ""):
            return a.get("source")
    return None


def _case_id(result: dict) -> str:
    for p in result.get("parameters", []):
        m = _CASE_ID_RE.search(str(p.get("value", "")))
        if m:
            return m.group(1)
    m = re.search(r"\]\s+(\S+)", result.get("name", ""))
    return m.group(1) if m else result.get("name", "?")


def infer_status(results_dir: Path) -> str:
    """从 allure-results 推断批次结论（给无内存记录的 cli 历史批次用）。"""
    statuses = []
    for f in results_dir.glob("*-result.json"):
        try:
            with open(f, encoding="utf-8") as fp:
                statuses.append(json.load(fp).get("status"))
        except (json.JSONDecodeError, OSError):
            continue
    if not statuses:
        return "unknown"
    bad = {s for s in statuses if s not in ("passed", "skipped")}
    return "failed" if bad else "passed"


def list_cases(results_dir: Path) -> dict:
    """批次用例结果摘要 + 统计。"""
    summary = []
    stats = {"passed": 0, "failed": 0, "broken": 0, "skipped": 0}
    for r in _load_results(results_dir):
        status = r.get("status", "unknown")
        if status in stats:
            stats[status] += 1
        name = r.get("name", "")
        prio = (_PRIORITY_RE.search(name) or [None, ""])[1] if _PRIORITY_RE.search(name) else ""
        summary.append({
            "case_id": _case_id(r),
            "name": name,
            "priority": prio,
            "status": status,
            "duration_ms": (r.get("stop") or 0) - (r.get("start") or 0),
            "error": mask_text((r.get("statusDetails") or {}).get("message", ""))[:1200],
        })
    return {"total": len(summary), "stats": stats, "items": summary}


def case_detail(results_dir: Path, case_id: str) -> dict | None:
    """单用例明细：请求/响应快照（均已掩码+截断）+ 失败信息。"""
    for r in _load_results(results_dir):
        if _case_id(r) != case_id:
            continue
        detail = {
            "case_id": case_id,
            "name": r.get("name", ""),
            "status": r.get("status", "unknown"),
            "description": mask_text(r.get("description", "")),
            "error": mask_text((r.get("statusDetails") or {}).get("message", "")),
            "trace": mask_text((r.get("statusDetails") or {}).get("trace", ""))[:2000],
            "request": None,
            "response": None,
        }
        src = _find_attachment(r, "请求")
        if src and (results_dir / src).exists():
            with open(results_dir / src, encoding="utf-8") as fp:
                detail["request"] = mask_obj(json.load(fp))
        src = _find_attachment(r, "响应")
        if src and (results_dir / src).exists():
            with open(results_dir / src, encoding="utf-8") as fp:
                resp = json.load(fp)
            if isinstance(resp.get("body"), str) and len(resp["body"]) > _BODY_LIMIT:
                resp["body"] = resp["body"][:_BODY_LIMIT] + "…（已截断，完整内容见 Allure 报告）"
            detail["response"] = mask_obj(resp)
        return detail
    return None
