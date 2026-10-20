"""pytest 配置：自定义命令行参数、用例加载、Session 级fixture。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core.context import Context, get_env_config, load_config  # noqa: E402
from core.excel_loader import load as load_excel  # noqa: E402
from core.excel_loader import load_secret_vars  # noqa: E402
from core.http_client import HttpExecutor  # noqa: E402
from core.runner import setup_logging  # noqa: E402

_LOAD_CACHE: dict = {}


def pytest_addoption(parser):
    parser.addoption("--env", default=None, help="环境名（对应 config.yaml 的 env 段，默认取 default_env）")
    parser.addoption("--file", default=str(ROOT / "data" / "api_cases.xlsx"), help="用例 Excel 文件或目录")
    parser.addoption("--module", default=None, help="按模块名筛选（包含匹配）")
    parser.addoption("--priority", default=None, help="按优先级筛选，逗号分隔，如 P0,P1")
    parser.addoption("--keyword", default=None, help="按关键字筛选（匹配 用例编号/接口名称/用例描述/URL）")
    parser.addoption("--cases", default=None, help="按用例编号精确选择，逗号分隔（优先于 --module/--priority/--keyword）")
    parser.addoption("--vars", default=None, help='运行前变量覆盖，JSON 对象字符串（覆盖同名 secret/Excel/YAML 变量，优先级低于运行时提取）')


def _parse_vars(raw):
    """解析 --vars JSON 为 dict；非法输入直接终止收集期报错，避免静默忽略覆盖。"""
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        raise pytest.UsageError(f"--vars 不是合法 JSON：{raw!r}")
    if not isinstance(obj, dict):
        raise pytest.UsageError("--vars 必须是 JSON 对象（键值映射）")
    out = {}
    for k, v in obj.items():
        out[str(k)] = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return out


def _load_cases(file_arg: str):
    key = str(Path(file_arg).resolve())
    if key not in _LOAD_CACHE:
        _LOAD_CACHE[key] = load_excel(Path(file_arg))
    return _LOAD_CACHE[key]


def pytest_generate_tests(metafunc):
    """按 Excel 行顺序生成参数化用例（严格保持顺序，保证接口依赖可用）。"""
    if "api_case" not in metafunc.fixturenames:
        return
    data = _load_cases(metafunc.config.getoption("--file"))

    module = metafunc.config.getoption("--module")
    priority = metafunc.config.getoption("--priority")
    keyword = metafunc.config.getoption("--keyword")
    cases_opt = metafunc.config.getoption("--cases")
    pri_set = {p.strip().upper() for p in priority.split(",") if p.strip()} if priority else None
    id_set = {c.strip() for c in cases_opt.split(",") if c.strip()} if cases_opt else None

    selected = []
    for case in data.cases:
        if id_set is not None:
            # 精确选择：仅按编号命中，保持 Excel 行序（依赖顺序优先于勾选顺序）
            if case.case_id in id_set:
                selected.append(case)
            continue
        if module and module not in case.module:
            continue
        if pri_set and case.priority.upper() not in pri_set:
            continue
        if keyword:
            haystack = " ".join([case.case_id, case.api_name, case.case_desc, case.url])
            if keyword not in haystack:
                continue
        selected.append(case)

    if not selected:
        hint = "--cases" if id_set is not None else "--file/--module/--priority/--keyword"
        raise pytest.UsageError(f"没有匹配到任何用例，请检查 {hint} 筛选条件")
    metafunc.parametrize("api_case", selected, ids=[c.case_id for c in selected])


@pytest.fixture(scope="session")
def app_config(request):
    """加载 config.yaml 并初始化日志。"""
    config = load_config()
    env_name = request.config.getoption("--env")
    env_cfg = get_env_config(config, env_name)
    setup_logging(config.get("log", {}).get("level", "INFO"))
    return {"config": config, "env": env_cfg}


@pytest.fixture(scope="session")
def excel_data(request):
    """Excel 解析结果（用例 + 全局变量），进程内缓存。"""
    return _load_cases(request.config.getoption("--file"))


@pytest.fixture(scope="session")
def context(request, app_config, excel_data):
    """Session 级共享变量池。

    优先级：运行时提取值 > 凭证文件 secret_vars > 用例 Excel 全局变量 > YAML 配置。
    """
    yaml_vars = {"base_url": app_config["env"].get("base_url", "")}
    secret_path = Path(app_config["config"].get("secret_vars_file", "data/secret_vars.xlsx"))
    if not secret_path.is_absolute():
        secret_path = ROOT / secret_path
    merged_vars = dict(excel_data.variables)
    merged_vars.update(load_secret_vars(secret_path))  # 凭证文件覆盖用例文件同名变量
    overrides = _parse_vars(request.config.getoption("--vars"))
    if overrides:
        merged_vars.update(overrides)  # 运行前覆盖：高于 secret/Excel/YAML，低于运行时提取
    return Context(yaml_vars, merged_vars)


@pytest.fixture(scope="session")
def executor(app_config):
    """Session 级 HTTP 执行器。"""
    env = app_config["env"]
    return HttpExecutor(
        base_url=env.get("base_url", ""),
        default_headers=env.get("default_headers"),
        default_timeout=env.get("timeout", 15),
        verify_ssl=env.get("verify_ssl", True),
    )


@pytest.fixture(scope="session")
def dep_map():
    """加载用例依赖映射（data/dependencies.json）。"""
    dep_file = ROOT / "data" / "dependencies.json"
    if not dep_file.exists():
        return {}
    try:
        with open(dep_file, encoding="utf-8") as fp:
            return json.load(fp)
    except (json.JSONDecodeError, OSError):
        return {}


@pytest.fixture(scope="session")
def case_results():
    """Session 级用例结果登记表，供依赖链检查。"""
    return {}  # {case_id: "passed" | "failed" | "skipped" | "error"}
