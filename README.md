# interface-auto 接口自动化测试框架

Excel 驱动的接口自动化测试程序：用例写在 Excel 中，程序读取执行并生成测试报告。
初版（v1）以命令行方式运行，页面版（v2）规划中。

## 技术栈

Python 3.10+ · requests · openpyxl · pytest · jsonpath-ng · pytest-html / allure-pytest · PyYAML · loguru

## 目录结构

```
interface-auto/
├── config/config.yaml        # 环境配置（域名/超时/默认请求头/报告开关）
├── data/api_cases.xlsx       # 接口用例 Excel（用例/全局变量/填写说明 3 个 Sheet）
├── core/                     # 核心引擎（纯逻辑，v2 页面版可直接复用）
│   ├── excel_loader.py       # Excel 解析 + 格式校验（报错精确定位到行列）
│   ├── context.py            # 变量池（提取值 > 全局变量表 > YAML 配置）
│   ├── variable.py           # {{变量}} 占位符替换引擎
│   ├── http_client.py        # requests 封装（超时、报文快照）
│   ├── extractor.py          # JSONPath 变量提取
│   ├── asserts.py            # 断言引擎（10 种操作符）
│   ├── models.py             # 数据模型
│   └── runner.py             # 单用例执行编排
├── tests/                    # pytest 参数化入口（保持 Excel 行顺序，保证接口依赖）
├── tools/gen_template.py     # 生成/重置 Excel 用例模板
├── main.py                   # CLI 入口
├── reports/                  # 每次运行一个时间戳目录：report.html + allure-results/
└── logs/                     # 运行日志（含完整请求/响应报文，保留最近 10 份）
```

## 快速开始

### 1. 安装依赖

```bash
# 建议使用虚拟环境
python -m venv .venv
# Windows
.venv\Scripts\pip install -r requirements.txt
# macOS / Linux
.venv/bin/pip install -r requirements.txt
```

### 2. 生成用例模板（首次）

```bash
python tools/gen_template.py
```

生成 `data/api_cases.xlsx`，内置 9 条演示用例（基于公开 API httpbin.org 与
jsonplaceholder.typicode.com，开箱即跑）。

### 3. 运行

```bash
python main.py
```

预期结果：`8 passed, 1 skipped`，并在 `reports/run_<时间戳>/` 下生成报告。

### 4. 查看报告

- **HTML 报告**：`reports/run_<时间戳>/report.html`，单文件，双击即可打开，
  每条用例含完整请求/响应报文
