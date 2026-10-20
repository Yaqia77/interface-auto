<script setup lang="ts">
/**
 * 统计报表：纯前端聚合，跨批次通过率趋势 / 模块分布 / 优先级分布 / 耗时 TOP。
 * 数据源：listRuns(100) + getRunCases(×N) + listCases({})。
 */
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api";
import type { RunCaseSummary, RunItem } from "../types";

const router = useRouter();

/* ============ 数据加载 ============ */
const batchLimit = ref(20);
const loading = ref(false);
// batchCases 按时间新→旧排列（与 listRuns 返回顺序一致）
const batchCases = ref<{ run: RunItem; items: RunCaseSummary[] }[]>([]);
const caseModuleMap = ref<Map<string, string>>(new Map());

async function load() {
  loading.value = true;
  try {
    // case_id → module 映射（全量用例）
    const allCases = await api.listCases({});
    const m = new Map<string, string>();
    for (const c of allCases.items) m.set(c.case_id, c.module);
    caseModuleMap.value = m;

    // 近 N 个已完成批次
    const runs = await api.listRuns(100);
    const finished = runs
      .filter((r) => ["passed", "failed"].includes(r.status))
      .slice(0, batchLimit.value);

    const results = await Promise.all(
      finished.map((r) => api.getRunCases(r.run_id).then((x) => x.items).catch(() => null)),
    );
    batchCases.value = finished
      .map((run, i) => ({ run, items: results[i] ?? [] }))
      .filter((x) => x.items.length > 0);
  } finally {
    loading.value = false;
  }
}

/* ============ KPI ============ */
const FAILED = new Set(["failed", "broken"]);

const kpi = computed(() => {
  let total = 0, passed = 0, failed = 0;
  for (const bc of batchCases.value) {
    total += bc.items.length;
    passed += bc.items.filter((i) => i.status === "passed").length;
    failed += bc.items.filter((i) => FAILED.has(i.status)).length;
  }
  return {
    batches: batchCases.value.length,
    total,
    passed,
    failed,
    passRate: total ? Math.round((passed / total) * 100) : 0,
  };
});

/* ============ 趋势（旧 → 新，用于图表） ============ */
interface TrendPoint {
  runId: string;
  label: string;
  total: number;
  passed: number;
  failed: number;
  rate: number;
}

const trendData = computed<TrendPoint[]>(() =>
  batchCases.value
    .slice()
    .reverse()
    .map((bc) => {
      const total = bc.items.length;
      const passed = bc.items.filter((i) => i.status === "passed").length;
      const failed = bc.items.filter((i) => FAILED.has(i.status)).length;
      return {
        runId: bc.run.run_id,
        label: (bc.run.started_at ?? "").replace("T", " ").slice(5, 16),
        total,
        passed,
        failed,
        rate: total ? passed / total : 0,
      };
    }),
);

// SVG 布局常量
const X0 = 36, X1 = 466, Y0 = 22, Y1 = 122; // viewBox 0 0 500 144

function toX(i: number, n: number): number {
  return n === 1 ? (X0 + X1) / 2 : X0 + (i / (n - 1)) * (X1 - X0);
}
function toY(rate: number): number {
  return Y0 + (1 - rate) * (Y1 - Y0);
}

const svgPolyline = computed(() => {
  const d = trendData.value;
  if (!d.length) return "";
  return d.map((p, i) => `${toX(i, d.length).toFixed(1)},${toY(p.rate).toFixed(1)}`).join(" ");
});

const svgArea = computed(() => {
  const d = trendData.value;
  if (d.length < 2) return "";
  const pts = d.map((p, i) => `${toX(i, d.length).toFixed(1)},${toY(p.rate).toFixed(1)}`);
  return `${X0},${Y1} ${pts.join(" ")} ${X1},${Y1}`;
});

const svgDots = computed(() => {
  const d = trendData.value;
  return d.map((p, i) => ({
    cx: +toX(i, d.length).toFixed(1),
    cy: +toY(p.rate).toFixed(1),
    ...p,
  }));
});

