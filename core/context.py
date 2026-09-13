"""环境配置加载与变量池。"""
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "config.yaml"


def load_config() -> dict:
    """加载 config/config.yaml。"""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"配置文件不存在: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_env_config(config: dict, env_name: str | None = None) -> dict:
    """取指定环境的配置段，未指定时用 default_env。"""
    envs = config.get("env") or {}
    name = env_name or config.get("default_env")
    if name not in envs:
        raise ValueError(f"环境 {name!r} 不存在，可用环境: {list(envs) or '无'}")
    return envs[name] or {}


class Context:
    """变量池。

    查找优先级：运行时 extract 提取值 > Excel「全局变量」表 > YAML 环境变量。
    """

    def __init__(self, yaml_vars: dict | None = None, excel_vars: dict | None = None):
        self._static: dict = {}
        self._static.update(yaml_vars or {})
        self._static.update(excel_vars or {})
        self._runtime: dict = {}

    def set(self, key: str, value: Any) -> None:
        self._runtime[key] = value

    def get(self, key: str) -> Any:
        if key in self._runtime:
            return self._runtime[key]
        return self._static.get(key)

    def has(self, key: str) -> bool:
        return key in self._runtime or key in self._static

    def all_keys(self) -> list:
        return sorted(set(self._static) | set(self._runtime))
