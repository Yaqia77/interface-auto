<script setup lang="ts">
/** 批次报告页（按原型重构）：无 runId 时落批次列表；有则展示批次概览 + 用例明细筛选 + 失败归类 + 执行详情抽屉 + Allure + 与上批次对比。 */
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "../api";
import type { RunCaseDetail, RunCaseSummary, RunItem } from "../types";

const route = useRoute();
const router = useRouter();
// run_id 含 "/"（cli 批次），走 query 传参：/report?runId=reports/run_xxx
const runId = computed(() => (route.query.runId as string) ?? "");

const loading = ref(false);
const cases = ref<RunCaseSummary[]>([]);
const stats = ref<Record<string, number>>({});
const total = ref(0);
const batch = ref<RunItem | null>(null);   // api 批次详情（cli 取不到为 null）

/* ================= 批次列表（无 runId 时的落地页，侧栏“报告详情”入口） ================= */
const listMode = computed(() => !runId.value);
const runList = ref<RunItem[]>([]);
const runStatusType = (s: string) =>
  (({ passed: "success", failed: "danger", error: "danger", running: "warning", pending: "info", broken: "warning" } as Record<string, any>)[s] ?? "info");
function argsText(a: Record<string, unknown> | null): string {
  if (!a) return "—";
  const parts = ["env", "module", "priority", "keyword"].map((k) => a[k]).filter(Boolean);
  return parts.length ? parts.join(" · ") : "全量";
}
async function loadRunList() {
  loading.value = true;
  try { runList.value = await api.listRuns(50); }
  finally { loading.value = false; }
}
function openRun(rid: string) { router.push({ path: "/report", query: { runId: rid } }); }

const activeTab = ref("detail");
const allureSrc = ref("");       // 懒加载：切到 Allure Tab 才设 src（首次现场生成可能 30s+）
const allureLoading = ref(false);

/* ================= 与上批次对比 ================= */
const runs = ref<RunItem[]>([]);           // 候选基线批次列表（listRuns 按时间倒序）
const baselineRunId = ref("");             // 选中的对比基线批次
const baselineCases = ref<RunCaseSummary[]>([]);
const baselineLoading = ref(false);
const compared = ref(false);               // 是否已成功加载过基线明细

const statusType = (s: string) =>
  (({ passed: "success", failed: "danger", broken: "warning", skipped: "info" } as Record<string, any>)[s] ?? "info");

/* ================= 明细筛选 + 失败置顶 ================= */
const filterStatus = ref<string[]>([]);
const filterPrio = ref<string[]>([]);
const filterKw = ref("");
const FAILED_STATUSES = ["failed", "broken"];
const statusOptions = ["passed", "failed", "broken", "skipped"];
const prioOptions = computed(() => [...new Set(cases.value.map((c) => c.priority))].sort());
const hasFilter = computed(
  () => filterStatus.value.length > 0 || filterPrio.value.length > 0 || filterKw.value.trim() !== "");

const filteredCases = computed(() => {
  const kw = filterKw.value.trim().toLowerCase();
  return cases.value
    .filter((c) => {
      if (filterStatus.value.length && !filterStatus.value.includes(c.status)) return false;
      if (filterPrio.value.length && !filterPrio.value.includes(c.priority)) return false;
      if (kw && !(c.case_id.toLowerCase().includes(kw) || (c.name ?? "").toLowerCase().includes(kw))) return false;
      return true;
    })
    .sort((a, b) => {
      const af = FAILED_STATUSES.includes(a.status) ? 0 : 1;
      const bf = FAILED_STATUSES.includes(b.status) ? 0 : 1;
      if (af !== bf) return af - bf;
      return a.case_id.localeCompare(b.case_id);
    });
});

function toggleOnlyFailed() {
  const isOn = filterStatus.value.length === 2 && FAILED_STATUSES.every((s) => filterStatus.value.includes(s));
  filterStatus.value = isOn ? [] : [...FAILED_STATUSES];
}
function clearFilter() {
  filterStatus.value = [];
  filterPrio.value = [];
  filterKw.value = "";
}

