"""interface-auto 平台后端入口（FastAPI）。

启动（项目根目录）:
    .venv/Scripts/python.exe -m uvicorn backend.main:app --reload --port 8000
接口文档:
    http://127.0.0.1:8000/docs  （Swagger UI，前端联调/评审用）
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import cases, runs
from backend.schemas import HealthOut
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

app.include_router(cases.router)
app.include_router(runs.router)


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
