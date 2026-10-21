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
├── data/scripts.json         # 公共脚本库（平台「公共脚本」页维护，已 gitignore）
├── core/                     # 核心引擎（纯逻辑，v2 页面版可直接复用）
│   ├── excel_loader.py       # Excel 解析 + 格式校验（报错精确定位到行列）
│   ├── context.py            # 变量池（提取值 > 全局变量表 > YAML 配置）
│   ├── variable.py           # {{变量}} 占位符替换引擎
│   ├── http_client.py        # requests 封装（超时、报文快照）
│   ├── extractor.py          # JSONPath 变量提取
│   ├── asserts.py            # 断言引擎（10 种操作符）
│   ├── scripts.py            # 公共脚本引擎（声明式步骤链的定义/校验/执行）
│   ├── models.py             # 数据模型
│   └── runner.py             # 单用例执行编排（含前后置脚本钩子）
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
| 前置脚本 | 否 | 逗号分隔的公共脚本名，在主请求之前按序执行 |
| 后置脚本 | 否 | 逗号分隔的公共脚本名，无论主流程成败都在最后执行 |

### 断言语法

格式：`[["操作符", "取值路径", "期望值"], ...]`，多条断言全部通过用例才算通过。

**取值路径**：

- `status_code` — 响应状态码
- `response_text` — 响应原文
- `$.xxx` — 响应体 JSONPath（`$` 为整个 body）
- `var.xxx` — 变量池取值（如 `var.token`），用于不依赖响应的校验（前后置脚本里常用）

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
- **优先级**：运行时变量提取 > 凭证文件 secret_vars.xlsx > 「全局变量」表 > config.yaml（提供 `base_url`）
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

### 前后置公共脚本（登录/造数/清理复用）

多个用例都要先登录、都要造数、都要收尾清理时，把这些重复动作沉淀成**公共脚本**，
用例只在「前置脚本 / 后置脚本」列写脚本名（逗号分隔）即可引用。

脚本是**声明式步骤链**，只有四种步骤动作（不执行任意代码，避开 RCE 与审计盲区）：

| 动作 | 可用字段 | 用途 |
|---|---|---|
| `request` | `method` `url` `headers` `params` `body` `extract` `assert` `timeout` | 发一次请求，可提取变量、可带断言 |
| `sleep` | `seconds` | 等待异步任务落库（单步上限 30 秒） |
| `set_var` | `vars` | 写变量池，值支持 `{{变量}}` 占位符 |
| `assert` | `assert` | 断言上一条响应，或 `var.xxx` 变量池 |

执行语义：

- **前置**任一步失败 → 用例直接判失败，**主请求不会发出**（避免脏数据打到被测系统）
- **后置**在 `finally` 里执行，**主流程成败都会跑**（负责回收造出的数据）；后置失败同样判用例失败并提示「数据可能未清理」
- 步骤写入的变量对该用例后续全部可用（与用例自身的 `变量提取` 同一个变量池）
- 每条步骤的执行情况以「脚本轨迹」附件进报告，报告中可逐步回溯；变量名命中
  `token/password/secret/key/auth/cookie` 时轨迹只留掩码，**敏感值不落盘**

约束：单脚本最多 20 步；脚本名不能含逗号/空格/斜杠等（Excel 以逗号分隔引用）；
定义与执行共用一套校验（`core/scripts.py`），存得下就跑得通。

CLI 侧同样生效：脚本库存 `data/scripts.json`（路径可在 config.yaml 的 `scripts_file` 改），
不引用脚本的存量用例文件即使没有这两列也完全不受影响。

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

## 敏感凭证管理

账号密码等敏感信息**不要写在用例 Excel 里**（用例文件会提交到 Git 仓库）。框架提供独立的凭证文件机制：

1. 复制 `data/secret_vars_template.xlsx` 为 `data/secret_vars.xlsx`
2. 在「全局变量」表中填入真实账号密码（如 `username` / `password`）
3. 用例中通过 `{{username}}`、`{{password}}` 引用，与普通变量用法完全一致

说明：

- `secret_vars.xlsx` 已被 .gitignore 忽略，**不会提交到仓库**，仅本地生效
- 运行时自动加载（路径可在 config.yaml 的 `secret_vars_file` 修改），文件不存在则跳过
- 同名变量时，凭证文件的值**覆盖**用例 Excel「全局变量」表中的值
  （演示用例可放心用假值，真实运行时由凭证文件接管）

## 失败定位

- **控制台 / HTML 报告**：断言失败展示「实际值 vs 期望值」逐条明细 + 完整请求/响应报文
- **Excel 校验**：格式错误精确定位，如 `[_verify_broken.xlsx → 用例 第2行 K列(请求体)] JSON 解析失败`
- **日志**：`logs/` 下按运行时间戳滚动，含每条用例的完整报文

## 平台版（Web）：登录与角色权限

平台后端 `backend/` + 前端 `platform-web/`，浏览器访问统一入口。所有 `/api/*` 接口默认需要登录态，
细粒度权限由各接口的 `require_perm(...)` 二次校验（前端 `v-perm` 只做按钮显隐，不是安全边界）。

```bash
# 后端（首次启动自动播种 5 个角色账号）
.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000
# 前端
cd platform-web ; npm run dev
# 权限全链路冒烟（需后端已启动）
.venv\Scripts\python.exe tools\smoke_authz.py
# 公共脚本冒烟（定义校验 + 引擎真打接口 + Excel 无损兼容 + 引用保护）
.venv\Scripts\python.exe tools\smoke_scripts.py
```

