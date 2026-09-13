"""单用例执行编排 + 日志配置。"""
import json
import sys
from pathlib import Path

from loguru import logger

from .asserts import run_assertions
from .extractor import extract_variables
from .http_client import HttpExecutor, request_snapshot, response_snapshot
from .models import CaseResult, TestCase
from .variable import render

ROOT = Path(__file__).resolve().parent.parent


def setup_logging(level: str = "INFO") -> None:
    """配置 loguru：控制台 + logs/ 目录下的滚动日志文件（保留最近 10 个）。"""
    logger.remove()
    logger.add(sys.stderr, level=level)
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    logger.add(
        str(log_dir / "interface-auto_{time:YYYYMMDD_HHmmss}.log"),
        level=level,
        encoding="utf-8",
        retention=10,
    )


class CaseRunner:
    """用例执行器：变量替换 -> 发请求 -> 变量提取 -> 断言。

    run() 不抛异常，执行结果（含失败详情）全部写入返回的 CaseResult。
    """

    def __init__(self, executor: HttpExecutor, ctx):
        self.executor = executor
        self.ctx = ctx

    def run(self, case: TestCase) -> CaseResult:
        result = CaseResult(case=case, ok=False)
        try:
            # 1. 变量替换（url / headers / params / body）
            url = render(case.url, self.ctx)
            headers = render(case.headers, self.ctx) if case.headers else None
            params = render(case.params, self.ctx) if case.params else None
            body = render(case.body, self.ctx) if case.body is not None else None

            # 2. 发送请求并留痕
            response = self.executor.execute(case.method, url, headers, params, body, case.timeout)
            result.request_snapshot = request_snapshot(case.method, url, headers, params, body)
            result.response_snapshot = response_snapshot(response)

            # 3. 变量提取（写入变量池，供后续用例使用）
            if case.extract:
                extracted = extract_variables(response, case.extract)
                for key, value in extracted.items():
                    self.ctx.set(key, value)
                logger.info("[{}] 变量提取: {}", case.case_id, extracted)

            # 4. 断言
            result.assertions = run_assertions(response, case.asserts, self.ctx)
            failed = [a for a in result.assertions if not a.passed]
            result.ok = not failed
            if failed:
                result.error = self._failure_message(case, result, failed)
        except Exception as e:  # 请求异常 / 提取异常等
            result.ok = False
            result.error = f"用例执行异常: {type(e).__name__}: {e}"
            logger.error("[{}] {}", case.case_id, result.error)
        return result

    @staticmethod
    def _failure_message(case: TestCase, result: CaseResult, failed: list) -> str:
        """组装断言失败详情：失败断言明细 + 请求/响应报文摘要。"""
        lines = [f"用例 {case.case_id} [{case.api_name}] 断言失败 {len(failed)}/{len(result.assertions)}:"]
        for i, a in enumerate(failed, 1):
            expected_text = "" if a.op == "not_null" else f", 期望值={_fmt(a.expected)}"
            detail = f"（{a.message}）" if a.message else ""
            lines.append(f"  [{i}] {a.op} {a.path}: 实际值={_fmt(a.actual)}{expected_text}{detail}")

        req, resp = result.request_snapshot, result.response_snapshot
        if req:
            lines.append(f"请求: {req['method']} {req['url']}")
            if req.get("params"):
                lines.append(f"  查询参数: {_fmt(req['params'])}")
            if req.get("body") is not None:
                lines.append(f"  请求体: {_fmt(req['body'])}")
        if resp:
            body = resp.get("body", "")
            body = body if len(body) <= 800 else body[:800] + "..."
            lines.append(f"响应: {resp['status_code']} {body}")
        return "\n".join(lines)


def _fmt(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)
