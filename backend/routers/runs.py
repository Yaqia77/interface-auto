"""执行批次接口：以子进程调用 main.py（零改写复用 pytest+报告编排），后台线程收集日志。"""
import os
import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

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