/* ============ 模块分布 ============ */
const moduleStats = computed(() => {
  const map = new Map<string, { total: number; passed: number; failed: number }>();
  for (const bc of batchCases.value) {
    for (const item of bc.items) {
      const mod = caseModuleMap.value.get(item.case_id) ?? "未分类";
      const rec = map.get(mod) ?? { total: 0, passed: 0, failed: 0 };
      rec.total++;
      if (item.status === "passed") rec.passed++;
      else if (FAILED.has(item.status)) rec.failed++;
      map.set(mod, rec);
    }
  }
  return [...map.entries()]
    .map(([mod, v]) => ({ mod, ...v, passRate: v.total ? v.passed / v.total : 0 }))
    .sort((a, b) => b.failed - a.failed || b.total - a.total);
});

/* ============ 优先级分布 ============ */
const priorityStats = computed(() => {
  const map = new Map<string, { total: number; passed: number; failed: number }>();
  for (const bc of batchCases.value) {
    for (const item of bc.items) {
      const p = item.priority || "?";
      const rec = map.get(p) ?? { total: 0, passed: 0, failed: 0 };
      rec.total++;
      if (item.status === "passed") rec.passed++;
      else if (FAILED.has(item.status)) rec.failed++;
      map.set(p, rec);
    }
  }
  return [...map.entries()]
    .map(([priority, v]) => ({ priority, ...v, passRate: v.total ? v.passed / v.total : 0 }))
    .sort((a, b) => a.priority.localeCompare(b.priority));
});

/* ============ 耗时 TOP（最新批次） ============ */
const durationTop = computed(() => {
  if (!batchCases.value.length) return [];
  const latest = batchCases.value[0];
  return latest.items
    .slice()
    .sort((a, b) => b.duration_ms - a.duration_ms)
    .slice(0, 8)
    .map((i) => ({
      case_id: i.case_id,
      name: i.name,
      status: i.status,
      duration_ms: i.duration_ms,
      mod: caseModuleMap.value.get(i.case_id) ?? "未分类",
    }));
});

const durMax = computed(() =>
  Math.max(1, ...durationTop.value.map((d) => d.duration_ms)),
);

const fmtDur = (ms: number) => (ms >= 1000 ? (ms / 1000).toFixed(2) + "s" : ms + "ms");
const fmtRate = (r: number) => Math.round(r * 100) + "%";
const toReport = (runId: string) => router.push({ path: "/report", query: { runId } });

onMounted(load);
</script>

