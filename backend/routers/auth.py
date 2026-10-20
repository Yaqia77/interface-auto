"""认证与用户管理接口：登录/登出/当前用户 + 用户 CRUD（仅 admin）。"""
from fastapi import APIRouter, Depends, HTTPException, Request

from backend import authz, user_store
from backend.schemas import LoginRequest, LoginResponse, UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/api/auth", tags=["用户与权限"])


def _public(user: dict, with_perms: bool = False) -> UserOut:
    """脱敏输出：绝不带出密码哈希。"""
    data = {
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
        "role_name": user_store.ROLE_NAMES.get(user["role"], user["role"]),
        "enabled": user.get("enabled", True),
        "created_at": user.get("created_at"),
        "updated_at": user.get("updated_at"),
    }
    if with_perms:
        data["permissions"] = authz.permissions_of(user["role"])
    return UserOut(**data)


@router.post("/login", response_model=LoginResponse, summary="登录（用户名+密码）")
def login(body: LoginRequest):
    user = user_store.get_user(body.username.strip())
    if user is None or not user_store.verify_password(body.password, user["password"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.get("enabled", True):
        raise HTTPException(status_code=403, detail="账号已停用，请联系管理员")
    token = authz.issue_token(user["username"])
    return LoginResponse(
        token=token,
        user=_public(user, with_perms=True),
    )


@router.post("/logout", summary="登出（吊销当前 token）")
def logout(request: Request):
    authz.revoke_token(authz.extract_token(request))
    return {"ok": True}


@router.get("/me", response_model=UserOut, summary="当前登录用户（含权限码列表）")
def me(user: dict = Depends(authz.get_current_user)):
    return _public(user, with_perms=True)


# ---------- 用户管理（仅 admin） ----------

@router.get("/users", response_model=list[UserOut], summary="用户列表")
def list_users(_: dict = Depends(authz.require_perm("user:manage"))):
    return [_public(u) for u in user_store.list_users()]


@router.post("/users", response_model=UserOut, status_code=201, summary="新建用户")
def create_user(body: UserCreate, _: dict = Depends(authz.require_perm("user:manage"))):
    try:
        user = user_store.create_user(
            username=body.username.strip(), password=body.password,
            display_name=body.display_name.strip(), role=body.role,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _public(user)


@router.put("/users/{username}", response_model=UserOut, summary="更新用户（资料/角色/启停/重置密码）")
def update_user(username: str, body: UserUpdate, actor: dict = Depends(authz.require_perm("user:manage"))):
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="未传任何需要修改的字段")
    # 防呆：admin 不能把自己降级/停用，避免锁死系统
    if username == actor["username"] and ("role" in fields or fields.get("enabled") is False):
        raise HTTPException(status_code=400, detail="不能修改自己的角色或停用自己")
    try:
        user = user_store.update_user(username, **fields)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if user is None:
        raise HTTPException(status_code=404, detail=f"用户不存在: {username}")
    return _public(user)


@router.delete("/users/{username}", summary="删除用户")
def delete_user(username: str, actor: dict = Depends(authz.require_perm("user:manage"))):
    if username == actor["username"]:
        raise HTTPException(status_code=400, detail="不能删除自己")
    if username == "admin":
        raise HTTPException(status_code=400, detail="内置 admin 账号不可删除")
    if not user_store.delete_user(username):
        raise HTTPException(status_code=404, detail=f"用户不存在: {username}")
    return {"ok": True}