/* ================= 批次概览 KPI ================= */
const failedCount = computed(() => (stats.value.failed ?? 0) + (stats.value.broken ?? 0));
const passRate = computed(() => (total.value ? Math.round(((stats.value.passed ?? 0) / total.value) * 100) : 0));
const hasFailures = computed(() => failedCount.value > 0);

/* ================= 失败归类（前端按错误文本聚合） ================= */
interface FailCat { label: string; color: string; count: number; hint?: string }
const failCats = computed<FailCat[]>(() => {
  let auth = 0, assert = 0, reqerr = 0, other = 0;
  for (const c of cases.value) {
    if (!FAILED_STATUSES.includes(c.status)) continue;
    const t = ((c.error ?? "") + " " + (c.summary ?? "")).toLowerCase();
    if (t.includes("鉴权") || t.includes("01000002") || t.includes("401") || t.includes("403") || t.includes("unauth")) auth++;
    else if (t.includes("异常") || t.includes("timeout") || t.includes("connection") || c.status === "broken") reqerr++;
    else if (t.includes("断言") || t.includes("assertion")) assert++;
    else other++;
  }
  const f = failedCount.value || 1;
  const pct = (n: number) => Math.round((n / f) * 100);
  return [
    { label: "鉴权失败", color: "#f56c6c", count: auth, hint: auth ? "建议：更新凭证 token" : undefined },
    { label: "断言不符", color: "#e6a23c", count: assert },
    { label: "请求异常", color: "#409eff", count: reqerr },
    { label: "其他", color: "#909399", count: other },
  ].map((c) => ({ ...c, count: c.count, hint: c.hint ? `${c.hint}（${pct(c.count)}%）` : c.hint }));
});

/* ================= 执行详情抽屉 ================= */
const detailVisible = ref(false);
const detail = ref<RunCaseDetail | null>(null);
const detailLoading = ref(false);
const detailTab = ref<"req" | "resp" | "assert" | "log">("req");

async function openDetail(row: RunCaseSummary) {
  detailVisible.value = true;
  detailLoading.value = true;
  detailTab.value = FAILED_STATUSES.includes(row.status) ? "assert" : "req";
  detail.value = null;
  try {
    detail.value = await api.getRunCaseDetail(runId.value, row.case_id);
  } finally {
    detailLoading.value = false;
  }
}

/* ================= 联动重跑 ================= */
function rerunCase(row: RunCaseSummary) {
  router.push({ path: "/execution", query: { keyword: row.case_id } });
}
function rerunBatch() {
  const a = (batch.value?.args ?? {}) as Record<string, unknown>;
  router.push({
    path: "/execution",
    query: {
      module: a.module ? String(a.module) : undefined,
      priority: a.priority ? String(a.priority) : undefined,
      keyword: a.keyword ? String(a.keyword) : undefined,
    },
  });
}

async function load() {
  if (!runId.value) { await loadRunList(); return; }
  // 切换批次时重置详情态，避免上一批次的数据/对比/Allure 驻留
  compared.value = false; baselineCases.value = []; allureSrc.value = ""; allureLoading.value = false; activeTab.value = "detail";
  loading.value = true;
  try {
    const resp = await api.getRunCases(runId.value);
    cases.value = resp.items;
    stats.value = resp.stats;
    total.value = resp.total;
    try { batch.value = await api.getRun(runId.value); } catch { batch.value = null; }  // cli 批次取不到内存详情
    // 加载候选基线批次（失败不阻断主流程），默认取当前批次之前最近的一次
    try {
      runs.value = await api.listRuns(50);
      pickDefaultBaseline();
    } catch { runs.value = []; }
  } finally {
    loading.value = false;
  }
}

