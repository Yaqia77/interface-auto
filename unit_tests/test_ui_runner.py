# -*- coding: utf-8 -*-
"""core.ui_runner 动作解释器功能测试：对本地 fixture 页跑通全部 12 动作 + 变量提取。

零外部依赖（本地 http 服务 fixture 页，以便验证 cookie 提取）。若浏览器未就绪则整体 skip，不阻断无 UI 环境下的回归。
    .venv/Scripts/python.exe -m pytest unit_tests/test_ui_runner.py -v
"""
import functools
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.context import Context  # noqa: E402
from core.ui_runner import UiRunner  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


class _QuietHandler(SimpleHTTPRequestHandler):
    """服务 fixture 静态页并静音访问日志。"""

    def log_message(self, *args):  # noqa: D102
        pass


def _chromium_ready() -> bool:
    """与 ui_runner 同口径：先试自带 chromium，再回退本机 Google Chrome。"""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            try:
                b = pw.chromium.launch(headless=True)
            except Exception:  # noqa: BLE001
                b = pw.chromium.launch(headless=True, channel="chrome")
            b.close()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="module")
def base_url():
    if not _chromium_ready():
        pytest.skip("浏览器未就绪（自带 chromium 与本机 Chrome 均不可用），跳过 UI 执行器测试")
    # 以 http 方式提供 fixture 页：浏览器对 file:// 不落地 cookie，需 http 才能验证 cookie: 提取
    handler = functools.partial(_QuietHandler, directory=str(FIXTURES.resolve()))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


def _steps(*s):
    return list(s)


def _run(ctx, base_url, steps, extract=None):
    case = {"case_id": "t", "browser": "chromium", "headless": True,
            "steps": steps, "extract": extract or []}
    runner = UiRunner(ctx, base_url)
    return runner.run(case)


def test_full_flow_all_actions(base_url):
    ctx = Context({"username": "qa77"}, {})
    result = _run(ctx, base_url, _steps(
        {"action": "goto", "value": "ui_demo.html"},
        {"action": "expect_visible", "locator": "css=#title"},
        {"action": "fill", "locator": "css=#username", "value": "{{username}}"},
        {"action": "fill", "locator": "css=#password", "value": "s3cret"},
        {"action": "press", "locator": "css=#password", "value": "Tab"},
        {"action": "select", "locator": "css=#role", "value": "测试"},
        {"action": "check", "locator": "css=#agree"},
        {"action": "hover", "locator": "css=#submit"},
        {"action": "click", "locator": "css=#submit"},
        {"action": "wait_for", "locator": "css=.welcome"},
        {"action": "expect_text", "locator": "css=.welcome", "value": "欢迎"},
        {"action": "expect_text", "locator": "css=#who", "value": "qa77"},
        {"action": "expect_url", "value": "?logged_in=1"},
        {"action": "screenshot"},
    ), extract=[
        {"var": "who_val", "source": "text|css=#who"},
        {"var": "uname", "source": "input_value|css=#username"},
        {"var": "sess", "source": "cookie:session_token"},
        {"var": "page_url", "source": "url"},
    ])
    assert result.ok, result.error
    assert all(s["ok"] for s in result.steps)
    assert len(result.steps) == 14
    # 变量提取写入池并可在后续引用
    assert ctx.get("who_val") == "qa77"
    assert ctx.get("uname") == "qa77"
    assert ctx.get("sess") == "abc123"
    assert "?logged_in=1" in ctx.get("page_url")
    # screenshot 步骤留了截图名
    assert result.steps[-1]["screenshot"]


def test_failure_stops_and_marks_error(base_url):
    ctx = Context({}, {})
    result = _run(ctx, base_url, _steps(
        {"action": "goto", "value": "ui_demo.html"},
        {"action": "expect_text", "locator": "css=#title", "value": "绝不存在的文本"},
        {"action": "click", "locator": "css=#submit"},  # 不该被执行（已中断）
    ))
    assert result.ok is False
    assert "期望" in (result.error or "") or "不含" in (result.error or "")
    assert len(result.steps) == 2  # 第二步失败即中断，第三步未记录
    assert result.steps[1]["ok"] is False
    assert result.steps[1]["screenshot"]  # 失败步骤有现场截图


def test_relative_url_requires_base(base_url):
    ctx = Context({}, {})
    r = UiRunner(ctx, "")  # 无 base_url
    res = r.run({"case_id": "t", "steps": [{"action": "goto", "value": "/login"}]})
    assert res.ok is False
    assert "base_url" in (res.error or "")
