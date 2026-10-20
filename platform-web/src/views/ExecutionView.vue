<script setup lang="ts">
/** 执行中心：发起批次 → 轮询日志 → 查看/打开中文 Allure 报告。 */
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
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

const router = useRouter();
const route = useRoute();
const carried = ref("");   // 从用例管理携带过来的筛选条件描述（非空则顶部提示）

/** 清除预填条件（仅清从用例管理带来的三个过滤项，不动环境/文件） */
function clearCarried() {
  form.module = "";
  form.priority = "";
  form.keyword = "";
  carried.value = "";
  rangeMode.value = "filter";
  router.replace({ path: "/execution" });
}

/* ================= 范围模式：按条件筛选 / 勾选用例（树形多选） ================= */
const rangeMode = ref<"filter" | "pick">("filter");
interface TreeNode { id: string; label: string; module?: string; priority?: string; children?: TreeNode[] }
const treeRef = ref();
const treeData = ref<TreeNode[]>([]);
const treeLoading = ref(false);
const treeFilter = ref("");
const checkedIds = ref<string[]>([]);

async function loadTree() {
  if (treeData.value.length) return;      // 首次切到勾选模式才加载，后续复用
  treeLoading.value = true;
  try {
    const resp = await api.listCases({ run: true });   // 仅列出已启用（run=Y）的用例
    const byMod = new Map<string, TreeNode[]>();
    for (const c of resp.items) {
      const leaf: TreeNode = { id: c.case_id, label: `${c.case_id} · ${c.api_name}`, module: c.module, priority: c.priority };
      if (!byMod.has(c.module)) byMod.set(c.module, []);
      byMod.get(c.module)!.push(leaf);
    }
    treeData.value = [...byMod.entries()]
      .sort((a, b) => a[0].localeCompare(b[0], "zh"))
      .map(([mod, children]) => ({ id: `mod:${mod}`, label: `${mod}（${children.length}）`, module: mod, children }));
  } finally {
    treeLoading.value = false;
  }
}

function filterNode(q: string, data: TreeNode): boolean {
  if (!q) return true;
  const s = q.toLowerCase();
  return data.label.toLowerCase().includes(s) || (data.module ?? "").toLowerCase().includes(s);
}

/** 收集已勾选的叶子（用例）id；模块父节点自动排除 */
function collectIds(): string[] {
  const nodes: TreeNode[] = treeRef.value?.getCheckedNodes(true) ?? [];
  return nodes.filter((n) => !n.id.startsWith("mod:")).map((n) => n.id);
}
function onCheck() {
  checkedIds.value = collectIds();
}
watch(treeFilter, (v) => treeRef.value?.filter(v));
watch(rangeMode, (m) => { if (m === "pick") loadTree(); });
const pickedCount = computed(() => checkedIds.value.length);

/* ================= 运行前变量覆盖 ================= */
interface VarRow { key: string; value: string }
const varRows = ref<VarRow[]>([]);
const advOpen = ref<string[]>([]);
function addVarRow() { varRows.value.push({ key: "", value: "" }); }
function delVarRow(i: number) { varRows.value.splice(i, 1); }
function buildVars(): Record<string, unknown> {
  const o: Record<string, unknown> = {};
  for (const r of varRows.value) {
    const k = r.key.trim();
    if (k) o[k] = r.value;
  }
  return o;
}

const statusType = (s: string) =>
  (({ running: "warning", passed: "success", failed: "danger", error: "danger", cancelled: "info", unknown: "info" } as Record<string, any>)[s] ?? "info");

async function loadRuns() {
  runs.value = await api.listRuns(20);
}

