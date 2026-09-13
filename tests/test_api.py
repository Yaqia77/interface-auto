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


def test_api(api_case, executor, context):
    if HAS_ALLURE:
        allure.dynamic.title(f"[{api_case.priority}] {api_case.case_id} {api_case.api_name}")
        allure.dynamic.feature(api_case.module)
        allure.dynamic.severity(SEVERITY.get(api_case.priority, "normal"))
        allure.dynamic.description(api_case.case_desc)

    if not api_case.run:
        pytest.skip("是否执行=N，跳过")

    runner = CaseRunner(executor, context)
    start = time.perf_counter()
    result = runner.run(api_case)
    result.duration = time.perf_counter() - start

    if HAS_ALLURE:
        if result.request_snapshot:
            _attach(result.request_snapshot, f"请求报文 {api_case.method} {api_case.url}")
        if result.response_snapshot:
            _attach(result.response_snapshot, "响应报文")

    if not result.ok:
        raise AssertionError(result.error)


def _attach(snapshot: dict, name: str):
    allure.attach(
        json.dumps(snapshot, ensure_ascii=False, indent=2, default=str),
        name=name,
        attachment_type=allure.attachment_type.JSON,
    )