<template>
  <div v-loading="loading" class="stats-page">
    <!-- 工具栏 -->
    <div class="toolbar">
      <el-select v-model="batchLimit" size="small" style="width: 110px" @change="load">
        <el-option :value="10" label="近 10 批" />
        <el-option :value="20" label="近 20 批" />
        <el-option :value="50" label="近 50 批" />
      </el-select>
      <el-button size="small" plain :loading="loading" @click="load">刷新</el-button>
      <span class="tip-note">并发拉取各批次明细，数据多时加载约 2-4 秒</span>
    </div>

    <!-- KPI 行 -->
    <el-row :gutter="10" class="kpi-row">
      <el-col :span="6">
        <el-card shadow="never" class="kpi-card">
          <div class="kpi-num">{{ kpi.batches }}</div>
          <div class="kpi-lbl">已完成批次</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="kpi-card">
          <div class="kpi-num">{{ kpi.total }}</div>
          <div class="kpi-lbl">总执行次数</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="kpi-card">
          <div class="kpi-num" style="color: #67c23a">{{ kpi.passRate }}%</div>
          <div class="kpi-lbl">综合通过率</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="kpi-card">
          <div class="kpi-num" style="color: #f56c6c">{{ kpi.failed }}</div>
          <div class="kpi-lbl">失败总次数</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 通过率趋势 -->
    <el-card shadow="never" class="section-card" header="通过率趋势（旧 → 新）">
      <template v-if="trendData.length">
        <svg viewBox="0 0 500 144" class="trend-svg" preserveAspectRatio="xMidYMid meet">
          <!-- 网格线 -->
          <line :x1="X0" :y1="Y0" :x2="X1" :y2="Y0" stroke="#f0f0f0" stroke-width="1" />
          <line :x1="X0" :y1="(Y0+Y1)/2" :x2="X1" :y2="(Y0+Y1)/2" stroke="#f0f0f0" stroke-width="1" stroke-dasharray="4 2" />
          <line :x1="X0" :y1="Y1" :x2="X1" :y2="Y1" stroke="#e8e8e8" stroke-width="1" />
          <!-- Y 轴标签 -->
          <text :x="X0 - 4" :y="Y0 + 4" text-anchor="end" font-size="10" fill="#bbb">100%</text>
          <text :x="X0 - 4" :y="(Y0+Y1)/2 + 4" text-anchor="end" font-size="10" fill="#bbb">50%</text>
          <text :x="X0 - 4" :y="Y1 + 4" text-anchor="end" font-size="10" fill="#bbb">0%</text>
          <!-- 填充区域（仅 ≥2 个点时绘制） -->
          <polygon v-if="svgArea" :points="svgArea" fill="rgba(64,158,255,0.07)" />
          <!-- 折线 -->
          <polyline :points="svgPolyline" fill="none" stroke="#409eff" stroke-width="2"
            stroke-linejoin="round" stroke-linecap="round" />
          <!-- 数据点 -->
          <circle
            v-for="d in svgDots"
            :key="d.runId"
            :cx="d.cx"
            :cy="d.cy"
            r="5"
            fill="#409eff"
            stroke="#fff"
            stroke-width="1.5"
            class="dot"
            @click="toReport(d.runId)"
          >
            <title>{{ d.label }}  {{ fmtRate(d.rate) }}（{{ d.passed }}/{{ d.total }}）</title>
          </circle>
        </svg>
        <div class="chart-footer">
          <span>共 {{ trendData.length }} 批</span>
          <span class="footer-cur">
            最新：{{ trendData[trendData.length - 1]?.label }}
            <strong :class="(trendData[trendData.length - 1]?.rate ?? 0) < 0.8 ? 'txt-fail' : 'txt-ok'">
              {{ fmtRate(trendData[trendData.length - 1]?.rate ?? 0) }}
            </strong>
          </span>
          <span class="footer-hint">点击数据点可跳转至该批次报告</span>
        </div>
      </template>
      <el-empty v-else description="暂无已完成批次数据" :image-size="60" />
    </el-card>

    <!-- 模块 + 优先级 -->
    <el-row :gutter="10">
      <!-- 模块分布 -->
      <el-col :span="14">
        <el-card shadow="never" class="section-card" header="模块通过率（跨批次累计）">
          <template v-if="moduleStats.length">
            <div v-for="s in moduleStats.slice(0, 12)" :key="s.mod" class="bar-row">
              <span class="bar-mod" :title="s.mod">{{ s.mod }}</span>
              <div class="bar-track">
                <div class="bar-pass" :style="{ width: (s.passed / Math.max(1, s.total)) * 100 + '%' }" />
                <div class="bar-fail" :style="{ width: (s.failed / Math.max(1, s.total)) * 100 + '%' }" />
              </div>
              <span class="bar-rate" :class="s.passRate >= 0.8 ? 'txt-ok' : 'txt-fail'">
                {{ fmtRate(s.passRate) }}
              </span>
              <span class="bar-cnt">{{ s.total }}</span>
            </div>
          </template>
          <el-empty v-else :image-size="50" description="无数据" />
        </el-card>
      </el-col>

      <!-- 优先级分布 -->
      <el-col :span="10">
        <el-card shadow="never" class="section-card" header="优先级通过率">
          <template v-if="priorityStats.length">
            <div v-for="s in priorityStats" :key="s.priority" class="bar-row">
              <span class="bar-pri">{{ s.priority }}</span>
              <div class="bar-track">
                <div class="bar-pass" :style="{ width: (s.passed / Math.max(1, s.total)) * 100 + '%' }" />
                <div class="bar-fail" :style="{ width: (s.failed / Math.max(1, s.total)) * 100 + '%' }" />
              </div>
              <span class="bar-rate" :class="s.passRate >= 0.8 ? 'txt-ok' : 'txt-fail'">
                {{ fmtRate(s.passRate) }}
              </span>
              <span class="bar-cnt">{{ s.total }}</span>
            </div>
          </template>
          <el-empty v-else :image-size="50" description="无数据" />
        </el-card>

        <!-- 最新批次耗时 TOP -->
        <el-card shadow="never" class="section-card" style="margin-top: 10px" header="最新批次耗时 TOP">
          <template v-if="durationTop.length">
            <div v-for="d in durationTop" :key="d.case_id" class="dur-row">
              <el-tag
                size="small"
                :type="d.status === 'passed' ? 'success' : 'danger'"
                class="dur-tag"
              >{{ d.status === "passed" ? "✓" : "✗" }}</el-tag>
              <span class="dur-name" :title="`${d.case_id} · ${d.name}`">{{ d.case_id }}</span>
              <div class="dur-track">
                <div
                  class="dur-bar"
                  :class="d.status !== 'passed' ? 'dur-bar-fail' : ''"
                  :style="{ width: (d.duration_ms / durMax) * 100 + '%' }"
                />
              </div>
              <span class="dur-val">{{ fmtDur(d.duration_ms) }}</span>
            </div>
          </template>
          <el-empty v-else :image-size="50" description="无数据" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.stats-page { display: flex; flex-direction: column; gap: 10px; }

