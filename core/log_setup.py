# -*- coding: utf-8 -*-
"""运行时日志配置（共享）：控制台 + logs/ 目录滚动日志。

原属 core.runner，因 api/web 两条链路都要用（tests/conftest 的 app_config fixture 统一初始化），
故提到 core 顶层共享位置，避免 conftest 反向依赖某个具体引擎包。行为与原 setup_logging 完全一致。
"""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

ROOT = Path(__file__).resolve().parent.parent  # 项目根（core/ 上一级）


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
