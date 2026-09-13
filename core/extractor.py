"""JSONPath 变量提取。"""
from jsonpath_ng import parse

from .http_client import response_json


class ExtractError(Exception):
    """变量提取失败。"""


def extract_variables(response, rules: dict) -> dict:
    """按 rules: {变量名: JSONPath} 从响应体提取值，返回 {变量名: 值}。

    任一变量提取失败即抛出 ExtractError（含变量名与 JSONPath）。
    """
    body = response_json(response)
    if body is None:
        raise ExtractError("响应体不是合法 JSON，无法提取变量")

    result = {}
    for var, path in (rules or {}).items():
        try:
            matches = parse(path).find(body)
        except Exception as e:  # jsonpath 语法错误
            raise ExtractError(f"变量 {var} 的 JSONPath {path!r} 语法错误: {e}") from e
        if not matches:
            raise ExtractError(f"变量 {var} 提取失败: JSONPath {path!r} 未匹配到任何值")
        result[var] = matches[0].value
    return result