.toolbar { display: flex; align-items: center; gap: 8px; }
.tip-note { font-size: 12px; color: #c0c4cc; }

/* KPI */
.kpi-row { margin: 0; }
.kpi-card { text-align: center; padding: 4px 0; }
.kpi-num { font-size: 28px; font-weight: 700; line-height: 1.2; color: #303133; }
.kpi-lbl { font-size: 12px; color: #909399; margin-top: 4px; }

/* Section */
.section-card { margin: 0; }
.section-card :deep(.el-card__header) { padding: 10px 16px; font-size: 13px; font-weight: 600; }
.section-card :deep(.el-card__body) { padding: 12px 16px; }

/* SVG 趋势 */
.trend-svg { width: 100%; height: auto; display: block; }
.dot { cursor: pointer; transition: opacity 0.12s ease; }
.dot:hover { opacity: 0.75; }
.chart-footer { display: flex; gap: 16px; margin-top: 6px; font-size: 12px; color: #909399; }
.footer-cur { color: #606266; }
.footer-hint { margin-left: auto; }

/* 横向分布条 */
.bar-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.bar-mod { font-size: 12px; color: #606266; width: 96px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex-shrink: 0; }
.bar-pri { font-size: 12px; color: #606266; width: 36px; text-align: center; flex-shrink: 0; }
.bar-track { flex: 1; height: 14px; background: #f2f3f5; border-radius: 3px; overflow: hidden; display: flex; }
.bar-pass { background: #67c23a; height: 100%; }
.bar-fail { background: #f56c6c; height: 100%; }
.bar-rate { font-size: 11px; width: 36px; text-align: right; flex-shrink: 0; font-weight: 600; }
.bar-cnt { font-size: 10px; color: #c0c4cc; width: 22px; text-align: right; flex-shrink: 0; }

/* 耗时行 */
.dur-row { display: flex; align-items: center; gap: 6px; margin-bottom: 5px; }
.dur-tag { flex-shrink: 0; }
.dur-name { font-size: 11px; color: #606266; width: 110px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex-shrink: 0; }
.dur-track { flex: 1; height: 10px; background: #f2f3f5; border-radius: 2px; overflow: hidden; }
.dur-bar { background: #409eff; height: 100%; border-radius: 2px; }
.dur-bar-fail { background: #e6a23c; }
.dur-val { font-size: 11px; color: #909399; width: 54px; text-align: right; flex-shrink: 0; }

/* 颜色 */
.txt-ok { color: #67c23a; }
.txt-fail { color: #f56c6c; }
</style>
