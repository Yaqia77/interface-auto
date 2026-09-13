"""断言引擎。

断言规则格式: [操作符, 取值路径, 期望值]，如 ["eq", "$.code", 0]。
取值路径支持:
  - status_code   响应状态码
  - response_text 响应原文
  - $.xxx         响应体 JSONPath（$ 为整个 body）
操作符: eq / neq / contains / gt / ge / lt / le / regex / not_null / len_eq
"""
import json
import re

from jsonpath_ng import parse

from .http_client import response_json
from .models import AssertionResult
from .variable import VariableNotFoundError, render


class AssertPathError(Exception):
    """取值路径无法解析。"""


def get_actual(response, path: str):
    """按取值路径从响应中取实际值。"""
    path = path.strip()
    if path == "status_code":
        return response.status_code
    if path == "response_text":
        return response.text
    if path.startswith("$"):
        body = response_json(response)
        if body is None:
            raise AssertPathError("响应体不是合法 JSON，无法按 JSONPath 取值")
        try:
            matches = parse(path).find(body)
        except Exception as e:
            raise AssertPathError(f"JSONPath {path!r} 语法错误: {e}") from e
        if not matches:
            raise AssertPathError(f"JSONPath {path!r} 未匹配到任何值")
        return matches[0].value
    raise AssertPathError(f"无法识别的取值路径 {path!r}（支持 status_code / response_text / $.开头）")


def run_assertions(response, rules: list, ctx) -> list:
    """执行全部断言，返回 AssertionResult 列表（不抛异常，逐条给出结果）。"""
    results = []
    for rule in rules or []:
        op = str(rule[0]).strip().lower()
        path = str(rule[1]).strip()
        expected = rule[2] if len(rule) > 2 else None

        # 期望值支持 {{变量}}（整串占位符保留原始类型）
        if isinstance(expected, str):
            try:
                expected = render(expected, ctx)
            except VariableNotFoundError as e:
                results.append(AssertionResult(op, path, expected, None, False, f"期望值变量解析失败: {e}"))
                continue

        try:
            actual = get_actual(response, path)
        except AssertPathError as e:
            results.append(AssertionResult(op, path, expected, None, False, str(e)))
            continue

        passed, message = _compare(op, actual, expected)
        results.append(AssertionResult(op, path, expected, actual, passed, message))
    return results


def _compare(op: str, actual, expected) -> tuple[bool, str]:
    """单条断言比较，返回 (是否通过, 失败说明)。"""
    try:
        if op == "eq":
            return _smart_eq(actual, expected), ""
        if op == "neq":
            return not _smart_eq(actual, expected), ""
        if op == "contains":
            return _contains(actual, expected), ""
        if op in ("gt", "ge", "lt", "le"):
            return _numeric(op, actual, expected), ""
        if op == "regex":
            return re.search(str(expected), str(actual)) is not None, ""
        if op == "not_null":
            return actual is not None and actual != "", ""
        if op == "len_eq":
            return len(actual) == int(expected), ""
        return False, f"未知操作符: {op}"
    except Exception as e:
        return False, f"断言执行异常: {e}"


def _smart_eq(actual, expected) -> bool:
    """相等比较；字符串与数字/布尔类型不一致时，尝试把字符串一侧解析为 JSON 标量再比。"""
    if actual == expected:
        return True
    if isinstance(actual, str) != isinstance(expected, str):
        try:
            if isinstance(actual, str):
                return _scalar(actual) == expected
            return actual == _scalar(expected)
        except (ValueError, TypeError):
            return False
    return False


def _scalar(text: str):
    value = json.loads(text)
    if isinstance(value, (dict, list)):
        raise ValueError("不是标量")
    return value


def _contains(actual, expected) -> bool:
    if isinstance(actual, list):
        return expected in actual
    return str(expected) in str(actual)


def _numeric(op: str, actual, expected) -> bool:
    a, e = float(actual), float(expected)
    return {"gt": a > e, "ge": a >= e, "lt": a < e, "le": a <= e}[op]