/* ================= 与上批次对比：基线选择 + 用例级 diff ================= */
function pickDefaultBaseline() {
  const curStart = batch.value?.started_at ?? "";
  // listRuns 已按时间倒序；取早于当前批次、且非自身的最近一次
  const older = runs.value.filter(
    (r) => r.run_id !== runId.value && (!curStart || (r.started_at ?? "") <= curStart));
  baselineRunId.value =
    older[0]?.run_id ?? runs.value.find((r) => r.run_id !== runId.value)?.run_id ?? "";
}

async function loadCompare() {
  if (!baselineRunId.value) return;
  baselineLoading.value = true;
  try {
    const resp = await api.getRunCases(baselineRunId.value);
    baselineCases.value = resp.items;
    compared.value = true;
  } finally {
    baselineLoading.value = false;
  }
}

const baselineOptions = computed(() =>
  runs.value.filter((r) => r.run_id !== runId.value).map((r) => ({
    value: r.run_id,
    label: `${r.run_id}　${r.started_at ?? ""}（${r.status}）`,
  })));

const isFail = (s?: string) => !!s && FAILED_STATUSES.includes(s);

/** 基线通过率（用于通过率增减），无基线明细时为 null */
const baselinePassRate = computed(() => {
  const t = baselineCases.value.length;
  if (!t) return null;
  return Math.round((baselineCases.value.filter((c) => c.status === "passed").length / t) * 100);
});
const passRateDelta = computed(() =>
  baselinePassRate.value == null ? null : passRate.value - baselinePassRate.value);

interface DiffRow {
  case_id: string;
  name: string;
  priority: string;
  from: string;   // 基线状态，"—" 表示基线无此用例
  to: string;     // 当前状态，"—" 表示当前无此用例
  type: "regression" | "fixed" | "persistent" | "added" | "removed";
}
type TagType = "danger" | "success" | "warning" | "primary" | "info";
const DIFF_META: Record<DiffRow["type"], { label: string; tag: TagType; color: string }> = {
  regression: { label: "新增失败", tag: "danger", color: "#f56c6c" },
  fixed: { label: "已修复", tag: "success", color: "#67c23a" },
  persistent: { label: "持续失败", tag: "warning", color: "#e6a23c" },
  added: { label: "新增用例", tag: "primary", color: "#409eff" },
  removed: { label: "已移除", tag: "info", color: "#909399" },
};
const DIFF_ORDER: DiffRow["type"][] = ["regression", "fixed", "persistent", "added", "removed"];

const diffRows = computed<DiffRow[]>(() => {
  if (!compared.value) return [];
  const curMap = new Map(cases.value.map((c) => [c.case_id, c]));
  const baseMap = new Map(baselineCases.value.map((c) => [c.case_id, c]));
  const rows: DiffRow[] = [];
  const row = (id: string, c: RunCaseSummary | undefined, b: RunCaseSummary | undefined,
    type: DiffRow["type"]): DiffRow => ({
    case_id: id,
    name: c?.name ?? b?.name ?? "",
    priority: c?.priority ?? b?.priority ?? "",
    from: b ? b.status : "—",
    to: c ? c.status : "—",
    type,
  });
  for (const [id, c] of curMap) {
    const b = baseMap.get(id);
    if (!b) { rows.push(row(id, c, b, "added")); continue; }
    if (isFail(c.status) && !isFail(b.status)) rows.push(row(id, c, b, "regression"));
    else if (!isFail(c.status) && isFail(b.status)) rows.push(row(id, c, b, "fixed"));
    else if (isFail(c.status) && isFail(b.status)) rows.push(row(id, c, b, "persistent"));
  }
  for (const [id, b] of baseMap) if (!curMap.has(id)) rows.push(row(id, undefined, b, "removed"));
  return rows.sort((a, b) => DIFF_ORDER.indexOf(a.type) - DIFF_ORDER.indexOf(b.type)
    || a.case_id.localeCompare(b.case_id));
});

const diffStats = computed(() => {
  const m: Record<DiffRow["type"], number> = { regression: 0, fixed: 0, persistent: 0, added: 0, removed: 0 };
  for (const r of diffRows.value) m[r.type]++;
  return m;
});
const hasBaseline = computed(() => !!baselineRunId.value && compared.value);


