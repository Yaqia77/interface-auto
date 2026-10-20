# -*- coding: utf-8 -*-
"""平台认证与权限冒烟测试（RBAC 全链路回归）。

用法：先启动后端，再执行本脚本
    python -m uvicorn backend.main:app --port 8000
    python tools/smoke_authz.py                  # 默认打 127.0.0.1:8000
    set IA_BASE=http://127.0.0.1:8899 && python tools/smoke_authz.py

覆盖：登录/登出、未登录 401、越权 403、报告删除与保留策略清理、路径穿越护栏、用户 CRUD、操作审计留痕。
脚本只在 reports/ 下造一个 1970 年的假批次并删除它，不触碰任何真实报告，可重复执行。
"""
import json
import os
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = os.environ.get("IA_BASE", "http://127.0.0.1:8000").rstrip("/")
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PASS = {"admin": "admin123", "tl": "tl123", "qa": "qa123", "viewer": "viewer123"}

# 用 cli 目录形式造一个干净的假批次（不污染 runs_history，只被 list_runs 的目录认领分支扫到）
FAKE_ID = "run_19700101_000000"
FAKE_DIR = ROOT / "reports" / FAKE_ID
FAKE_REL = f"reports\\{FAKE_ID}"      # list_runs 在 Windows 下返回反斜杠相对路径
TRAVERSAL = "reports" + chr(92) + ".." + chr(92) + "config"   # 路径穿越样本

_passed = _failed = 0


def check(name, cond, extra=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  [OK] {name}")
    else:
        _failed += 1
        print(f"  [FAIL] {name} {extra}")


def req(method, path, body=None, token=None):
    """极简 HTTP 客户端（只用标准库，避免给后端测试拉额外依赖）。"""
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw or "{}")
        except json.JSONDecodeError:
            return e.code, {"raw": raw[:200]}
    except urllib.error.URLError as e:
        print(f"后端不可达：{BASE}（{e.reason}）", file=sys.stderr)
        sys.exit(2)


def login(username, password):
    code, resp = req("POST", "/api/auth/login", {"username": username, "password": password})
    assert code == 200, f"登录失败 {username}: {code} {resp}"
    return resp["token"], resp["user"]