角色与权限矩阵（默认基线写在 `backend/perm_store.py`，可在「系统管理 → 角色权限」页勾选调整，自定义分配存 `data/permissions.json`）：

| 权限码 | admin | tl | qa | dev | viewer |
|---|---|---|---|---|---|
| `case:write` 用例编辑/导入 | ✓ | ✓ | ✓ | | |
| `case:delete` 用例删除 | ✓ | ✓ | | | |
| `api:manage` 接口定义管理 | ✓ | ✓ | ✓ | | |
| `script:manage` 公共脚本管理 | ✓ | ✓ | ✓ | | |
| `plan:manage` 测试场景管理 | ✓ | ✓ | ✓ | | |
| `run:create` 触发/取消执行 | ✓ | ✓ | ✓ | ✓ | |
| `env:manage` / `secret:manage` / `webhook:manage` / `schedule:manage` | ✓ | ✓ | | | |
| `report:delete` 报告删除与旧报告清理 | ✓ | ✓ | | | |
| `audit:view` 操作审计查询/导出 | ✓ | ✓ | | | |
| `audit:manage` 审计日志清理 | ✓ | | | | |
| `user:manage` 用户管理 | ✓ | | | | |

说明：

- 播种账号 `admin/tl/qa/dev/viewer`（密码同用户名的 123 后缀），**生产部署请立即在「用户管理」改密**；
  账号数据存 `data/users.json`（已 gitignore，密码以 PBKDF2-HMAC-SHA256 加盐哈希保存）
- 报告堆积处理：报告列表行内「删除」+ 顶部「清理旧报告」（按时间保留最近 N 个批次，
  同步清理报告目录、历史条目与场景卡片的批次引用；运行中的批次拒绝删除）
- 三层权限拦截：路由 `meta.perm`（菜单级）→ `v-perm` 指令（按钮级）→ 后端 `require_perm`（数据级），
  前端仅控制可见性，真正拦下越权请求的是后端；用例/依赖/场景/凭证/环境/通知/定时/执行/报告
  的全部**写接口**均已挂 `require_perm`（新增一个 POST/PUT/DELETE 接口就必须带上它）。
  冒烟脚本第 7 节对每个写接口做越权试探，且试探体一律是「必填留空 / 资源不存在 / 自依赖」，
  因此能同时证明三件事：无权限角色 403、持权角色能穿过权限层、一轮试探不会写坏任何数据
- 操作审计留痕（`data/audit_logs.jsonl`，已 gitignore）：所有写操作与登录尝试都记录
  操作人/角色/动作/对象/请求摘要/结果/IP，入口在侧栏「系统管理 → 操作审计」（admin/tl 可见）；
  `password`、`token` 类字段与 Bearer 串写入前统一脱敏为 `***`，明文密码与凭证**绝不落盘**；
  文件超 2MB 自动裁剪最旧记录，页面支持按操作人/时间/仅失败筛选与 CSV 导出（Excel 双击不乱码）
- 权限矩阵可视化编辑（「系统管理 → 角色权限」，仅 admin）：界面只能改「权限码 → 角色」的分配，
  **不能凭空造码**（码目录由代码固定，否则前端 `v-perm` 会失效）；保存后按文件 mtime 热加载，
  **已登录会话无需重新登录即刻按新矩阵判定**（被收回权限者下一个请求即 403）；
  内置防锁死护栏：`user:manage`/`audit:manage` 强制保留给 admin，`run:create` 等关键码不允许全员为空，
  违反一律 400 并回具体原因；页面保存前展示人类可读的变更清单，每次变更自动落审计
- 公共脚本页（「测试管理 → 公共脚本」，需 `script:manage`）：步骤链编辑器的表单直接由
  `/api/scripts/meta` 渲染，动作与可用字段与后端校验同源（`core/scripts.py` 的 `ACTION_FIELDS`），
  **不会出现「页面能填、执行不认」的口径漂移**；用例抽屉的「前置/后置脚本」只允许从脚本库选
  （保存时后端校存在性，笔误当场拦下）；被用例引用的脚本**不可删除、不可改名**（409 并列出引用它的用例编号）；
  引用列首次写值时会自动补 Excel 表头，无需手工重建文件；执行详情抽屉的「脚本轨迹」Tab 逐步展示成败与摘要

## 路线图

- [x] v1：Excel 驱动 + CLI 运行 + 双报告（HTML / Allure）
- [ ] v1.1：CI 集成（Jenkinsfile / GitHub Actions）、失败通知（钉钉/企微/邮件）
- [ ] v2：页面版（FastAPI + Vue3 + Element Plus，在线编辑用例、触发执行、历史报告）
  - [x] v2 骨架：用例/场景/执行/报告/环境/凭证/通知/定时任务 + 登录与 RBAC 权限
  - [x] v2 审计：写操作与登录尝试留痕、脱敏落盘、筛选查询与 CSV 导出、超量自动裁剪
  - [x] v2 权限：角色权限矩阵可视化编辑（勾选即改，热生效 + 防锁死护栏 + 变更落审计）
  - [x] v2 脚本：前后置公共脚本（声明式步骤链 + Excel 引用列 + 引用保护 + 报告脚本轨迹）
  - [ ] v2 接口：接口定义管理（接口库沉淀 + OpenAPI 导入 + 由接口生成用例骨架）