function onTabChange(name: string) {
  if (name === "allure" && !allureSrc.value) {
    allureLoading.value = true;
    allureSrc.value = api.reportUrl(runId.value);
  }
  if (name === "compare" && !compared.value && !baselineLoading.value) {
    loadCompare();
  }
}

function onBaselineChange() {
  compared.value = false;
  baselineCases.value = [];
  loadCompare();
}

const durFmt = (ms: number) => (ms / 1000).toFixed(2) + "s";
const fmt = (v: unknown) => (v == null ? "—" : JSON.stringify(v, null, 2));
const strVal = (v: unknown) => (v == null ? "—" : typeof v === "object" ? JSON.stringify(v) : String(v));

onMounted(load);
// 同一 /report 路由下 query.runId 变化（列表→详情、重跑回跳）不会重新挂载，靠 watch 重载
watch(runId, () => load());
</script>

<template>
  <div v-loading="loading">
    <!-- 批次列表落地页（无 runId，侧栏“报告详情”入口） -->
    <div v-if="listMode">
      <div class="page-title">报告详情</div>
      <div class="page-desc">选择一个批次查看用例明细、失败归类、Allure 报告与上批次对比。</div>
      <div class="list-actions">
        <el-button size="small" @click="loadRunList">⟳ 刷新</el-button>
        <el-button size="small" type="primary" @click="router.push('/execution')">🚀 去执行中心发起新批次</el-button>
      </div>
      <el-card shadow="never" style="margin-top: 12px">
        <el-table :data="runList" size="small" row-key="run_id">
          <el-table-column label="批次" min-width="240">
            <template #default="{ row }">
              <div class="mono">{{ row.run_id }}</div>
              <div class="case-name">{{ argsText(row.args) }}</div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }"><el-tag :type="runStatusType(row.status)" size="small">{{ row.status }}</el-tag></template>
          </el-table-column>
          <el-table-column label="来源" width="90">
            <template #default="{ row }"><el-tag size="small" :type="row.source === 'api' ? 'primary' : 'info'">{{ row.source }}</el-tag></template>
          </el-table-column>
          <el-table-column label="开始时间" width="190">
            <template #default="{ row }"><span class="mono">{{ row.started_at ?? "—" }}</span></template>
          </el-table-column>
          <el-table-column label="操作" width="130" fixed="right">
            <template #default="{ row }">
              <el-button size="small" text type="primary" @click="openRun(row.run_id)">查看报告 ›</el-button>
            </template>
          </el-table-column>
          <template #empty><span style="color: #909399">暂无批次，去执行中心跑一次吧。</span></template>
        </el-table>
      </el-card>
    </div>

    <template v-else>
    <!-- 批次概览头 -->
    <div class="batch-head">
      <div class="batch-head-left">
        <el-button size="small" @click="router.back()">‹ 返回</el-button>
        <span class="page-title">批次报告</span>
        <el-tag v-if="batch?.args?.env" size="small" type="primary">{{ batch.args.env }}</el-tag>
        <el-tag size="small" :type="batch?.source === 'api' ? 'primary' : 'info'">{{ batch?.source ?? 'cli' }}</el-tag>
        <span class="mono rid">{{ runId }}</span>
        <span v-if="batch?.started_at" class="dim">{{ batch.started_at }}</span>
      </div>
      <div class="batch-head-right">
        <el-button type="danger" plain size="small" :disabled="!batch" @click="rerunBatch">⟳ 重跑该批次条件</el-button>
      </div>
    </div>

    <!-- KPI 卡 -->
    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="6"><el-card shadow="never" class="kpi"><div class="label">用例总数</div><div class="value">{{ total }}</div></el-card></el-col>
      <el-col :span="6"><el-card shadow="never" class="kpi"><div class="label">通过</div><div class="value ok">{{ stats.passed ?? 0 }}</div></el-card></el-col>
      <el-col :span="6"><el-card shadow="never" class="kpi"><div class="label">失败</div><div class="value fail">{{ failedCount }}</div></el-card></el-col>
      <el-col :span="6"><el-card shadow="never" class="kpi"><div class="label">通过率</div><div class="value" :style="{ color: passRate >= 100 ? '#67c23a' : passRate >= 60 ? '#e6a23c' : '#f56c6c' }">{{ passRate }}%</div><div v-if="passRateDelta != null" class="kpi-trend" :style="{ color: passRateDelta > 0 ? '#67c23a' : passRateDelta < 0 ? '#f56c6c' : '#909399' }">{{ passRateDelta > 0 ? "▲ +" : passRateDelta < 0 ? "▼ " : "＝ " }}{{ passRateDelta }}% 较基线</div></el-card></el-col>
    </el-row>

    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <el-tab-pane label="用例明细（平台视图）" name="detail">
        <el-card shadow="never">
          <div class="filter-bar">
            <el-select v-model="filterStatus" multiple collapse-tags placeholder="全部状态" style="width: 180px">
              <el-option v-for="s in statusOptions" :key="s" :label="s" :value="s" />
            </el-select>
            <el-select v-model="filterPrio" multiple collapse-tags placeholder="全部优先级" style="width: 150px">
              <el-option v-for="p in prioOptions" :key="p" :label="p" :value="p" />
            </el-select>
            <el-input v-model="filterKw" placeholder="编号/名称" clearable style="width: 200px" />
            <el-button @click="toggleOnlyFailed">仅看失败</el-button>
            <el-button v-if="hasFilter" text type="primary" @click="clearFilter">清除筛选</el-button>
            <span class="filter-count">显示 {{ filteredCases.length }} / 共 {{ total }} 条 · 失败已置顶</span>
          </div>
          <el-table :data="filteredCases" size="small" row-key="case_id">
            <el-table-column label="状态" width="80">
              <template #default="{ row }"><el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag></template>
            </el-table-column>
            <el-table-column label="用例" min-width="240">
              <template #default="{ row }">
                <div class="mono">{{ row.case_id }}</div>
                <div class="case-name">{{ row.name }}</div>
              </template>
            </el-table-column>
            <el-table-column prop="priority" label="优先级" width="80" />
            <el-table-column label="结果摘要" min-width="260">
              <template #default="{ row }">
                <span :class="['summary', FAILED_STATUSES.includes(row.status) ? 'txt-fail' : 'txt-ok']">{{ row.summary || row.status }}</span>
              </template>
            </el-table-column>
            <el-table-column label="耗时" width="90">
              <template #default="{ row }">{{ durFmt(row.duration_ms) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="180" fixed="right">
              <template #default="{ row }">
                <div class="op-cell">
                  <el-button size="small" text type="primary" @click="openDetail(row)">详情</el-button>
                  <el-button
                    v-if="FAILED_STATUSES.includes(row.status)"
                    size="small"
                    text
                    type="warning"
                    @click="rerunCase(row)"
                  >重跑此用例</el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
          <div style="margin-top: 8px; color: #909399; font-size: 12px">
            数据源：批次 allure-results ｜ Authorization / 用户 ID / 预签名已由后端统一掩码
          </div>
        </el-card>

        <!-- 失败归类 -->
        <el-card v-if="hasFailures" shadow="never" style="margin-top: 12px" header="失败归类（本批次）">
          <div class="fail-cats">
            <div v-for="c in failCats" :key="c.label" class="fail-cat">
              <i :style="{ background: c.color }" />
              <b>{{ c.label }}</b> {{ c.count }}
              <span v-if="c.hint" class="cat-hint">{{ c.hint }}</span>
            </div>
          </div>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="Allure 中文报告（内嵌）" name="allure">
        <el-alert
          v-if="allureLoading"
          type="info"
          :closable="false"
          title="首次打开需现场生成单文件报告，可能需要 10~60 秒…"
          style="margin-bottom: 8px"
        />
        <iframe
          v-if="allureSrc"
          :src="allureSrc"
          @load="allureLoading = false"
          style="width: 100%; height: calc(100vh - 260px); border: 1px solid #e4e7ed; border-radius: 6px; background: #fff"
        />
      </el-tab-pane>

      <el-tab-pane label="与上批次对比" name="compare">
        <el-card shadow="never" v-loading="baselineLoading">
          <div class="filter-bar">
            <span style="font-size: 13px; color: #606266">基线批次</span>
            <el-select
              v-model="baselineRunId"
              filterable
              placeholder="选择对比的基线批次"
              style="width: 420px"
              @change="onBaselineChange"
            >
              <el-option v-for="o in baselineOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <el-button :disabled="!baselineRunId" @click="loadCompare">重新对比</el-button>
            <span v-if="passRateDelta != null" class="filter-count">
              通过率较基线
              <b :style="{ color: passRateDelta > 0 ? '#67c23a' : passRateDelta < 0 ? '#f56c6c' : '#909399' }">
                {{ passRateDelta > 0 ? "▲ +" : passRateDelta < 0 ? "▼ " : "＝ " }}{{ passRateDelta }}%
              </b>
            </span>
          </div>

          <div v-if="!baselineOptions.length" class="dim">
            没有其他批次可供对比。
          </div>
          <template v-else-if="hasBaseline">
            <div class="diff-stats">
              <div v-for="t in DIFF_ORDER" :key="t" class="diff-chip" :style="{ borderColor: DIFF_META[t].color }">
                <span class="dot" :style="{ background: DIFF_META[t].color }" />
                <b>{{ DIFF_META[t].label }}</b>
                <span class="diff-count">{{ diffStats[t] }}</span>
              </div>
            </div>

            <el-table v-if="diffRows.length" :data="diffRows" size="small" row-key="case_id" style="margin-top: 12px">
              <el-table-column label="变化" width="110">
                <template #default="{ row }"><el-tag :type="DIFF_META[row.type].tag" size="small">{{ DIFF_META[row.type].label }}</el-tag></template>
              </el-table-column>
              <el-table-column label="用例" min-width="240">
                <template #default="{ row }">
                  <div class="mono">{{ row.case_id }}</div>
                  <div class="case-name">{{ row.name }}</div>
                </template>
              </el-table-column>
              <el-table-column prop="priority" label="优先级" width="80" />
              <el-table-column label="基线 → 当前" width="200">
                <template #default="{ row }">
                  <el-tag :type="row.from === '—' ? 'info' : statusType(row.from)" size="small">{{ row.from }}</el-tag>
                  <span style="margin: 0 6px">→</span>
                  <el-tag :type="row.to === '—' ? 'info' : statusType(row.to)" size="small">{{ row.to }}</el-tag>
                </template>
              </el-table-column>
            </el-table>
            <el-alert
              v-else
              type="success"
              :closable="false"
              show-icon
              title="与基线批次逐条一致，无新增失败 / 修复 / 用例增减。"
            />
          </template>
          <div v-else-if="!baselineLoading" class="dim">请选择基线批次后开始对比。</div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 执行详情抽屉：请求 / 响应 / 断言逐条 / 日志 -->
    <el-drawer v-model="detailVisible" size="620px" :title="detail?.case_id ? detail.case_id + ' · 执行详情' : '执行详情'">
      <div v-loading="detailLoading" style="min-height: 240px">
        <el-tabs v-if="detail" v-model="detailTab">
          <el-tab-pane label="请求快照" name="req">
            <pre class="json">{{ fmt(detail.request) }}</pre>
          </el-tab-pane>
          <el-tab-pane label="响应快照" name="resp">
            <pre class="json">{{ fmt(detail.response) }}</pre>
          </el-tab-pane>
          <el-tab-pane label="断言结果" name="assert">
            <el-table v-if="detail.assertions && detail.assertions.length" :data="detail.assertions" size="small">
              <el-table-column prop="op" label="操作符" width="90" />
              <el-table-column prop="path" label="取值路径" min-width="150">
                <template #default="{ row }"><span class="mono">{{ row.path }}</span></template>
              </el-table-column>
              <el-table-column label="期望" min-width="110">
                <template #default="{ row }"><span class="mono">{{ strVal(row.expected) }}</span></template>
              </el-table-column>
              <el-table-column label="实际" min-width="110">
                <template #default="{ row }"><span class="mono">{{ strVal(row.actual) }}</span></template>
              </el-table-column>
              <el-table-column label="结果" width="70">
                <template #default="{ row }">
                  <el-tag :type="row.passed ? 'success' : 'danger'" size="small">{{ row.passed ? "✓" : "✗" }}</el-tag>
                </template>
              </el-table-column>
            </el-table>
            <el-alert
              v-else
              type="info"
              :closable="false"
              show-icon
              title="该批次未记录逐条断言明细（早期数据或请求异常未进入断言）。可切「日志」查看失败信息。"
            />
            <div v-if="detail.error" class="fail-line mono">{{ detail.error.split("\n")[0] }}</div>
          </el-tab-pane>
          <el-tab-pane label="日志" name="log">
            <div v-if="detail.error" class="fail-line mono" style="margin-top: 0">{{ detail.error }}</div>
            <pre v-if="detail.trace" class="json" style="max-height: 360px">{{ detail.trace }}</pre>
            <span v-if="!detail.error && !detail.trace" style="color: #909399">无异常日志</span>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-drawer>
    </template>
  </div>
