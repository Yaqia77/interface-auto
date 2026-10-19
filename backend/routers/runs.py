"""执行批次接口：以子进程调用 main.py（零改写复用 pytest+报告编排），后台线程收集日志。"""
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

from backend.schemas import RunCreate, RunOut

ROOT = Path(__file__).resolve().parents[2]  # 项目根（backend/routers/ 上溯两级）

router = APIRouter(prefix="/api/runs", tags=["执行中心"])

# 内存态登记表：run_id -> 记录。重启即失，历史批次由 reports/ 目录扫描兜底。
_runs: dict[str, dict] = {}
_LOCK = threading.Lock()

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

    run_id = f"api_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    rec = {
        "run_id": run_id, "status": "running", "proc": None, "log": [],
        "args": body.model_dump(exclude_none=True), "started_at": _now(),
        "finished_at": None, "exit_code": None, "report_dir": None,
    }
    with _LOCK:
        _runs[run_id] = rec
    threading.Thread(target=_worker, args=(run_id, cmd), daemon=True).start()
    return _to_out(rec)


@router.get("", response_model=list[RunOut], summary="批次列表（API 发起 + reports/ 历史）")
def list_runs(limit: int = 20):
    items: list[RunOut] = [_to_out(r) for r in _runs.values()]

    # 扫描本地 CLI 历史运行目录，补全（status=unknown，source=cli）
    reports = ROOT / "reports"
    known = {r["report_dir"] for r in _runs.values() if r["report_dir"]}
    if reports.is_dir():
        for d in sorted(reports.glob("run_*"), reverse=True):
            rel = _rel(str(d))
            if rel in known:
                continue
            ts = d.name.replace("run_", "").replace("_", " ")
            items.append(RunOut(run_id=rel, status="unknown", source="cli",
                                started_at=ts, report_dir=rel))
            if len(items) >= limit:
                break

    items.sort(key=lambda x: (x.started_at or ""), reverse=True)
    return items[:limit]


@router.get("/{run_id}", response_model=RunOut, summary="批次详情（含日志尾部）")
def get_run(run_id: str):
    rec = _runs.get(run_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"批次不存在或已随服务重启丢失: {run_id}")
    return _to_out(rec, log_tail=100)


@router.get("/{run_id}/log", summary="批次完整日志（纯文本，供实时轮询）")
def get_log(run_id: str):
    rec = _runs.get(run_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"批次不存在: {run_id}")
    return {"run_id": run_id, "status": _status_from(rec),
            "lines": len(rec["log"]), "log": "\n".join(rec["log"])}


# 历史批次 id 形式：run_YYYYMMDD_HHMMSS 或 reports/run_YYYYMMDD_HHMMSS（列表接口返回的 cli 条目）
_CLI_RUN_RE = re.compile(r"^(?:reports[/\\])?run_\d{8}_\d{6}$")


def _resolve_report_dir(run_id: str) -> str | None:
    """run_id -> 报告目录（相对项目根）。内存优先，其次认领 reports/ 历史目录。"""
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
