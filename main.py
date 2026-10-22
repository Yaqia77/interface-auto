"""接口自动化测试 CLI 入口。

用法示例:
    python main.py                                    # 使用 default_env + data/api_cases.xlsx
    python main.py --env test --file data/api_cases.xlsx
    python main.py --module 演示-文章CRUD              # 只跑指定模块
    python main.py --priority P0,P1                   # 只跑指定优先级
    python main.py --keyword 登录                      # 按关键字筛选
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.context import load_config  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Excel 驱动的接口自动化测试")
    parser.add_argument("--env", default=None, help="环境名，默认取 config.yaml 的 default_env")
    parser.add_argument("--file", default="data/api_cases.xlsx", help="用例 Excel 文件或目录（目录则合并所有 .xlsx）")
    parser.add_argument("--module", default=None, help="按模块名筛选（包含匹配）")
    parser.add_argument("--priority", default=None, help="按优先级筛选，逗号分隔，如 P0,P1")
    parser.add_argument("--keyword", default=None, help="按关键字筛选（用例编号/接口名称/用例描述/URL）")
    parser.add_argument("--cases", default=None, help="按用例编号精确选择，逗号分隔（优先于 --module/--priority/--keyword）")
    parser.add_argument("--vars", default=None, help="运行前变量覆盖，JSON 字符串")
    parser.add_argument("--no-html", action="store_true", help="不生成 pytest-html 报告")
    parser.add_argument("--no-allure", action="store_true", help="不生成 allure 结果")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    report_cfg = config.get("report", {})

    # 相对路径统一按项目根目录解析
    file_arg = Path(args.file)
    if not file_arg.is_absolute():
        file_arg = (ROOT / file_arg).resolve()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = ROOT / "reports" / f"run_{ts}"
    report_dir.mkdir(parents=True, exist_ok=True)

    # 按用例文件类型分流收集：.json → UI 链路（test_ui），其余 → 接口链路（test_api）。
    # 显式指定单个测试文件，避免两类收集器在同一批次互相干扰（api 收集器会误读 json）。
    if file_arg.suffix.lower() == ".json":
        test_target = str(ROOT / "tests" / "test_ui.py")
    else:
        test_target = str(ROOT / "tests" / "test_api.py")
    pytest_args = [test_target, "-v", "--tb=short"]
    if args.env:
        pytest_args += [f"--env={args.env}"]
    pytest_args += [f"--file={file_arg}"]
    if args.module:
        pytest_args += [f"--module={args.module}"]
    if args.priority:
        pytest_args += [f"--priority={args.priority}"]
    if args.keyword:
        pytest_args += [f"--keyword={args.keyword}"]
    if args.cases:
        pytest_args += [f"--cases={args.cases}"]
    if args.vars:
        pytest_args += [f"--vars={args.vars}"]
    if report_cfg.get("html", True) and not args.no_html:
        pytest_args += [f"--html={report_dir / 'report.html'}", "--self-contained-html"]
    if report_cfg.get("allure", True) and not args.no_allure:
        pytest_args += [f"--alluredir={report_dir / 'allure-results'}"]

    print(f"[interface-auto] 用例文件: {file_arg}")
    print(f"[interface-auto] 报告目录: {report_dir}")
    exit_code = pytest.main(pytest_args)

    print("=" * 60)
    html_report = report_dir / "report.html"
    if html_report.exists():
        print(f"[interface-auto] HTML 报告: {html_report}")
    allure_dir = report_dir / "allure-results"
    if allure_dir.exists():
        allure_cfg = ROOT / "allurerc.mjs"  # Allure 3 报告配置（reportLanguage=zh，打开即中文）
        cfg_arg = f' --config "{allure_cfg}"' if allure_cfg.exists() else ""
        print(f"[interface-auto] Allure 结果: {allure_dir}（执行 allure serve{cfg_arg} {allure_dir} 查看）")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
