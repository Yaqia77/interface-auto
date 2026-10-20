"""参数化接口用例执行入口（用例来自 Excel，见 conftest.py 的 pytest_generate_tests）。"""
import json
import time

import pytest

from core.runner import CaseRunner

try:
    import allure
    HAS_ALLURE = True
except ImportError:  # 未安装 allure-pytest 时跳过增强报告
    HAS_ALLURE = False

SEVERITY = {"P0": "blocker", "P1": "critical", "P2": "major", "P3": "minor"}


def test_api(api_case, executor, context, dep_map, case_results):
    if HAS_ALLURE:
        allure.dynamic.title(f"[{api_case.priority}] {api_case.case_id} {api_case.api_name}")
        allure.dynamic.feature(api_case.module)
        allure.dynamic.severity(SEVERITY.get(api_case.priority, "normal"))
        allure.dynamic.description(api_case.case_desc)

    if not api_case.run:
        pytest.skip("是否执行=N，跳过")

    # 依赖链检查：前置用例必须全部通过
    deps = dep_map.get(api_case.case_id, [])
    if deps:
        failed_deps = [d for d in deps if case_results.get(d) not in ("passed", None)]
        # None = 该依赖未在本次执行范围内，不强制检查
        if failed_deps:
            case_results[api_case.case_id] = "skipped"
            pytest.skip(f"依赖用例未通过: {', '.join(failed_deps)}")

    runner = CaseRunner(executor, context)
    start = time.perf_counter()
    result = runner.run(api_case)
    result.duration = time.perf_counter() - start

    if HAS_ALLURE:
        if result.request_snapshot:
            _attach(result.request_snapshot, f"请求报文 {api_case.method} {api_case.url}")
        if result.response_snapshot:
            _attach(result.response_snapshot, "响应报文")
        if result.assertions:
            _attach_assertions(result.assertions)

    if not result.ok:
        case_results[api_case.case_id] = "failed"
        raise AssertionError(result.error)
    else:
        case_results[api_case.case_id] = "passed"


def _attach(snapshot: dict, name: str):
    allure.attach(
        json.dumps(snapshot, ensure_ascii=False, indent=2, default=str),
        name=name,
        attachment_type=allure.attachment_type.JSON,
    )


def _attach_assertions(assertions):
    """逐条断言结果落盘（op/path/expected/actual/passed/message），供平台报告详情“断言结果”视图消费。"""
    rows = [
        {
            "op": a.op,
            "path": a.path,
            "expected": a.expected,
            "actual": a.actual,
            "passed": bool(a.passed),
            "message": a.message,
        }
        for a in assertions
    ]
    allure.attach(
        json.dumps(rows, ensure_ascii=False, indent=2, default=str),
        name="断言结果",
        attachment_type=allure.attachment_type.JSON,
    )
