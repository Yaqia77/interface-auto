/** Axios 封装 + 接口函数（开发期经 Vite 代理 /api → FastAPI:8000）。 */
import axios from "axios";
import { ElMessage } from "element-plus";
import type { CaseItem, CasePage, CaseMeta, CaseHistoryResp, EnvsResp, EnvsUpdate, RunCasesResp, RunCaseDetail, RunItem, SecretsResp, PlanItem, PlanCreateReq, PlanUpdateReq, WebhookItem, WebhookCreateReq, WebhookUpdateReq, ScheduleItem, ScheduleCreateReq, ScheduleUpdateReq, LoginResp, UserInfo, UserCreateReq, UserUpdateReq } from "../types";
import { clearToken, getToken } from "../utils/session";

const http = axios.create({ baseURL: "/api", timeout: 30000 });

// 请求拦截：统一注入登录态
http.interceptors.request.use((cfg) => {
  const token = getToken();
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});

http.interceptors.response.use(
  (resp) => resp,
  (error) => {
    // 401：登录态失效，清 token 后硬跳登录页（避开在登录页本身死循环）
    if (error.response?.status === 401) {
      clearToken();
      if (window.location.pathname !== "/login") {
        ElMessage.warning("登录已过期，请重新登录");
        window.location.assign("/login");
      }
      return Promise.reject(error);
    }
    // 错误归一：后端 detail 优先，其次网络层信息
    const detail = error.response?.data?.detail ?? error.message;
    ElMessage.error(typeof detail === "string" ? detail : JSON.stringify(detail));
    return Promise.reject(error);
  }
);

