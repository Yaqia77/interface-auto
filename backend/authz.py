"""认证与鉴权（RBAC 骨架，对应设计文档第二章角色权限矩阵）。

- Token：登录成功后签发随机串，内存登记表维护（服务重启需重新登录，MVP 可接受）。
- 权限：角色 -> 权限码集合；接口用 Depends(require_perm("xxx")) 做后端二次校验，
  前端 v-perm 只做按钮显隐，安全边界始终在后端。
"""
import secrets
import threading
from typing import Callable

from fastapi import Depends, HTTPException, Request

# 权限码目录（粒度对齐设计文档「菜单级→按钮级→数据级」中的按钮/操作级）
PERMISSIONS = {
    "case:write":     {"admin", "tl", "qa"},              # 用例新增/编辑/导入
    "case:delete":    {"admin", "tl"},                    # 用例删除（设计文档：删除需 TL+）
    "secret:manage":  {"admin", "tl"},                    # 凭证增删改
    "env:manage":     {"admin", "tl"},                    # 环境配置写回
    "run:create":     {"admin", "tl", "qa", "dev"},       # 触发执行（Viewer 不可）
    "plan:manage":    {"admin", "tl", "qa"},              # 测试场景 CRUD
    "schedule:manage": {"admin", "tl"},                   # 定时任务
    "webhook:manage": {"admin", "tl"},                    # 通知配置
    "report:delete":  {"admin", "tl"},                    # 报告删除/清理
    "user:manage":    {"admin"},                          # 用户管理（系统管理）
    "audit:view":     {"admin", "tl"},                    # 操作审计查询/导出（TL 系统管理只读）
    "audit:manage":   {"admin"},                          # 审计日志清理
}

# 只读角色兜底：viewer/dev 不持有任何写权限码，天然仅 GET

# token -> username（内存态；服务重启即失效）
_TOKENS: dict[str, str] = {}
_TOKEN_LOCK = threading.Lock()


def issue_token(username: str) -> str:
    token = secrets.token_urlsafe(32)
    with _TOKEN_LOCK:
        _TOKENS[token] = username
    return token


def revoke_token(token: str) -> None:
    with _TOKEN_LOCK:
        _TOKENS.pop(token, None)


def username_of(token: str) -> str | None:
    with _TOKEN_LOCK:
        return _TOKENS.get(token)


def permissions_of(role: str) -> list[str]:
    return sorted(code for code, roles in PERMISSIONS.items() if role in roles)


def extract_token(request: Request) -> str:
    """从 Authorization: Bearer 头取 token；iframe 场景兜底支持 ?token= 查询参数。"""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.query_params.get("token", "")


# 免认证白名单：健康检查、登录、文档、报告 HTML（iframe/新标签直接加载）
EXEMPT_EXACT = {"/api/health", "/api/auth/login", "/docs", "/openapi.json", "/redoc"}


def is_exempt(path: str) -> bool:
    if path in EXEMPT_EXACT:
        return True
    # /api/runs/{id}/report 是浏览器 iframe 资源，无法带自定义头：放行
    # （仅只读 HTML，明细 JSON 接口仍需鉴权）
    if path.endswith("/report") and path.startswith("/api/runs/"):
        return True
    return False


def get_current_user(request: Request) -> dict:
    """FastAPI 依赖：读取中间件写入 request.state.user，未登录 401。"""
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return user


def require_perm(code: str) -> Callable:
    """工厂依赖：要求当前用户持有权限码，否则 403。"""
    def _dep(user: dict = Depends(get_current_user)) -> dict:
        if code not in permissions_of(user.get("role", "")):
            raise HTTPException(status_code=403, detail=f"无权限: {code}（角色 {user.get('role')} 不允许）")
        return user
    return _dep
