"""执行批次接口：以子进程调用 main.py（零改写复用 pytest+报告编排），后台线程收集日志。

批次记录落盘 reports/runs_history.json：服务重启/热重载不再丢失平台发起的批次历史；
日志仅保留尾部 200 行，重启后仍在报告页可查。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend import allure_store
from backend.schemas import RunCreate, RunOut

ROOT = Path(__file__).resolve().parents[2]  # 项目根（backend/routers/ 上溯两级）

router = APIRouter(prefix="/api/runs", tags=["执行中心"])

# 内存态登记表：run_id -> 记录。持久化兜底见 _persist / _load_history。
_runs: dict[str, dict] = {}
_LOCK = threading.Lock()

_HISTORY = ROOT / "reports" / "runs_history.json"
_LOG_KEEP = 200           # 落盘仅留日志尾部，排障够用且文件可控
_PERSIST_KEYS = ("run_id", "status", "args", "started_at", "finished_at", "exit_code", "report_dir")


def _persist(rec: dict) -> None:
    """单批次记录落盘（状态变更时调用；失败只记日志不影响主流程）。"""
    try:
        _HISTORY.parent.mkdir(parents=True, exist_ok=True)
        history: dict = {}
        if _HISTORY.exists():
            try:
                with open(_HISTORY, encoding="utf-8") as fp:
                    history = json.load(fp)
            except (json.JSONDecodeError, OSError):
                history = {}
        entry = {k: rec[k] for k in _PERSIST_KEYS}
        entry["log_tail"] = rec["log"][-_LOG_KEEP:]
        history[rec["run_id"]] = entry
        # 只留最近 200 条，防无限增长
        if len(history) > 200:
            for old in sorted(history)[: len(history) - 200]:
                history.pop(old)
        tmp = _HISTORY.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fp:
            json.dump(history, fp, ensure_ascii=False)
        os.replace(tmp, _HISTORY)
    except OSError:
        pass


_loaded = False


def _load_history() -> None:
    """懒加载：首次访问接口时恢复历史批次；running 残档说明进程已死，标 error。"""
    global _loaded
    _loaded = True
    if not _HISTORY.exists():
        return
    try:
        with open(_HISTORY, encoding="utf-8") as fp:
            history = json.load(fp)
    except (json.JSONDecodeError, OSError):
        return
    for rid, entry in history.items():
        if rid in _runs:
            continue
        log = entry.pop("log_tail", []) or []
        rec = {"run_id": rid, "log": log, "proc": None, **{k: entry.get(k) for k in _PERSIST_KEYS}}
        if rec["status"] == "running":
            rec["status"] = "error"
            log.append("（服务重启，批次执行线程已中断，状态不可知）")
        _runs[rid] = rec

_REPORT_DIR_RE = re.compile(r"\[interface-auto\] 报告目录:\s*(.+)$")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _rel(path: str) -> str:
    try:
        return str(Path(path).relative_to(ROOT))
    except ValueError:
        return path


def _status_from(rec: dict) -> str:
    if rec["status"] != "running" or rec["exit_code"] is None:
        return rec["status"]
    return "passed" if rec["exit_code"] == 0 else "failed"


def _to_out(rec: dict, log_tail: int = 0) -> RunOut:
    tail = None
    if log_tail and rec.get("log"):
        tail = "\n".join(rec["log"][-log_tail:])
    return RunOut(
        run_id=rec["run_id"], status=_status_from(rec), source="api",
        args=rec["args"], started_at=rec["started_at"], finished_at=rec["finished_at"],
        exit_code=rec["exit_code"], report_dir=rec["report_dir"], log_tail=tail,
    )


def _worker(run_id: str, cmd: list[str]):
    """子进程执行 + 日志逐行收集（供前端轮询/后续升级 WebSocket）。"""
    rec = _runs[run_id]
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", env=env,
        )
        rec["proc"] = proc
        for line in proc.stdout:                      # 阻塞逐行读，进程结束自然退出
            line = line.rstrip()
            rec["log"].append(line)
            m = _REPORT_DIR_RE.search(line)
            if m:
                rec["report_dir"] = _rel(m.group(1).strip())
        rec["exit_code"] = proc.wait()
    except Exception as e:
        rec["log"].append(f"后端执行异常: {e!r}")
        rec["status"] = "error"
    finally:
        rec["finished_at"] = _now()
        if rec["status"] == "running":
            rec["status"] = _status_from(rec)
        _persist(rec)


@router.post("", response_model=RunOut, summary="发起执行批次", status_code=202)
def create_run(body: RunCreate):
    # 用例文件存在性前置校验（格式错误留给执行时报错，与 CLI 行为一致）
    f = Path(body.file)
    if not f.is_absolute():
        f = ROOT / f
    if not f.exists():
        raise HTTPException(status_code=404, detail=f"用例文件不存在: {body.file}")

    cmd = [sys.executable, str(ROOT / "main.py"), "--file", body.file]
    if body.env:
        cmd.append(f"--env={body.env}")
    if body.module:
        cmd.append(f"--module={body.module}")
    if body.priority:
        cmd.append(f"--priority={body.priority}")
    if body.keyword:
        cmd.append(f"--keyword={body.keyword}")
    if body.cases:
        # 去重去空，保持前端传入顺序（但实际执行序以 Excel 行序为准，见 conftest）
        ids = list(dict.fromkeys(c for c in body.cases if c))
        if ids:
            cmd.append("--cases=" + ",".join(ids))
    if body.vars:
        cmd.append("--vars=" + json.dumps(body.vars, ensure_ascii=False))

    run_id = f"api_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    rec = {
        "run_id": run_id, "status": "running", "proc": None, "log": [],
        "args": body.model_dump(exclude_none=True), "started_at": _now(),
        "finished_at": None, "exit_code": None, "report_dir": None,
    }
    with _LOCK:
        if not _loaded:
            _load_history()
        _runs[run_id] = rec
        _persist(rec)
    threading.Thread(target=_worker, args=(run_id, cmd), daemon=True).start()
    return _to_out(rec)


@router.get("", response_model=list[RunOut], summary="批次列表（API 发起 + reports/ 历史）")
def list_runs(limit: int = 20):
    with _LOCK:
        if not _loaded:
            _load_history()
    items: list[RunOut] = [_to_out(r) for r in _runs.values()]

    # 扫描本地 CLI 历史运行目录，补全（source=cli；状态从 allure-results 推断）
    reports = ROOT / "reports"
    known = {r["report_dir"] for r in _runs.values() if r["report_dir"]}
    if reports.is_dir():
        for d in sorted(reports.glob("run_*"), reverse=True):
            rel = _rel(str(d))
            if rel in known:
                continue
            ts = datetime.strptime(d.name[4:], "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
            results = d / "allure-results"
            status = allure_store.infer_status(results) if results.is_dir() else "unknown"
            items.append(RunOut(run_id=rel, status=status, source="cli",
                                started_at=ts, report_dir=rel))
            if len(items) >= limit:
                break

    items.sort(key=lambda x: (x.started_at or ""), reverse=True)
    return items[:limit]


@router.get("/history/{case_id}", summary="单用例跨批次执行历史（新→旧）")
def case_history(case_id: str, limit: int = 30):
    """扫描近期批次的 allure-results，抽取该用例逐次结果，供用例历史时间线。

    只返回含该用例的批次；cli 历史目录会现场推断（扫描量受 limit 约束）。
    """
    limit = max(1, min(limit, 100))
    runs = list_runs(limit=500)
    history: list[dict] = []
    for r in runs:
        if len(history) >= limit:
            break
        rel = r.report_dir or _resolve_report_dir(r.run_id)
        if not rel:
            continue
        results = (ROOT / rel) / "allure-results"
        if not results.is_dir():
            continue
        rec = allure_store.case_run_summary(results, case_id)
        if rec is None:
            continue
        history.append({
            "run_id": r.run_id, "source": r.source, "started_at": r.started_at,
            "finished_at": r.finished_at, **rec,
        })
    # 连续失败（从最新往回数，非失败即断链）
    FAILED = {"failed", "broken"}
    consec = 0
    for h in history:
        if h["status"] in FAILED:
            consec += 1
        else:
            break
    return {
        "case_id": case_id,
        "scanned_batches": min(len(runs), 500),
        "found": len(history),
        "passed": sum(1 for h in history if h["status"] == "passed"),
        "failed": sum(1 for h in history if h["status"] in FAILED),
        "consec_fail": consec,
        "history": history,
    }


@router.get("/{run_id}", response_model=RunOut, summary="批次详情（含日志尾部）")
def get_run(run_id: str):
    with _LOCK:
        if not _loaded:
            _load_history()
        rec = _runs.get(run_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"批次不存在: {run_id}")
    return _to_out(rec, log_tail=100)


@router.post("/{run_id}/cancel", summary="取消运行中的批次（终止子进程树）")
def cancel_run(run_id: str):
    with _LOCK:
        if not _loaded:
            _load_history()
        rec = _runs.get(run_id)
        if rec is None:
            raise HTTPException(status_code=404, detail=f"批次不存在: {run_id}")
        if rec["status"] != "running":
            return {"run_id": run_id, "status": rec["status"], "cancelling": False}
        proc = rec.get("proc")
        rec["status"] = "cancelled"
        rec["finished_at"] = _now()
        rec["log"].append("[runner] 已请求取消（终止进程树）")
        _persist(rec)
    if proc is not None and proc.poll() is None:
        # Windows：terminate 只杀 main.py 自身，pytest 孙进程需 /T 连树杀掉
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       capture_output=True, text=True)
    return {"run_id": run_id, "status": "cancelled", "cancelling": True}


@router.get("/{run_id}/log", summary="批次完整日志（纯文本，供实时轮询）")
def get_log(run_id: str):
    with _LOCK:
        if not _loaded:
            _load_history()
        rec = _runs.get(run_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"批次不存在: {run_id}")
    return {"run_id": run_id, "status": _status_from(rec),
            "lines": len(rec["log"]), "log": "\n".join(rec["log"])}


# 历史批次 id 形式：run_YYYYMMDD_HHMMSS 或 reports/run_YYYYMMDD_HHMMSS（列表接口返回的 cli 条目）
_CLI_RUN_RE = re.compile(r"^(?:reports[/\\])?run_\d{8}_\d{6}$")


def _resolve_report_dir(run_id: str) -> str | None:
    """run_id -> 报告目录（相对项目根）。内存优先，其次认领 reports/ 历史目录。"""
    with _LOCK:
        if not _loaded:
            _load_history()
        rec = _runs.get(run_id)
    if rec:
        return rec["report_dir"]
    if _CLI_RUN_RE.match(run_id):
        return run_id if run_id.startswith("reports") else f"reports/{run_id}"
    return None


@router.get("/{run_id}/report", summary="批次报告（allure=中文单文件 / html=pytest-html）")
def get_report(run_id: str, view: str = "allure"):
    """直接返回 HTML，前端可 iframe 内嵌或 window.open。

    allure 首次访问时现场生成（allure generate + allurerc.mjs 中文单文件），之后走已生成缓存。
    """
    rel = _resolve_report_dir(run_id)
    if rel is None:
        raise HTTPException(status_code=404, detail=f"批次不存在或报告目录未生成: {run_id}")
    d = (ROOT / rel).resolve()
    if d != ROOT and ROOT not in d.parents:
        raise HTTPException(status_code=400, detail="非法报告路径")
    if not d.is_dir():
        raise HTTPException(status_code=404, detail=f"报告目录不存在: {rel}")

    if view == "html":
        p = d / "report.html"
        if not p.exists():
            raise HTTPException(status_code=404, detail="pytest-html 报告不存在（运行时可能用了 --no-html）")
        return FileResponse(p, media_type="text/html")

    results, out = d / "allure-results", d / "allure-report"
    index = out / "index.html"
    if not index.exists():
        if not results.is_dir():
            fallback = d / "report.html"
            if fallback.exists():  # 无 allure 结果时退回 pytest-html，避免前端白屏
                return FileResponse(fallback, media_type="text/html")
            raise HTTPException(status_code=404, detail="allure-results 不存在，无法生成报告")
        allure_cmd = shutil.which("allure")
        if not allure_cmd:
            raise HTTPException(status_code=501, detail="未找到 allure CLI（npm install -g allure）")
        cfg = ROOT / "allurerc.mjs"
        cmd = [allure_cmd, "generate", str(results), "--output", str(out)]
        if cfg.exists():
            cmd += ["--config", str(cfg)]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=180, cwd=str(ROOT))
        if proc.returncode != 0 or not index.exists():
            raise HTTPException(status_code=500, detail=f"allure generate 失败: {(proc.stderr or proc.stdout)[-400:]}")
    return FileResponse(index, media_type="text/html")


def _results_dir_or_404(run_id: str) -> Path:
    """平台明细接口共用：定位批次的 allure-results 目录。"""
    rel = _resolve_report_dir(run_id)
    if rel is None:
        raise HTTPException(status_code=404, detail=f"批次不存在或报告目录未生成: {run_id}")
    d = (ROOT / rel).resolve()
    if d != ROOT and ROOT not in d.parents:
        raise HTTPException(status_code=400, detail="非法报告路径")
    results = d / "allure-results"
    if not results.is_dir():
        raise HTTPException(status_code=404, detail="allure-results 不存在，无法提供明细")
    return results


@router.get("/{run_id}/cases", summary="批次用例结果摘要（平台原生报告页，已掩码）")
def get_run_cases(run_id: str):
    return {"run_id": run_id, **allure_store.list_cases(_results_dir_or_404(run_id))}


@router.get("/{run_id}/cases/{case_id}", summary="单用例请求/响应明细（已掩码+截断）")
def get_run_case(run_id: str, case_id: str):
    detail = allure_store.case_detail(_results_dir_or_404(run_id), case_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"批次 {run_id} 中不存在用例 {case_id}")
    return detail