async function start() {
  const body: Parameters<typeof api.createRun>[0] = { env: form.env || undefined, file: form.file };
  if (rangeMode.value === "pick") {
    const ids = collectIds();
    if (!ids.length) {
      ElMessage.warning("请至少勾选一条用例（或切回“按条件筛选”）");
      return;
    }
    body.cases = ids;
  } else {
    body.priority = form.priority || undefined;
    body.module = form.module || undefined;
    body.keyword = form.keyword || undefined;
  }
  const vars = buildVars();
  if (Object.keys(vars).length) body.vars = vars;

  launching.value = true;
  try {
    const run = await api.createRun(body);
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

async function cancelCurrent() {
  if (!current.value) return;
  const r = await api.cancelRun(current.value.run_id);
  ElMessage[r.cancelling ? "warning" : "info"](r.cancelling ? "已终止批次进程树" : `批次已结束：${r.status}`);
  // 立刻刷新一次，不等下一轮轮询
  try { current.value = await api.getRun(current.value.run_id); } catch { /* 拦截器已提示 */ }
  loadRuns();
}

function openReport(runId: string) {
  // 模板里没有 window 作用域，统一走这里
  window.open(api.reportUrl(runId), "_blank");
}

function toReportPage(runId: string) {
  // 站内报告页：平台原生明细（掩码后）+ Allure 内嵌
  router.push({ path: "/report", query: { runId } });
}

function watchRun(run: RunItem) {
  if (run.source !== "api") {
    // cli 历史批次没有内存日志，直接进站内报告页
    toReportPage(run.run_id);
    return;
  }
  current.value = run;
  startPolling(run.run_id);
}

onMounted(async () => {
  loadRuns();
  // 从用例管理“按当前条件执行”跳转而来：预填模块/优先级/关键字
  const q = route.query;
  if (q.module || q.priority || q.keyword) {
    form.module = (q.module as string) || "";
    form.priority = (q.priority as string) || "";
    form.keyword = (q.keyword as string) || "";
    const parts: string[] = [];
    if (q.module) parts.push(`模块=${q.module}`);
    if (q.priority) parts.push(`优先级=${q.priority}`);
    if (q.keyword) parts.push(`关键字=${q.keyword}`);
    carried.value = parts.join("，");
  }
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
          <el-alert
            v-if="carried"
            type="warning"
            :closable="false"
            show-icon
            style="margin-bottom: 12px"
            title="已按用例管理的筛选条件预填"
          >
            <template #default>
              <div style="font-size: 12px">{{ carried }}；确认环境后点“开始执行”即按此范围跑。
                <el-button link type="primary" size="small" @click="clearCarried">清除条件</el-button>
              </div>
            </template>
          </el-alert>
          <el-form label-width="72px" @submit.prevent>
            <el-form-item label="环境">
              <el-select v-model="form.env" style="width: 100%">
                <el-option v-for="e in envs" :key="e.name" :label="`${e.name}（${e.base_url}）`" :value="e.name" />
              </el-select>
            </el-form-item>
            <el-form-item label="范围">
              <el-radio-group v-model="rangeMode" size="small">
                <el-radio-button label="filter">按条件筛选</el-radio-button>
                <el-radio-button label="pick">勾选用例</el-radio-button>
              </el-radio-group>
            </el-form-item>

            <template v-if="rangeMode === 'filter'">
              <el-form-item label="优先级">
                <el-input v-model="form.priority" placeholder="如 P0 或 P0,P1（留空=全量）" />
              </el-form-item>
              <el-form-item label="模块">
                <el-input v-model="form.module" placeholder="包含匹配，留空不筛选" />
              </el-form-item>
              <el-form-item label="关键字">
                <el-input v-model="form.keyword" placeholder="编号/接口名/描述/URL" />
              </el-form-item>
            </template>
            <div v-else class="pick-wrap">
              <div class="pick-bar">
                <el-input v-model="treeFilter" size="small" placeholder="过滤模块/编号/接口名" clearable />
                <span class="pick-count">已选 {{ pickedCount }} 条</span>
              </div>
              <el-tree
                ref="treeRef"
                v-loading="treeLoading"
                :data="treeData"
                show-checkbox
                node-key="id"
                :props="{ children: 'children', label: 'label' }"
                :filter-node-method="filterNode"
                default-expand-all
                class="pick-tree"
                @check="onCheck"
              />
              <div class="pick-tip">勾选模式使用默认用例文件，仅列已启用（run=Y）用例；执行顺序按用例依赖（Excel 行序）。</div>
            </div>

            <el-form-item label="用例文件">
              <el-input v-model="form.file" :disabled="rangeMode === 'pick'" />
            </el-form-item>

            <el-collapse v-model="advOpen" class="vars-collapse">
              <el-collapse-item name="vars">
                <template #title>
                  变量覆盖（可选，运行前生效）
                  <el-tag v-if="varRows.length" size="small" type="warning" style="margin-left: 6px">{{ varRows.length }}</el-tag>
                </template>
                <div v-for="(r, i) in varRows" :key="i" class="var-row">
                  <el-input v-model="r.key" size="small" placeholder="变量名" />
                  <el-input v-model="r.value" size="small" placeholder="值" />
                  <el-button size="small" text type="danger" @click="delVarRow(i)">删</el-button>
                </div>
                <el-button size="small" plain @click="addVarRow">+ 添加变量</el-button>
                <div class="vars-hint">覆盖同名 secret/Excel/YAML 变量（如 base_url、token）；运行时提取值仍优先。</div>
              </el-collapse-item>
            </el-collapse>

            <el-button type="primary" :loading="launching" style="width: 100%; margin-top: 10px" @click="start">
              ▶ 开始执行<template v-if="rangeMode === 'pick' && pickedCount">（{{ pickedCount }} 条）</template>
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
          <el-button
            v-if="current.status === 'running'"
            size="small"
            type="danger"
            plain
            style="margin-bottom: 6px"
            @click="cancelCurrent"
          >
            ⏹ 取消执行
          </el-button>
          <pre class="console">{{ logText || "等待日志…" }}</pre>
          <el-button
            v-if="current.report_dir && ['passed', 'failed'].includes(current.status)"
            type="primary"
            size="small"
            style="margin-top: 8px"
            @click="toReportPage(current.run_id)"
          >
            📊 查看批次报告
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
            <el-table-column label="操作" width="230">
              <template #default="{ row }">
                <el-button size="small" text type="primary" @click="watchRun(row)">
                  {{ row.source === "api" ? "看日志" : "明细" }}
                </el-button>
                <el-button
                  v-if="row.source === 'api' && ['passed', 'failed'].includes(row.status)"
                  size="small"
                  text
                  type="primary"
                  @click="toReportPage(row.run_id)"
                >
                  明细
                </el-button>
                <el-button
                  v-if="row.report_dir"
                  size="small"
                  text
                  @click="openReport(row.run_id)"
                >
                  Allure
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
.pick-wrap { margin-bottom: 12px; }
.pick-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.pick-count { font-size: 12px; color: #409eff; white-space: nowrap; }
.pick-tree {
  max-height: 300px; overflow: auto; border: 1px solid #ebeef5; border-radius: 6px; padding: 4px;
}
.pick-tip { margin-top: 6px; font-size: 12px; color: #909399; line-height: 1.5; }
.vars-collapse { margin-top: 4px; }
.vars-collapse :deep(.el-collapse-item__header) { font-size: 13px; height: 34px; line-height: 34px; }
.var-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.var-row .el-input { flex: 1; }
.vars-hint { margin-top: 6px; font-size: 12px; color: #909399; line-height: 1.5; }
</style>
