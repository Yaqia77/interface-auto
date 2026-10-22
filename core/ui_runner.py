# -*- coding: utf-8 -*-
"""UI 用例执行器：Playwright sync API 的步骤解释器。

设计：与接口链路（core.runner）分轨，但同为"给定用例数据 + 变量池 → 逐步执行 → 结果对象"。
本模块不依赖 allure / pytest，报告增强通过注入的回调完成（step=上下文管理器工厂、
attach=(name, png_bytes) 落图），由 tests/test_ui.py 负责胶水，保持 core 纯净、可单测。

动作集与定位器前缀口径与 backend.ui_case_store.ACTIONS / _LOCATOR_PREFIXES 一致（二者是唯二消费方）。
"""
from __future__ import annotations

import time
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from loguru import logger

from .variable import render

# 步骤默认操作超时（毫秒）：定位/断言等待上限，环境慢时可在用例层调整（v1 固定）
_DEFAULT_TIMEOUT_MS = 8000

# 截图默认落盘目录（无 allure 钩子的独立/CLI 运行也会写图到此；reports 已 gitignore）
DEFAULT_OUTPUT_DIR = Path("reports") / "ui_screenshots"


@dataclass
class UiRunResult:
    case_id: str
    ok: bool = False
    error: Optional[str] = None
    steps: list[dict] = field(default_factory=list)   # 步骤轨迹（含 action/locator/ok/耗时/截图名）
    duration: float = 0.0
    extracted: dict = field(default_factory=dict)      # 本条用例提取到的变量（已写入 ctx）


class UiRunnerError(Exception):
    """浏览器/动作层的可恢复错误，统一转成用例失败而非崩溃。"""


def _resolve_locator(page, locator: str):
    """把平台定位器语法解析为 Playwright Locator。

    前缀：css=（裸选择器缺省即按 css）/ xpath= / text= 直接交给 page.locator（Playwright
    原生理解这三类 engine）；role=button,name=登录 解析为 get_by_role。
    """
    if not locator:
        raise UiRunnerError("该动作需要定位器，但定位为空")
    if locator.startswith("role="):
        body = locator[len("role="):]
        parts = [p for p in body.split(",")]
        role = parts[0].strip()
        kwargs = {}
        for kv in parts[1:]:
            if "=" in kv:
                k, v = kv.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k == "name":
                    kwargs["name"] = v
                elif k in ("exact",):
                    kwargs["exact"] = v.lower() == "true"
        return page.get_by_role(role, **kwargs)
    # css= 去掉前缀（css 是默认引擎）；xpath= / text= 保留原样交给 locator()
    if locator.startswith("css="):
        return page.locator(locator[len("css="):])
    return page.locator(locator)


def _join_url(value: str, base_url: str) -> str:
    value = (value or "").strip()
    if "://" in value:  # 已带协议（http/https/file 等）视为绝对地址
        return value
    base = (base_url or "").rstrip("/")
    if not base:
        raise UiRunnerError(f"相对地址 {value!r} 需要在 config.yaml 中配置环境 base_url")
    return f"{base}/{value.lstrip('/')}"


def _expect(cond: bool, message: str) -> None:
    if not cond:
        raise UiRunnerError(message)


# Playwright 自带内核未下载时的报错特征（据此触发本机 Chrome 回退）
_MISSING_KERNEL_HINTS = (
    "executable doesn't exist", "please run the following command",
    "playwright install", "host executables", "browserbridge",
)


def _looks_missing_kernel(msg: str) -> bool:
    low = (msg or "").lower()
    return any(h in low for h in _MISSING_KERNEL_HINTS)