export const api = {
  /* ---------- 登录与用户 ---------- */
  login: (body: { username: string; password: string }) =>
    http.post<LoginResp>("/auth/login", body).then((r) => r.data),

  logout: () => http.post<{ ok: boolean }>("/auth/logout").then((r) => r.data),

  getMe: () => http.get<UserInfo>("/auth/me").then((r) => r.data),

  listUsers: () => http.get<UserInfo[]>("/auth/users").then((r) => r.data),

  createUser: (body: UserCreateReq) =>
    http.post<UserInfo>("/auth/users", body).then((r) => r.data),

  updateUser: (username: string, body: UserUpdateReq) =>
    http.put<UserInfo>(`/auth/users/${encodeURIComponent(username)}`, body).then((r) => r.data),

  deleteUser: (username: string) =>
    http.delete<{ ok: boolean }>(`/auth/users/${encodeURIComponent(username)}`).then((r) => r.data),

  listCases: (params: {
    module?: string;
    priority?: string;
    keyword?: string;
    run?: boolean;
  }) => http.get<CasePage>("/cases", { params }).then((r) => r.data),

  listEnvs: () => http.get<EnvsResp>("/envs").then((r) => r.data),

  /** 保存环境配置（写回 config.yaml，下一次执行/拉取即生效） */
  updateEnvs: (body: EnvsUpdate) =>
    http.put<EnvsResp>("/envs", body).then((r) => r.data),

  /** 更新用例（只传改动字段；后端写回 Excel，校验不外溢） */
  updateCase: (caseId: string, changes: Record<string, unknown>) =>
    http
      .put<CaseItem>(`/cases/${encodeURIComponent(caseId)}`, changes)
      .then((r) => r.data),

  /** 新增用例（整行追加写回 Excel 末行，编号唯一） */
  createCase: (data: Record<string, unknown>) =>
    http.post<CaseItem>("/cases", data).then((r) => r.data),

  /** 删除用例（Excel 整行删除） */
  deleteCase: (caseId: string) =>
    http
      .delete<{ deleted: string; file: string }>(
        `/cases/${encodeURIComponent(caseId)}`
      )
      .then((r) => r.data),

  /** 编辑用元数据：优先级/模块/请求头/断言操作符/变量候选 */
  getCaseMeta: () => http.get<CaseMeta>("/cases/meta").then((r) => r.data),

  listRuns: (limit = 20) =>
    http.get<RunItem[]>("/runs", { params: { limit } }).then((r) => r.data),

  createRun: (body: {
    env?: string;
    module?: string;
    priority?: string;
    keyword?: string;
    cases?: string[];
    vars?: Record<string, unknown>;
    file?: string;
  }) => http.post<RunItem>("/runs", body).then((r) => r.data),

  getRun: (runId: string) =>
    http.get<RunItem>(`/runs/${encodeURIComponent(runId)}`).then((r) => r.data),

  /** 取消运行中批次（后端 taskkill 进程树；已结束批次幂等返回当前状态） */
  cancelRun: (runId: string) =>
    http
      .post<{ run_id: string; status: string; cancelling: boolean }>(
        `/runs/${encodeURIComponent(runId)}/cancel`
      )
      .then((r) => r.data),

  /** 删除批次报告（含报告目录；需 report:delete 权限） */
  deleteRun: (runId: string) =>
    http
      .delete<{ run_id: string; deleted_report_dir: string | null }>(
        `/runs/${encodeURIComponent(runId)}`
      )
      .then((r) => r.data),

  /** 清理旧报告：保留最近 keep 个批次，其余删除 */
  cleanupRuns: (keep = 20) =>
    http
      .post<{ keep: number; scanned: number; deleted: number; deleted_ids: string[] }>(
        `/runs/cleanup?keep=${keep}`
      )
      .then((r) => r.data),

  getRunLog: (runId: string) =>
    http
      .get<{ run_id: string; status: string; lines: number; log: string }>(
        `/runs/${encodeURIComponent(runId)}/log`
      )
      .then((r) => r.data),

  /** 平台原生明细：批次用例结果摘要（已掩码） */
  getRunCases: (runId: string) =>
    http
      .get<RunCasesResp>(`/runs/${encodeURIComponent(runId)}/cases`)
      .then((r) => r.data),

  /** 单用例请求/响应快照（已掩码+截断） */
  getRunCaseDetail: (runId: string, caseId: string) =>
    http
      .get<RunCaseDetail>(
        `/runs/${encodeURIComponent(runId)}/cases/${encodeURIComponent(caseId)}`
      )
      .then((r) => r.data),

  /** 单用例跨批次执行历史（新→旧） */
  getCaseHistory: (caseId: string, limit = 30) =>
    http
      .get<CaseHistoryResp>(`/runs/history/${encodeURIComponent(caseId)}`, { params: { limit } })
      .then((r) => r.data),

  /** 单文件 Allure 中文报告（新标签打开；后端首次访问会现场生成） */
  reportUrl: (runId: string) =>
    `/api/runs/${encodeURIComponent(runId)}/report`,

  /* ---------- 凭证管理（值全程掩码，不回显明文） ---------- */
  listSecrets: () => http.get<SecretsResp>("/secrets").then((r) => r.data),

  createSecret: (body: { name: string; value: string; remark?: string }) =>
    http.post<SecretsResp>("/secrets", body).then((r) => r.data),

  updateSecret: (name: string, body: { value?: string; remark?: string }) =>
    http
      .put<SecretsResp>(`/secrets/${encodeURIComponent(name)}`, body)
      .then((r) => r.data),

  deleteSecret: (name: string) =>
    http
      .delete<SecretsResp>(`/secrets/${encodeURIComponent(name)}`)
      .then((r) => r.data),

  /* ---------- 测试场景 ---------- */
  listPlans: () => http.get<PlanItem[]>("/plans").then((r) => r.data),

  createPlan: (body: PlanCreateReq) =>
    http.post<PlanItem>("/plans", body).then((r) => r.data),

  getPlan: (id: string) =>
    http.get<PlanItem>(`/plans/${encodeURIComponent(id)}`).then((r) => r.data),

  updatePlan: (id: string, body: PlanUpdateReq) =>
    http.put<PlanItem>(`/plans/${encodeURIComponent(id)}`, body).then((r) => r.data),

  deletePlan: (id: string) =>
    http.delete<{ ok: boolean }>(`/plans/${encodeURIComponent(id)}`).then((r) => r.data),

  /** 按场景发起执行，返回新批次 RunItem */
  runPlan: (id: string) =>
    http.post<RunItem>(`/plans/${encodeURIComponent(id)}/run`).then((r) => r.data),

  /* ---------- 用例导入导出 ---------- */
  /** 导出筛选结果为 xlsx 下载 */
  exportCases: (params: { module?: string; priority?: string; keyword?: string; run?: boolean }) =>
    http.get("/cases/export", { params, responseType: "blob" }).then((r) => r.data as Blob),

  /** 导入 xlsx 文件追加用例 */
  importCases: (file: File) => {
    const fd = new FormData();
    fd.append("uploaded_file", file);
    return http
      .post<{ imported: number; skipped: number; errors: string[] }>("/cases/import", fd,
        { headers: { "Content-Type": "multipart/form-data" }, timeout: 60000 })
      .then((r) => r.data);
  },

  /* ---------- Webhook 通知管理 ---------- */
  listWebhooks: () => http.get<WebhookItem[]>("/webhooks").then((r) => r.data),

  createWebhook: (body: WebhookCreateReq) =>
    http.post<WebhookItem>("/webhooks", body).then((r) => r.data),

  updateWebhook: (id: string, body: WebhookUpdateReq) =>
    http.put<WebhookItem>(`/webhooks/${encodeURIComponent(id)}`, body).then((r) => r.data),

  deleteWebhook: (id: string) =>
    http.delete<{ ok: boolean }>(`/webhooks/${encodeURIComponent(id)}`).then((r) => r.data),

  testWebhook: (id: string) =>
    http.post<{ ok: boolean; status_code: number; response: string }>(
      `/webhooks/${encodeURIComponent(id)}/test`).then((r) => r.data),

  /* ---------- 定时任务 ---------- */
  listSchedules: () => http.get<ScheduleItem[]>("/schedules").then((r) => r.data),

  createSchedule: (body: ScheduleCreateReq) =>
    http.post<ScheduleItem>("/schedules", body).then((r) => r.data),

  updateSchedule: (id: string, body: ScheduleUpdateReq) =>
    http.put<ScheduleItem>(`/schedules/${encodeURIComponent(id)}`, body).then((r) => r.data),

  deleteSchedule: (id: string) =>
    http.delete<{ ok: boolean }>(`/schedules/${encodeURIComponent(id)}`).then((r) => r.data),

  runSchedule: (id: string) =>
    http.post<RunItem>(`/schedules/${encodeURIComponent(id)}/run`).then((r) => r.data),

  previewCron: (cron: string, n = 5) =>
    http.get<{ cron: string; next_runs: string[] }>("/schedules/preview/next-runs", {
      params: { cron, n },
    }).then((r) => r.data),

  /* ---------- 用例依赖 ---------- */
  getAllDeps: () => http.get<Record<string, string[]>>("/dependencies").then((r) => r.data),

  getDeps: (caseId: string) =>
    http.get<{ case_id: string; dependencies: string[] }>(
      `/dependencies/${encodeURIComponent(caseId)}`).then((r) => r.data),

  setDeps: (caseId: string, deps: string[]) =>
    http.put<{ case_id: string; dependencies: string[] }>(
      `/dependencies/${encodeURIComponent(caseId)}`, { dependencies: deps }).then((r) => r.data),
};
