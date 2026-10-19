<script setup lang="ts">
/** 执行中心：发起批次 → 轮询日志 → 查看/打开中文 Allure 报告。 */
import { onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api";
import type { EnvInfo, RunItem } from "../types";

const form = reactive({
  env: "",
  priority: "",
  module: "",
  keyword: "",
  file: "data/api_cases.xlsx",
});

const envs = ref<EnvInfo[]>([]);
const launching = ref(false);
const current = ref<RunItem | null>(null);
const logText = ref("");
const runs = ref<RunItem[]>([]);
let timer: number | undefined;

const statusType = (s: string) =>
  (({ running: "warning", passed: "success", failed: "danger", error: "danger", unknown: "info" } as Record<string, any>)[s] ?? "info");

async function loadRuns() {
  runs.value = await api.listRuns(20);
}

async function start() {
  launching.value = true;
  try {
    const run = await api.createRun({
      env: form.env || undefined,
      priority: form.priority || undefined,
      module: form.module || undefined,
      keyword: form.keyword || undefined,
      file: form.file,
    });
    current.value = run;
    logText.value = "";
    ElMessage.success(`批次已受理：${run.run_id}`);
    startPolling(run.run_id);
    loadRuns();
  } finally {
    launching.value = false;
  }
}

function startPolling(runId: string) {
  stopPolling();
  timer = window.setInterval(async () => {
    try {
      const [detail, log] = await Promise.all([api.getRun(runId), api.getRunLog(runId)]);
      current.value = detail;
      logText.value = log.log;
      if (detail.status !== "running") {
        stopPolling();
        loadRuns();
        ElMessage[detail.status === "passed" ? "success" : "warning"](`批次结束：${detail.status}`);
      }
    } catch {
      stopPolling();
    }
  }, 2000);
}

function stopPolling() {
  if (timer) {
    clearInterval(timer);
    timer = undefined;
  }
}

function openReport(runId: string) {
  // 模板里没有 window 作用域，统一走这里
  window.open(api.reportUrl(runId), "_blank");
}

function watchRun(run: RunItem) {
  if (run.source !== "api") {
    // cli 历史批次没有内存日志，直接给报告入口
    openReport(run.run_id);
    return;
  }
  current.value = run;
  startPolling(run.run_id);
}

onMounted(async () => {
  loadRuns();
  const resp = await api.listEnvs();
  envs.value = resp.envs;
  form.env = resp.default_env ?? "";
});

onBeforeUnmount(stopPolling);
</script>

<template>
  <div>
    <el-row :gutter="12">
      <el-col :span="8">
        <el-card shadow="never" header="发起执行">
          <el-form label-width="80px" @submit.prevent>
            <el-form-item label="环境">
              <el-select v-model="form.env" style="width: 100%">
                <el-option v-for="e in envs" :key="e.name" :label="`${e.name}（${e.base_url}）`" :value="e.name" />
              </el-select>
            </el-form-item>
            <el-form-item label="优先级">
              <el-input v-model="form.priority" placeholder="如 P0 或 P0,P1（留空=全量）" />
            </el-form-item>
            <el-form-item label="模块">
              <el-input v-model="form.module" placeholder="包含匹配，留空不筛选" />
            </el-form-item>
            <el-form-item label="关键字">
              <el-input v-model="form.keyword" placeholder="编号/接口名/描述/URL" />
            </el-form-item>
            <el-form-item label="用例文件">
              <el-input v-model="form.file" />
            </el-form-item>
            <el-button type="primary" :loading="launching" style="width: 100%" @click="start">
              ▶ 开始执行
            </el-button>
          </el-form>
        </el-card>

        <el-card v-if="current" shadow="never" style="margin-top: 12px">
          <template #header>
            当前批次
            <el-tag :type="statusType(current.status)" size="small" style="margin-left: 8px">{{ current.status }}</el-tag>
            <span v-if="current.exit_code !== null" style="float: right; color: #909399; font-size: 12px">exit={{ current.exit_code }}</span>
          </template>
          <div class="mono" style="font-size: 12px; margin-bottom: 6px; word-break: break-all">{{ current.run_id }}</div>
          <pre class="console">{{ logText || "等待日志…" }}</pre>
          <el-button
            v-if="current.report_dir && ['passed', 'failed'].includes(current.status)"
            type="primary"
            size="small"
            style="margin-top: 8px"
            @click="openReport(current.run_id)"
          >
            📈 打开中文 Allure 报告
          </el-button>
        </el-card>
      </el-col>

      <el-col :span="16">
        <el-card shadow="never">
          <template #header>
            批次列表
            <el-button size="small" style="float: right" @click="loadRuns">刷新</el-button>
          </template>
          <el-table :data="runs" size="small" row-key="run_id">
            <el-table-column label="批次" min-width="200">
              <template #default="{ row }"><span class="mono">{{ row.run_id }}</span></template>
            </el-table-column>
            <el-table-column label="来源" width="70">
              <template #default="{ row }">
                <el-tag size="small" :type="row.source === 'api' ? 'primary' : 'info'">{{ row.source }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }"><el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="started_at" label="开始时间" width="150" />
            <el-table-column label="操作" width="180">
              <template #default="{ row }">
                <el-button size="small" text type="primary" @click="watchRun(row)">
                  {{ row.source === "api" ? "看日志" : "报告" }}
                </el-button>
                <el-button
                  v-if="row.source === 'api' && ['passed', 'failed'].includes(row.status)"
                  size="small"
                  text
                  type="primary"
                  @click="openReport(row.run_id)"
                >
                  报告
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <div style="margin-top: 8px; color: #909399; font-size: 12px">
            api = 平台发起（内存跟踪，可看实时日志）；cli = 本地/CI 历史运行（reports/ 目录认领，可直接出报告）
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.mono { font-family: Consolas, Monaco, monospace; }
.console {
  background: #1e2530; color: #9ab; border-radius: 6px; padding: 10px 12px;
  font-family: Consolas, Monaco, monospace; font-size: 12px; line-height: 1.6;
  height: 300px; overflow: auto; white-space: pre-wrap; word-break: break-all; margin: 0;
}
</style>
