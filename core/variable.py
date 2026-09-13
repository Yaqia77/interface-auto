"""{{变量}} 占位符替换引擎。"""
import json
import re

_PATTERN = re.compile(r"\{\{\s*([A-Za-z_]\w*)\s*\}\}")


class VariableNotFoundError(KeyError):
    """引用了未定义的变量。"""


def render(obj, ctx):
    """递归替换字符串/字典/列表中的 {{var}} 占位符。

    当整个字符串恰好是一个占位符时，返回变量的原始值（保留数字/布尔/对象类型）；
    否则做字符串内替换，非字符串变量值序列化为 JSON 文本。
    """
    if isinstance(obj, str):
        return _render_str(obj, ctx)
    if isinstance(obj, dict):
        return {k: render(v, ctx) for k, v in obj.items()}
    if isinstance(obj, list):
        return [render(v, ctx) for v in obj]
    return obj


def _render_str(text: str, ctx):
    whole = _PATTERN.fullmatch(text.strip())
    if whole:  # 整串就是一个占位符 → 保留原始类型
        return _lookup(whole.group(1), ctx)

    def _sub(match):
        value = _lookup(match.group(1), ctx)
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)

    return _PATTERN.sub(_sub, text)


def _lookup(key: str, ctx):
    if not ctx.has(key):
        available = ", ".join(ctx.all_keys()) or "无"
        raise VariableNotFoundError("变量 {" + key + "} 未定义（当前可用变量: " + available + "）")
    return ctx.get(key)
