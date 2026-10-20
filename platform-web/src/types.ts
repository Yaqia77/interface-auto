/** 与后端 OpenAPI 契约对齐的类型（backend/schemas.py）。 */

export interface CaseItem {
  case_id: string;
  module: string;
  api_name: string;
  case_desc: string;
  priority: string;
  run: boolean;
  method: string;
  url: string;
  headers: Record<string, unknown> | null;
  params: Record<string, unknown> | null;
  body: unknown;
  extract: Record<string, string> | null;
  asserts: string[][] | null;
  timeout: number | null;
  source: string;
  row: number;
}

export interface CasePage {
  total: number;
  items: CaseItem[];
}

export interface RunItem {
  run_id: string;
  status: "pending" | "running" | "passed" | "failed" | "error" | "unknown";
  source: "api" | "cli";
  args: Record<string, unknown> | null;
  started_at: string | null;
  finished_at: string | null;
  exit_code: number | null;
  report_dir: string | null;
  log_tail: string | null;
}

export interface EnvInfo {
  name: string;
  base_url: string | null;
  timeout?: number | null;
  verify_ssl?: boolean;
  default_headers?: Record<string, string>;
}

export interface EnvsResp {
  default_env: string | null;
  envs: EnvInfo[];
  secret_vars_file?: string | null;
  report?: Record<string, boolean>;
  log?: Record<string, string>;
}

/** PUT /api/envs 请求体：整体覆盖式保存环境段 */
export interface EnvsUpdate {
  default_env: string;
  envs: EnvInfo[];
}

/** 编辑用元数据（/api/cases/meta）：下拉候选统一来源 */
export interface AssertOpInfo {
  op: string;
  desc: string;
  need_expected: boolean;
}

export interface HeaderSuggest {
  key: string;
  value: string;
  used: number;
}

export interface CaseMeta {
  priorities: string[];
  methods: string[];
  assert_ops: AssertOpInfo[];
  modules: string[];
  header_suggest: HeaderSuggest[];
  variables: string[];
}

/** 批次用例结果摘要（/api/runs/{id}/cases，后端已掩码） */
export interface RunCaseSummary {
  case_id: string;
  name: string;
  priority: string;
  status: "passed" | "failed" | "broken" | "skipped" | string;
  duration_ms: number;
  error: string;
  summary: string;
  assert_total: number | null;
  assert_failed: number | null;
}

/** 单条断言执行结果（报告详情“断言结果”Tab） */
export interface AssertResult {
  op: string;
  path: string;
  expected: unknown;
  actual: unknown;
  passed: boolean;
  message: string;
}

export interface RunCasesResp {
  run_id: string;
  total: number;
  stats: Record<string, number>;
  items: RunCaseSummary[];
}

export interface RunCaseDetail {
  case_id: string;
  name: string;
  status: string;
  description: string;
  error: string;
  trace: string;
  request: Record<string, unknown> | null;
  response: Record<string, unknown> | null;
  assertions: AssertResult[] | null;
}

/** 凭证变量（/api/secrets）：后端仅回掩码值，绝不透传明文 */
export interface SecretVar {
  name: string;
  masked_value: string;
  length: number;
  empty: boolean;
  kind: string;      // 登录态/凭证 | 密文 | 固定值
  remark: string;
}

export interface SecretsResp {
  exists: boolean;
  items: SecretVar[];
}

/** 单用例跨批次执行历史（/api/runs/history/{case_id}） */
export interface CaseHistoryEntry {
  run_id: string;
  source: "api" | "cli" | string;
  started_at: string | null;
  finished_at: string | null;
  status: string;
  duration_ms: number;
  summary: string;
  error: string;
}
export interface CaseHistoryResp {
  case_id: string;
  scanned_batches: number;
  found: number;
  passed: number;
  failed: number;
  consec_fail: number;
  history: CaseHistoryEntry[];
}

/** 测试场景（/api/plans） */
export interface PlanItem {
  id: string;
  name: string;
  desc: string;
  case_ids: string[];
  env: string;
  created_at: string;
  updated_at: string;
  last_run_id: string | null;
  last_run_at: string | null;
}

export interface PlanCreateReq {
  name: string;
  desc?: string;
  case_ids: string[];
  env?: string;
}

export interface PlanUpdateReq {
  name?: string;
  desc?: string;
  case_ids?: string[];
  env?: string;
}

/** Webhook 通知配置（/api/webhooks） */
export interface WebhookItem {
  id: string;
  name: string;
  url: string;
  type: "wechat_work" | "feishu" | "custom";
  events: string[];
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface WebhookCreateReq {
  name: string;
  url: string;
  type?: string;
  events?: string[];
  enabled?: boolean;
}

export interface WebhookUpdateReq {
  name?: string;
  url?: string;
  type?: string;
  events?: string[];
  enabled?: boolean;
}

/** 定时任务（/api/schedules） */
export interface ScheduleItem {
  id: string;
  name: string;
  cron: string;
  plan_id: string;
  run_config: Record<string, unknown>;
  enabled: boolean;
  last_run_id: string | null;
  last_run_at: string | null;
  next_run_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ScheduleCreateReq {
  name: string;
  cron: string;
  plan_id?: string;
  run_config?: Record<string, unknown>;
  enabled?: boolean;
}

export interface ScheduleUpdateReq {
  name?: string;
  cron?: string;
  plan_id?: string;
  run_config?: Record<string, unknown>;
  enabled?: boolean;
}

/** 用户与权限（/api/auth）：后端绝不下发密码字段 */
export interface UserInfo {
  username: string;
  display_name: string;
  role: "admin" | "tl" | "qa" | "dev" | "viewer" | string;
  role_name: string;
  enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
  permissions: string[];
}

export interface LoginResp {
  token: string;
  user: UserInfo;
}

export interface UserCreateReq {
  username: string;
  password: string;
  display_name?: string;
  role: string;
}

export interface UserUpdateReq {
  display_name?: string;
  role?: string;
  enabled?: boolean;
  password?: string;
}

/** 操作审计留痕（/api/audit）：谁在什么时候改了什么 · 结果如何 */
export interface AuditItem {
  id: string;
  ts: string;
  username: string;
  display_name: string;
  role: string;
  method: string;
  path: string;
  action: string;
  target: string;
  detail: string;
  query: string;
  status: number;
  ok: boolean;
  ip: string;
}

export interface AuditLogsResp {
  total: number;
  returned: number;
  items: AuditItem[];
}