def req_text(method, path, token=None):
    """取文本响应（CSV 导出类接口）。"""
    r = urllib.request.Request(BASE + path, method=method)
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, resp.read().decode("utf-8-sig", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def main():
    if not FAKE_DIR.parent.is_dir():
        print("reports/ 不存在，后端可能未初始化", file=sys.stderr)
        return 2
    shutil.rmtree(FAKE_DIR, ignore_errors=True)
    (FAKE_DIR / "allure-results").mkdir(parents=True)
    (FAKE_DIR / "report.html").write_text("fake", encoding="utf-8")

    print(f"目标：{BASE}")
    print("== 1. 认证边界 ==")
    code, _ = req("GET", "/api/health")
    check("免登录白名单 /api/health 可访问", code == 200, code)
    code, resp = req("GET", "/api/runs")
    check("未登录访问业务接口 401", code == 401, f"{code} {resp}")
    code, resp = req("GET", "/api/runs", token="bogus-token")
    check("非法 token 401", code == 401, f"{code} {resp}")
    code, resp = req("POST", "/api/auth/login", {"username": "admin", "password": "wrong-pass"})
    check("错误密码 401", code == 401, f"{code} {resp}")

    print("== 2. 登录与权限矩阵 ==")
    _, viewer_user = login("viewer", DEFAULT_PASS["viewer"])
    check("viewer 权限集为空", viewer_user["permissions"] == [], viewer_user["permissions"])
    check("角色名中文回显", viewer_user["role_name"] == "只读访客", viewer_user["role_name"])
    admin_token, admin_user = login("admin", DEFAULT_PASS["admin"])
    check("admin 权限全量（含用户/审计管理）",
          {"user:manage", "report:delete", "audit:view", "audit:manage"} <= set(admin_user["permissions"]),
          admin_user["permissions"])
    # 预清理：上一轮冒烟可能残留测试账号，保证脚本可重复执行
    req("DELETE", "/api/auth/users/smoke_qa", token=admin_token)
    tl_token, tl_user = login("tl", DEFAULT_PASS["tl"])
    check("tl 可删报告", "report:delete" in tl_user["permissions"], tl_user["permissions"])
    check("tl 不可管用户", "user:manage" not in tl_user["permissions"], tl_user["permissions"])
    qa_token, qa_user = login("qa", DEFAULT_PASS["qa"])
    check("qa 不可删报告", "report:delete" not in qa_user["permissions"], qa_user["permissions"])
    vt = login("viewer", DEFAULT_PASS["viewer"])[0]
    code, resp = req("GET", "/api/runs", token=vt)
    check("viewer 可只读批次列表", code == 200 and isinstance(resp, list), f"{code} {resp}")
    code, resp = req("DELETE", "/api/runs/" + urllib.parse.quote(FAKE_REL, safe=""), token=vt)
    check("viewer 删报告被拒 403", code == 403, f"{code} {resp}")
    code, resp = req("POST", "/api/runs/cleanup?keep=9999", token=vt)
    check("viewer 清理旧报告被拒 403", code == 403, f"{code} {resp}")
    code, resp = req("GET", "/api/auth/users", token=qa_token)
    check("qa 查用户列表被拒 403", code == 403, f"{code} {resp}")

    print("== 3. 报告删除与保留策略 ==")
    code, resp = req("GET", "/api/runs?limit=1000", token=tl_token)
    check("tl 列表能看到播种的假批次", code == 200 and any(FAKE_ID in r["run_id"] for r in resp), code)
    code, resp = req("POST", "/api/runs/cleanup?keep=9999", token=tl_token)
    check("清理 keep 过大时不删任何批次", code == 200 and resp["deleted"] == 0, f"{code} {resp}")
    enc = urllib.parse.quote(FAKE_REL, safe="")
    code, resp = req("DELETE", f"/api/runs/{enc}", token=admin_token)
    check("admin 删 cli 批次成功", code == 200 and resp["deleted_report_dir"] == FAKE_REL, f"{code} {resp}")
    check("报告目录已物理删除", not FAKE_DIR.exists())
    code, resp = req("DELETE", f"/api/runs/{enc}", token=admin_token)
    check("重复删除返回 404", code == 404, f"{code} {resp}")
    code, resp = req("DELETE", "/api/runs/" + urllib.parse.quote(TRAVERSAL, safe=""), token=admin_token)
    check("路径穿越被拦截（非 200）", code != 200, f"{code} {resp}")
    check("config 目录未被误删", (ROOT / "config" / "config.yaml").exists())
    check("真实报告目录未被冒烟波及", len(list((ROOT / "reports").glob("run_20*"))) > 0)

    print("== 4. 用户 CRUD（仅 admin） ==")
    new_user = {"username": "smoke_qa", "password": "smoke123", "role": "qa"}
    code, resp = req("POST", "/api/auth/users", new_user, admin_token)
    check("admin 建用户", code == 201 and resp["role"] == "qa", f"{code} {resp}")
    code, resp = req("POST", "/api/auth/users", new_user, tl_token)
    check("tl 建用户被拒 403", code == 403, f"{code} {resp}")
    nu = login("smoke_qa", "smoke123")[1]
    check("新用户可登录", nu["username"] == "smoke_qa", nu)
    code, resp = req("PUT", "/api/auth/users/smoke_qa", {"enabled": False}, admin_token)
    check("admin 停用用户", code == 200 and resp["enabled"] is False, f"{code} {resp}")
    disabled_rejected = False
    try:
        login("smoke_qa", "smoke123")
    except AssertionError:
        disabled_rejected = True
    check("停用后禁止登录", disabled_rejected)
    code, resp = req("DELETE", "/api/auth/users/admin", token=admin_token)
    check("内置 admin 不可删", code == 400, f"{code} {resp}")
    code, resp = req("DELETE", "/api/auth/users/smoke_qa", token=admin_token)
    check("admin 删用户", code == 200, f"{code} {resp}")
    code, resp = req("POST", "/api/auth/logout", token=admin_token)
    check("登出接口可用", code == 200, f"{code} {resp}")
    code, resp = req("GET", "/api/auth/me", token=admin_token)
    check("登出后 token 失效 401", code == 401, f"{code} {resp}")

    # 后续审计用例需重新取一个有效 admin token
    admin_token, _ = login("admin", DEFAULT_PASS["admin"])

    print("== 5. 操作审计留痕 ==")
    code, resp = req("GET", "/api/audit/logs")
    check("未登录查审计 401", code == 401, f"{code} {resp}")
    code, resp = req("GET", "/api/audit/logs", token=vt)
    check("viewer 查审计被拒 403", code == 403, f"{code} {resp}")
    code, resp = req("GET", "/api/audit/logs", token=tl_token)
    check("tl 可查审计（系统管理只读粒度）", code == 200 and "items" in resp, f"{code} {resp}")

    # 造一条含敏感字段的写操作，验证留痕 + 脱敏
    code, resp = req("POST", "/api/auth/users",
                     {"username": "smoke_aud", "password": "TopSecret123", "role": "qa"}, admin_token)
    check("审计样本写操作成功", code == 201, f"{code} {resp}")
    code, resp = req("GET", "/api/audit/logs?keyword=smoke_aud&limit=50", token=admin_token)
    hits = resp.get("items", []) if code == 200 else []
    check("写操作已落审计", code == 200 and len(hits) >= 1, f"{code} {resp}")
    if hits:
        top = hits[0]
        check("审计动作名为可读中文", bool(top.get("action")) and top["action"] != "POST", top.get("action"))
        check("审计记录操作人与角色", top.get("username") == "admin" and top.get("role") == "admin", top)
        check("请求体已脱敏（明文密码不落盘）", "TopSecret123" not in json.dumps(top, ensure_ascii=False), top)
        check("脱敏后仍保留字段轮廓", "***" in (top.get("detail") or ""), top.get("detail"))
        print(f"       动作示例：{top.get('action')} | 对象：{top.get('target')} | 摘要：{top.get('detail')}")

    # 失败登录与越权尝试也必须留痕
    req("POST", "/api/auth/login", {"username": "admin", "password": "nope-not-right"})
    code, resp = req("GET", "/api/audit/logs?keyword=%E7%99%BB%E5%BD%95%E5%B0%9D%E8%AF%95&limit=20", token=admin_token)
    log_hits = resp.get("items", []) if code == 200 else []
    check("登录尝试已留痕", code == 200 and len(log_hits) >= 1, f"{code} {resp}")
    check("登录留痕不含明文密码",
          all("nope-not-right" not in json.dumps(h, ensure_ascii=False) for h in log_hits), log_hits[:1])

    code, resp = req("GET", "/api/audit/logs?only_failed=true&limit=50", token=admin_token)
    fails = resp.get("items", []) if code == 200 else []
    check("越权/未授权尝试作为失败留痕可筛", code == 200 and any(h.get("status") in (401, 403) for h in fails),
          f"{code} {[h.get('status') for h in fails][:8]}")

    code, resp = req("GET", "/api/audit/logs?username=admin&days=1&limit=20", token=admin_token)
    scoped = resp.get("items", []) if code == 200 else []
    check("按操作人 + 天数筛选生效",
          code == 200 and scoped and all(h["username"] == "admin" for h in scoped), f"{code} {len(scoped)}")

    code, body = req_text("GET", "/api/audit/export?token=" + admin_token)
    check("审计 CSV 可导出（?token= 鉴权）", code == 200 and body.startswith("时间"), f"{code} {body[:40]}")

    code, resp = req("DELETE", "/api/audit/logs?keep_days=0", token=tl_token)
    check("tl 清理审计被拒 403", code == 403, f"{code} {resp}")

    # 回收本轮自建账号：smoke_qa 已在第 4 节删除，此处只回收 smoke_aud
    code, resp = req("DELETE", "/api/auth/users/smoke_aud", token=admin_token)
    check("冒烟测试账号已回收", code == 200, f"{code} {resp}")

    # ---- 收尾：删除假批次目录（不碰任何真实报告） ----
    shutil.rmtree(FAKE_DIR, ignore_errors=True)
    print(f"\n结果：通过 {_passed} / 失败 {_failed}")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
