/** Axios 封装 + 接口函数（开发期经 Vite 代理 /api → FastAPI:8000）。 */
import axios from "axios";
import { ElMessage } from "element-plus";
import type { CaseItem, CasePage, CaseMeta, EnvsResp, RunCasesResp, RunCaseDetail, RunItem } from "../types";

const http = axios.create({ baseURL: "/api", timeout: 30000 });

http.interceptors.response.use(
  (resp) => resp,
  (error) => {
    // 错误归一：后端 detail 优先，其次网络层信息
    const detail = error.response?.data?.detail ?? error.message;
    ElMessage.error(typeof detail === "string" ? detail : JSON.stringify(detail));
    return Promise.reject(error);
  }
);

export const api = {
  listCases: (params: {
    module?: string;
    priority?: string;
    keyword?: string;
    run?: boolean;
  }) => http.get<CasePage>("/cases", { params }).then((r) => r.data),

  listEnvs: () => http.get<EnvsResp>("/envs").then((r) => r.data),

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

  /** 单文件 Allure 中文报告（新标签打开；后端首次访问会现场生成） */
  reportUrl: (runId: string) =>
    `/api/runs/${encodeURIComponent(runId)}/report`,
};
