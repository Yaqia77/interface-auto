<script setup lang="ts">
/** 批次报告页：平台原生明细（掩码后请求/响应）+ Allure 中文报告内嵌。 */
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "../api";
import type { RunCaseDetail, RunCaseSummary } from "../types";

const route = useRoute();
const router = useRouter();
// run_id 含 "/"（cli 批次），走 query 传参：/report?runId=reports/run_xxx
const runId = computed(() => (route.query.runId as string) ?? "");

const loading = ref(false);
const cases = ref<RunCaseSummary[]>([]);
const stats = ref<Record<string, number>>({});
const total = ref(0);

const activeTab = ref("detail");
const allureSrc = ref("");       // 懒加载：切到 Allure Tab 才设 src（首次现场生成可能 30s+）
const allureLoading = ref(false);

const detailVisible = ref(false);
const detail = ref<RunCaseDetail | null>(null);
const detailLoading = ref(false);

const statusType = (s: string) =>
  (({ passed: "success", failed: "danger", broken: "warning", skipped: "info" } as Record<string, any>)[s] ?? "info");

async function load() {
  if (!runId.value) return;
  loading.value = true;
  try {
    const resp = await api.getRunCases(runId.value);
    cases.value = resp.items;
    stats.value = resp.stats;
    total.value = resp.total;
  } finally {
    loading.value = false;
  }
}

async function openDetail(row: RunCaseSummary) {
  detailVisible.value = true;
  detailLoading.value = true;
  detail.value = null;
  try {
    detail.value = await api.getRunCaseDetail(runId.value, row.case_id);
  } finally {
    detailLoading.value = false;
  }
}

function onTabChange(name: string) {
  if (name === "allure" && !allureSrc.value) {
    allureLoading.value = true;
    allureSrc.value = api.reportUrl(runId.value);
    // loading 撤除交给 iframe 的 @load 事件（此时组件尚未渲染，手动 addEventListener 会落空）
  }
}

const fmt = (v: unknown) => (v == null ? "—" : JSON.stringify(v, null, 2));

onMounted(load);
</script>

<template>
  <div>
    <div style="display: flex; align-items: center; margin-bottom: 12px; gap: 12px">
      <el-button size="small" @click="router.back()">‹ 返回</el-button>
      <b>批次报告</b>
      <span class="mono" style="font-size: 12px; color: #909399; word-break: break-all">{{ runId }}</span>
      <div style="margin-left: auto; display: flex; gap: 8px">
        <el-tag type="success" size="small">通过 {{ stats.passed ?? 0 }}</el-tag>
        <el-tag type="danger" size="small">失败 {{ (stats.failed ?? 0) + (stats.broken ?? 0) }}</el-tag>
        <el-tag type="info" size="small">跳过 {{ stats.skipped ?? 0 }}</el-tag>
      </div>
    </div>

    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <el-tab-pane label="用例明细（平台视图）" name="detail">
        <el-card shadow="never">
          <el-table :data="cases" v-loading="loading" size="small" row-key="case_id">
            <el-table-column label="状态" width="90">
              <template #default="{ row }"><el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="case_id" label="用例编号" min-width="150">
              <template #default="{ row }"><span class="mono">{{ row.case_id }}</span></template>
            </el-table-column>
            <el-table-column prop="name" label="名称" min-width="220" show-overflow-tooltip />
            <el-table-column prop="priority" label="优先级" width="70" />
            <el-table-column label="耗时" width="90">
              <template #default="{ row }">{{ (row.duration_ms / 1000).toFixed(2) }}s</template>
            </el-table-column>
            <el-table-column label="失败信息" min-width="220">
              <template #default="{ row }">
                <span v-if="row.error" class="err mono">{{ row.error.split("\n")[0] }}</span>
                <span v-else style="color: #909399">—</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="110">
              <template #default="{ row }">
                <el-button size="small" text type="primary" @click="openDetail(row)">请求/响应</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div style="margin-top: 8px; color: #909399; font-size: 12px">
            共 {{ total }} 条 ｜ 数据源：批次 allure-results ｜ Authorization / 用户 ID / 预签名已由后端统一掩码
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
          style="width: 100%; height: calc(100vh - 240px); border: 1px solid #e4e7ed; border-radius: 6px; background: #fff"
        />
      </el-tab-pane>
    </el-tabs>

    <!-- 单用例明细抽屉 -->
    <el-drawer v-model="detailVisible" size="55%" :title="detail?.case_id ?? '明细'">
      <div v-loading="detailLoading" style="min-height: 200px">
        <template v-if="detail">
          <el-descriptions :column="2" border size="small" style="margin-bottom: 12px">
            <el-descriptions-item label="状态">
              <el-tag :type="statusType(detail.status)" size="small">{{ detail.status }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="用例">{{ detail.name }}</el-descriptions-item>
            <el-descriptions-item label="描述" :span="2">{{ detail.description || "—" }}</el-descriptions-item>
          </el-descriptions>

          <div v-if="detail.error" class="fail-line mono">{{ detail.error }}</div>

          <el-divider content-position="left">请求快照（已掩码）</el-divider>
          <pre class="json">{{ fmt(detail.request) }}</pre>

          <el-divider content-position="left">响应快照（已掩码·截断）</el-divider>
          <pre class="json">{{ fmt(detail.response) }}</pre>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.mono { font-family: Consolas, Monaco, monospace; }
.err { color: #f56c6c; font-size: 12px; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.json { background: #f8f9fb; border: 1px solid #e4e7ed; border-radius: 6px; padding: 10px 12px; font-family: Consolas, Monaco, monospace; font-size: 12px; line-height: 1.6; white-space: pre-wrap; word-break: break-all; max-height: 300px; overflow: auto; }
.fail-line { background: #fef0f0; border: 1px solid #fde2e2; border-radius: 4px; padding: 8px 12px; color: #f56c6c; font-size: 12px; margin-bottom: 12px; white-space: pre-wrap; word-break: break-all; }
</style>