- **Allure 报告**（可选，需本机安装 [Allure 命令行](https://allure.apache.org/)）：

```bash
allure serve reports/run_<时间戳>/allure-results
```

## 用例编写指南

Excel 共 3 个 Sheet：**用例**（核心）、**全局变量**、**填写说明**（Excel 内置帮助，可随时查阅）。

### 用例表字段

| 字段 | 必填 | 说明 |
|---|---|---|
| 用例编号 | 是 | 全局唯一，如 `login_001` |
| 模块 | 是 | 模块名，用于报告分组与 `--module` 筛选 |
| 接口名称 | 是 | 接口的业务名称 |
| 用例描述 | 是 | 一句话描述验证点 |
| 优先级 | 是 | P0 / P1 / P2 / P3 |
| 是否执行 | 是 | Y 执行，N 跳过 |
| 请求方式 | 是 | GET / POST / PUT / DELETE / PATCH |
| 请求路径 | 是 | `http` 开头的完整 URL 直接使用；相对路径拼接 config.yaml 的 `base_url`；支持 `{{变量}}` |
| 请求头 | 否 | JSON 对象，与环境默认请求头合并（用例优先） |
| 查询参数 | 否 | JSON 对象，URL 查询参数 |
| 请求体 | 否 | JSON 对象/数组，或纯文本 |
| 变量提取 | 否 | `{"变量名":"$.data.token"}`，从响应体按 JSONPath 提取 |
| 断言 | 是 | JSON 数组，见下方断言语法 |
| 超时(秒) | 否 | 正数，缺省用 config.yaml 的 timeout |

### 断言语法

格式：`[["操作符", "取值路径", "期望值"], ...]`，多条断言全部通过用例才算通过。

**取值路径**：

- `status_code` — 响应状态码
- `response_text` — 响应原文
- `$.xxx` — 响应体 JSONPath（`$` 为整个 body）

**操作符**：

| 操作符 | 说明 | 示例 |
|---|---|---|
| eq / neq | 相等 / 不等（字符串与数字智能比较） | `["eq","$.code",0]` |
| contains | 字符串子串包含 / 列表成员包含 | `["contains","$.message","成功"]` |
| gt / ge / lt / le | 数值比较 | `["gt","$.total",0]` |
| regex | 正则匹配 | `["regex","$.phone","^1\d{10}$"]` |
| not_null | 非空（可省略期望值） | `["not_null","$.data.id"]` |
| len_eq | 长度相等（列表条数/字符串长度） | `["len_eq","$",10]` |

**期望值支持 `{{变量}}`**：如 `["eq","$.id","{{post_id}}"]`，可实现"查询结果与上一步创建的 ID 一致"类断言。

### 变量机制

- **写法**：`{{变量名}}`，可用于 请求路径 / 请求头 / 查询参数 / 请求体 / 断言期望值
- **优先级**：运行时变量提取 > 「全局变量」表 > config.yaml（提供 `base_url`）
- **类型保留**：JSON 列中占位符写在引号内（如 `{"id":"{{post_id}}"}`），
  当整个值恰好是一个占位符时，替换后保留原始类型（数字/布尔）
- **依赖顺序**：用例严格按行号顺序串行执行，后面的用例可使用前面用例提取的变量
  （如先登录提 token，再访问鉴权接口）
- **筛选提醒**：按 `--module/--priority/--keyword` 筛选时，被依赖的用例
  （如提取 token 的登录用例）需同时被选中，否则会报「变量未定义」

### 典型场景：登录态串联

| 用例编号 | 请求方式 | 请求路径 | 变量提取 | 断言 |
|---|---|---|---|---|
| login_001 | POST | /api/login | `{"token":"$.data.token"}` | `[["eq","status_code",200]]` |
| get_profile_001 | GET | /api/profile | | `[["eq","status_code",200]]` |

get_profile_001 的请求头写：`{"Authorization":"Bearer {{token}}"}`

## 运行参数

```bash
python main.py [选项]
```

| 参数 | 说明 |
|---|---|
| `--env <名称>` | 环境名，对应 config.yaml 的 `env` 段，默认取 `default_env` |
| `--file <路径>` | 用例 Excel 文件或目录（目录则合并所有 .xlsx），默认 `data/api_cases.xlsx` |
| `--module <名称>` | 按模块名筛选（包含匹配） |
| `--priority <P0,P1>` | 按优先级筛选，逗号分隔 |
| `--keyword <关键字>` | 按关键字筛选（匹配 用例编号/接口名称/用例描述/URL） |
| `--no-html` | 不生成 pytest-html 报告 |
| `--no-allure` | 不生成 allure 结果 |

示例：

```bash
python main.py --env test --module 用户模块 --priority P0
```

## 环境配置（config.yaml）

```yaml
default_env: test
env:
  test:
    base_url: https://httpbin.org   # 用例中相对路径的拼接前缀
    timeout: 15                     # 全局默认超时（秒）
    default_headers:                # 全局默认请求头（用例可覆盖）
      User-Agent: interface-auto/1.0
```

接入真实系统：把 `base_url` 换成被测环境域名，用例中只写相对路径；
多环境（dev/test/prod）在 `env` 段下并列配置多个，运行时 `--env` 切换。

## 失败定位

- **控制台 / HTML 报告**：断言失败展示「实际值 vs 期望值」逐条明细 + 完整请求/响应报文
- **Excel 校验**：格式错误精确定位，如 `[_verify_broken.xlsx → 用例 第2行 K列(请求体)] JSON 解析失败`
- **日志**：`logs/` 下按运行时间戳滚动，含每条用例的完整报文

## 路线图

- [x] v1：Excel 驱动 + CLI 运行 + 双报告（HTML / Allure）
- [ ] v1.1：CI 集成（Jenkinsfile / GitHub Actions）、失败通知（钉钉/企微/邮件）
- [ ] v2：页面版（FastAPI + SQLite + Vue3 + Element Plus，在线编辑用例、触发执行、历史报告）
