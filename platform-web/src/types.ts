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
}

export interface EnvsResp {
  default_env: string | null;
  envs: EnvInfo[];
}

/** 批次用例结果摘要（/api/runs/{id}/cases，后端已掩码） */
export interface RunCaseSummary {
  case_id: string;
  name: string;
  priority: string;
  status: "passed" | "failed" | "broken" | "skipped" | string;
  duration_ms: number;
  error: string;
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
}
