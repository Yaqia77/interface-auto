"""interface-auto 平台后端入口（FastAPI）。

启动（项目根目录）:
    .venv/Scripts/python.exe -m uvicorn backend.main:app --reload --port 8000
接口文档:
    http://127.0.0.1:8000/docs  （Swagger UI，前端联调/评审用）
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend import authz, config_writer, scheduler, user_store
from backend.routers import auth, cases, dependencies, notifications, plans, runs, schedules, secrets
from backend.schemas import EnvsUpdate, HealthOut
from core.context import load_config

ROOT = Path(__file__).resolve().parent.parent

app = FastAPI(
    title="interface-auto 测试平台 API",
    version="0.1.0",
    description="Excel 驱动接口自动化框架的平台化后端：用例查询 / 执行调度 / 批次跟踪。",
)

# 开发期放开跨域；生产部署（Nginx 同域反代）后可收紧
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(cases.router)
app.include_router(dependencies.router)
app.include_router(notifications.router)
app.include_router(plans.router)
app.include_router(runs.router)
app.include_router(schedules.router)
app.include_router(secrets.router)


@app.middleware("http")
async def auth_middleware(request, call_next):
    """全局认证：/api/* 默认需登录态，白名单（登录/健康/报告 HTML/文档）除外。

    权限细粒度由各接口 Depends(require_perm(...)) 二次校验，安全边界始终在后端。
    """
    path = request.url.path
    # CORS 预检交给 CORS 中间件；非 /api 路径（静态/文档）放行
    if request.method == "OPTIONS" or not path.startswith("/api/") or authz.is_exempt(path):
        return await call_next(request)
    token = authz.extract_token(request)
    username = authz.username_of(token) if token else None
    user = user_store.get_user(username) if username else None
    if user is None or not user.get("enabled", True):
        return JSONResponse(status_code=401, content={"detail": "未登录或登录已过期"})
    request.state.user = user
    return await call_next(request)


@app.on_event("startup")
def _bootstrap():
    """服务启动：播种默认用户 + 拉起 Cron 调度线程。"""
    user_store.bootstrap()
    scheduler.start()


@app.get("/api/health", response_model=HealthOut, tags=["系统"], summary="健康检查")
def health():
    cfg = load_config()
    return HealthOut(
        status="ok",
        default_env=cfg.get("default_env"),
        cases_file_exists=(ROOT / "data" / "api_cases.xlsx").exists(),
    )


@app.get("/api/envs", tags=["系统"], summary="环境列表与配置详情（前端下拉/环境页）")
def envs():
    cfg = load_config()
    env_items = []
    for name, section in (cfg.get("env") or {}).items():
        section = section or {}
        env_items.append({
            "name": name,
            "base_url": section.get("base_url"),
            "timeout": section.get("timeout"),
            "verify_ssl": section.get("verify_ssl", True),
            # default_headers 来自 config.yaml（开发者可控），值为变量引用或静态头，无明文凭证
            "default_headers": section.get("default_headers") or {},
        })
    return {
        "default_env": cfg.get("default_env"),
        "envs": env_items,
        "secret_vars_file": cfg.get("secret_vars_file"),
        "report": cfg.get("report") or {},
        "log": cfg.get("log") or {},
    }


_CONFIG_ERROR_STATUS = {"invalid": 400, "not_found": 404, "locked": 409}


@app.put("/api/envs", tags=["系统"], summary="保存环境配置（写回 config.yaml 并即时生效）")
def update_envs(payload: EnvsUpdate):
    """整体覆盖式写回环境段：行级替换保留注释/其余章节，校验通过才落盘。

    load_config 无缓存，写回后下一次执行/拉取即读到新配置，无需重启。
    """
    try:
        config_writer.save_envs(
            payload.default_env,
            [e.model_dump() for e in payload.envs],
        )
    except config_writer.ConfigWriteError as e:
        raise HTTPException(status_code=_CONFIG_ERROR_STATUS.get(e.kind, 400), detail=str(e))
    return envs()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