class UiRunner:
    """一条 UI 用例的执行器：开浏览器 → 逐步执行 → 提取变量 → 关浏览器。

    run() 不抛异常：任何步骤失败即截全屏、中断后续步骤，把结果写进 UiRunResult。
    """

    def __init__(self, ctx, base_url: str, attach: Optional[Callable[[str, bytes], None]] = None,
                 step: Optional[Callable[[str], "object"]] = None,
                 output_dir: Optional[Path] = DEFAULT_OUTPUT_DIR):
        self.ctx = ctx
        self.base_url = base_url
        self._attach = attach
        self._step = step
        self.output_dir = output_dir

    def _step_cm(self, label: str):
        return self._step(label) if self._step else nullcontext()

    def run(self, case: dict) -> UiRunResult:
        from playwright.sync_api import sync_playwright

        result = UiRunResult(case_id=case.get("case_id", ""), ok=False)
        browser_name = (case.get("browser") or "chromium").lower()
        headless = bool(case.get("headless", True))
        start = time.perf_counter()
        pw = None
        browser = None
        page = None
        try:
            pw = sync_playwright().start()
            browser = self._launch(pw, browser_name, headless)
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(_DEFAULT_TIMEOUT_MS)
            self.page = page
            self._context = context

            steps = case.get("steps") or []
            for i, step in enumerate(steps, 1):
                result.steps.append(self._run_step(page, step, i))
                if result.steps[-1]["ok"] is False:
                    # 失败即截全屏并中断后续步骤
                    self._capture(page, result.steps[-1], f"步骤{i}失败")
                    break

            # 变量提取（仅在未失败时进行）
            if all(s["ok"] for s in result.steps):
                self._extract(page, case.get("extract") or [], result)

            result.ok = all(s["ok"] for s in result.steps)
            if not result.ok:
                bad = next(s for s in result.steps if not s["ok"])
                result.error = bad.get("error") or f"步骤 {bad['index']}（{bad.get('action')}）失败"
        except UiRunnerError as e:
            result.error = str(e)
            logger.error("[{}] UI 执行错误: {}", case.get("case_id"), e)
        except Exception as e:  # noqa: BLE001 浏览器/动作异常兜底为用例失败
            result.error = f"UI 执行异常: {type(e).__name__}: {e}"
            if page is not None:
                self._capture(page, (result.steps[-1] if result.steps else {}), "异常现场")
            logger.error("[{}] UI 执行异常: {}", case.get("case_id"), e)
        finally:
            for closer in (lambda: page and page.close(),
                           lambda: browser and browser.close(),
                           lambda: pw and pw.stop()):
                try:
                    closer()
                except Exception:  # noqa: BLE001
                    pass
            result.duration = time.perf_counter() - start
        return result

    @staticmethod
    def _launch(pw, name: str, headless: bool = True):
        launcher = getattr(pw, name, None)
        if launcher is None:
            raise UiRunnerError(f"不支持的浏览器: {name}（可用 chromium/firefox/webkit）")
        try:
            return launcher.launch(headless=headless)
        except Exception as e:  # noqa: BLE001 内核缺失时走兼容回退
            msg = str(e)
            if name == "chromium" and _looks_missing_kernel(msg):
                # 自带 chromium 未下载 → 自动回退到本机已装的 Google Chrome（channel），
                # 直接复用用户正式版本（如 156.0.8078.48），无需联网下载 Playwright 内核
                return UiRunner._launch_local_chrome(launcher, headless, cause=e)
            if _looks_missing_kernel(msg):
                raise UiRunnerError(f"浏览器内核缺失，请先执行 `python -m playwright install {name}`：{msg}") from e
            raise

    @staticmethod
    def _launch_local_chrome(launcher, headless: bool, cause: Exception):
        """回退：依次尝试本机 chrome / chrome-beta，命中即返回；都不可用给出中文指引。"""
        tried: list[str] = []
        for channel in ("chrome", "chrome-beta"):
            try:
                browser = launcher.launch(headless=headless, channel=channel)
                logger.info("未找到 Playwright 自带 Chromium，已回退到本机 Google Chrome（channel={}, version={}）",
                            channel, browser.version)
                return browser
            except Exception as ce:  # noqa: BLE001
                tried.append(f"{channel}: {(str(ce).splitlines() or [''])[0]}")
        raise UiRunnerError(
            "Playwright 自带 Chromium 未安装，且本机未检测到可复用的 Google Chrome。\n"
            "  方式一（推荐，无需下载）：安装/保留本机 Google Chrome，本平台会自动复用；\n"
            "  方式二：执行 `python -m playwright install chromium` 下载自带内核。\n"
            f"  回退尝试：{' ｜ '.join(tried)}"
        ) from cause

    # ---------- 单步 ----------

    def _run_step(self, page, step: dict, index: int) -> dict:
        action = step.get("action")
        raw_locator = step.get("locator")
        raw_value = step.get("value")
        label = f"{index}. {action}"
        if step.get("desc"):
            label += f" · {step['desc']}"
        entry = {"index": index, "action": action, "action_desc": _action_desc(action),
                 "locator": raw_locator, "value": _stringify(raw_value),
                 "desc": step.get("desc") or "", "ok": False, "duration_ms": 0,
                 "error": None, "screenshot": None}
        t0 = time.perf_counter()
        try:
            with self._step_cm(label):
                # 变量替换只作用于取值与地址类定位（定位器一般静态）
                value = render(raw_value, self.ctx) if isinstance(raw_value, str) else raw_value
                locator = _resolve_locator(page, raw_locator) if raw_locator else None
                self._dispatch(page, locator, action, value, entry)
                entry["ok"] = True
        except Exception as e:  # noqa: BLE001 单步失败：记录 + 截图，不炸整条
            entry["error"] = f"{type(e).__name__}: {str(e).splitlines()[0] if str(e) else e}"[:400]
            logger.warning("[步骤失败] {} -> {}", label, entry["error"])
        finally:
            entry["duration_ms"] = int((time.perf_counter() - t0) * 1000)
        return entry

    def _dispatch(self, page, locator, action: str, value, entry: dict) -> None:
        if action == "goto":
            page.goto(_join_url(str(value), self.base_url))
        elif action == "click":
            locator.click()
        elif action == "fill":
            locator.fill("" if value is None else str(value))
        elif action == "press":
            locator.press(str(value))
        elif action == "select":
            locator.select_option(label=str(value))
        elif action == "check":
            locator.check()
        elif action == "hover":
            locator.hover()
        elif action == "wait_for":
            locator.wait_for(state="visible")
        elif action == "screenshot":
            # 显式截图：有定位器截元素，否则截整页；结果记入当前步骤轨迹
            self._capture(page, entry, "手动", locator=locator)
        elif action == "expect_visible":
            _expect(locator.is_visible(), "元素不可见")
        elif action == "expect_text":
            txt = locator.inner_text()
            _expect(str(value) in txt, f"文本不含期望值：期望包含 {value!r}，实际 {txt!r}")
        elif action == "expect_url":
            _expect(str(value) in page.url, f"当前地址 {page.url!r} 不含期望 {value!r}")
        else:
            raise UiRunnerError(f"未知动作: {action}")

    # ---------- 变量提取 ----------

    def _extract(self, page, extract: list, result: UiRunResult) -> None:
        for item in extract:
            var = item.get("var")
            source = item.get("source", "")
            value = self._read_source(page, source)
            if value is not None:
                self.ctx.set(var, value)
                result.extracted[var] = value
                logger.info("[{}] 变量提取 {}={}", result.case_id, var, value)

    def _read_source(self, page, source: str):
        """source 语法：text|<locator> / input_value|<locator> / cookie:<name> / url。"""
        source = (source or "").strip()
        if source == "url":
            return page.url
        if source.startswith("cookie:"):
            name = source[len("cookie:"):].strip()
            for ck in page.context.cookies():
                if ck.get("name") == name:
                    return ck.get("value")
            return None
        if "|" in source:
            kind, _, loc = source.partition("|")
            locator = _resolve_locator(page, loc.strip())
            kind = kind.strip()
            if kind == "text":
                return locator.inner_text()
            if kind == "input_value":
                return locator.input_value()
            if kind == "attr":
                # attr|css=#x:data-id 形式取属性
                sel, _, attr = loc.partition(":")
                return locator.get_attribute(attr.strip()) if attr else None
            raise UiRunnerError(f"未知提取来源类型: {kind}")
        raise UiRunnerError(f"变量提取 source 格式非法: {source!r}")

    # ---------- 截图 ----------

    def _capture(self, page, entry: dict, name_suffix: str, locator=None) -> None:
        """截当前步现场：默认落盘 output_dir；有 allure 钩子则同时作为附件写入。

        任一途径成功即把截图名记入步骤轨迹（供报告页回指）；截图失败不影响执行结论。
        """
        if entry is None:
            return
        try:
            target = locator if locator is not None else page
            png = target.screenshot(full_page=(locator is None))
            att_name = f"截图-{name_suffix}-{entry.get('index', 0)}.png"
            saved = False
            if self.output_dir is not None:
                try:
                    self.output_dir.mkdir(parents=True, exist_ok=True)
                    (self.output_dir / att_name).write_bytes(png)
                    saved = True
                except Exception as de:  # noqa: BLE001
                    logger.warning("截图落盘失败: {}", de)
            if self._attach is not None:
                try:
                    self._attach(att_name, png)
                    saved = True
                except Exception as ae:  # noqa: BLE001
                    logger.warning("截图附件写入失败: {}", ae)
            if saved:
                entry["screenshot"] = att_name
        except Exception as e:  # noqa: BLE001 截图失败不影响失败结论
            logger.warning("截图失败: {}", e)


def _stringify(v) -> str:
    if v is None:
        return ""
    return v if isinstance(v, str) else str(v)


_DESC_CACHE: dict[str, str] = {}


def _action_desc(action: str) -> str:
    if not _DESC_CACHE:
        try:
            from backend.ui_case_store import ACTIONS  # 单一口径来源
            _DESC_CACHE.update({a: m["desc"] for a, m in ACTIONS.items()})
        except Exception:  # noqa: BLE001 core 不应强依赖 backend，降级用动作名
            pass
    return _DESC_CACHE.get(action, action)
