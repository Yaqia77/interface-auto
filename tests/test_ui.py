# -*- coding: utf-8 -*-
"""UI 用例执行入口（用例来自项目 JSON，见 conftest.py 的 ui_case 参数化）。

链路复用接口自动化：pytest 收集 → allure 步骤/附件 → allure-results → 平台报告。
每条步骤以 allure.step 记录；截图与步骤轨迹作为附件落入 allure-results，
供平台报告页「UI 步骤」视图消费（截图经 /api/runs/{id}/attachment/{file} 取图）。
"""
import json

import pytest

from core.ui_runner import UiRunner

try:
    import allure
    HAS_ALLURE = True
except ImportError:  # 未装 allure-pytest 时降级：不出步骤/附件，但仍正常判定成败
    HAS_ALLURE = False

SEVERITY = {"P0": "blocker", "P1": "critical", "P2": "major", "P3": "minor"}


def _step_cm(label):
    return allure.step(label) if HAS_ALLURE else _null()


class _null:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _attach_png(name, data):
    if HAS_ALLURE:
        allure.attach(name=name, body=data, attachment_type=allure.attachment_type.PNG)


def test_ui(ui_case, app_config, context, dep_map, case_results):
    if HAS_ALLURE:
        allure.dynamic.title(f"[{ui_case.get('priority')}] {ui_case.get('case_id')} {ui_case.get('name')}")
        allure.dynamic.feature(ui_case.get("module", ""))
        allure.dynamic.severity(SEVERITY.get(ui_case.get("priority"), "normal"))
        allure.dynamic.description(ui_case.get("desc", ""))

    if not ui_case.get("run", True):
        case_results[ui_case.get("case_id")] = "skipped"
        pytest.skip("是否执行=N，跳过")

    deps = dep_map.get(ui_case.get("case_id"), [])
    if deps:
        failed_deps = [d for d in deps if case_results.get(d) not in ("passed", None)]
        if failed_deps:
            case_results[ui_case.get("case_id")] = "skipped"
            pytest.skip(f"因依赖用例未通过而阻塞: {', '.join(failed_deps)}")

    base_url = (app_config["env"] or {}).get("base_url", "")
    runner = UiRunner(context, base_url,
                      attach=(_attach_png if HAS_ALLURE else None),
                      step=(_step_cm if HAS_ALLURE else None))
    result = runner.run(ui_case)

    if HAS_ALLURE:
        allure.attach(
            json.dumps(result.steps, ensure_ascii=False, indent=2, default=str),
            name="UI步骤", attachment_type=allure.attachment_type.JSON,
        )

    if not result.ok:
        case_results[ui_case.get("case_id")] = "failed"
        raise AssertionError(result.error or "UI 用例失败")
    case_results[ui_case.get("case_id")] = "passed"