</template>

<style scoped>
.mono { font-family: Consolas, Monaco, monospace; }
.page-title { font-size: 16px; font-weight: 600; }
.batch-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.batch-head-left { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.batch-head-right { display: flex; align-items: center; gap: 8px; }
.rid { font-size: 12px; color: #909399; word-break: break-all; }
.dim { color: #909399; font-size: 13px; }
.kpi { text-align: center; }
.kpi .label { color: #909399; font-size: 13px; }
.kpi .value { font-size: 26px; font-weight: 700; margin-top: 4px; }
.kpi .value.ok { color: #67c23a; }
.kpi .value.fail { color: #f56c6c; }
.filter-bar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.filter-count { margin-left: auto; color: #909399; font-size: 12px; }
.page-desc { color: #909399; font-size: 13px; margin: 4px 0 12px; }
.list-actions { display: flex; gap: 8px; }
.case-name { color: #909399; font-size: 12px; }
.summary { font-size: 12px; }
.txt-fail { color: #f56c6c; }
.txt-ok { color: #606266; }
.op-cell { display: flex; align-items: center; gap: 2px; white-space: nowrap; }
.op-cell .el-button + .el-button { margin-left: 0; }
.fail-cats { display: flex; gap: 24px; flex-wrap: wrap; font-size: 13px; }
.fail-cat { display: flex; align-items: center; gap: 6px; }
.fail-cat i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; }
.cat-hint { color: #e6a23c; font-size: 12px; }
.kpi-trend { font-size: 12px; margin-top: 2px; }
.diff-stats { display: flex; gap: 12px; flex-wrap: wrap; }
.diff-chip { display: flex; align-items: center; gap: 6px; border: 1px solid; border-radius: 6px; padding: 8px 14px; font-size: 13px; }
.diff-chip .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; }
.diff-count { font-size: 18px; font-weight: 700; margin-left: 2px; }
.json { background: #f8f9fb; border: 1px solid #e4e7ed; border-radius: 6px; padding: 10px 12px; font-family: Consolas, Monaco, monospace; font-size: 12px; line-height: 1.6; white-space: pre-wrap; word-break: break-all; max-height: 460px; overflow: auto; margin: 0; }
.fail-line { background: #fef0f0; border: 1px solid #fde2e2; border-radius: 4px; padding: 8px 12px; color: #f56c6c; font-size: 12px; margin-top: 12px; white-space: pre-wrap; word-break: break-all; }
</style>
