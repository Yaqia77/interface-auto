<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "../api";
import type { ScheduleItem, PlanItem } from "../types";

const items = ref<ScheduleItem[]>([]);
const plans = ref<PlanItem[]>([]);
const loading = ref(false);

/* 抽屉表单 */
const drawerVisible = ref(false);
const isEdit = ref(false);
const editId = ref("");
const form = reactive({
  name: "",
  cron: "0 8 * * *",
  target: "plan" as "plan" | "config",
  plan_id: "",
  run_config: { env: "", module: "", priority: "" },
  enabled: true,
});

/* Cron 预览 */
const previewRuns = ref<string[]>([]);
const previewLoading = ref(false);

async function loadList() {
  loading.value = true;
  try {
    const [sch, pl] = await Promise.all([api.listSchedules(), api.listPlans()]);
    items.value = sch;
    plans.value = pl;
  } finally {
    loading.value = false;
  }
}
onMounted(loadList);

function openCreate() {
  isEdit.value = false;
  editId.value = "";
  form.name = "";
  form.cron = "0 8 * * *";
  form.target = "plan";
  form.plan_id = "";
  form.run_config = { env: "", module: "", priority: "" };
  form.enabled = true;
  previewRuns.value = [];
  drawerVisible.value = true;
}

function openEdit(item: ScheduleItem) {
  isEdit.value = true;
  editId.value = item.id;
  form.name = item.name;
  form.cron = item.cron;
  form.target = item.plan_id ? "plan" : "config";
  form.plan_id = item.plan_id || "";
  form.run_config = { env: "", module: "", priority: "", ...(item.run_config || {}) };
  form.enabled = item.enabled;
  previewRuns.value = [];
  drawerVisible.value = true;
}

async function doPreview() {
  if (!form.cron.trim()) return;
  previewLoading.value = true;
  try {
    const resp = await api.previewCron(form.cron, 5);
    previewRuns.value = resp.next_runs;
  } catch {
    previewRuns.value = [];
  } finally {
    previewLoading.value = false;
  }
}

async function save() {
  if (!form.name.trim()) { ElMessage.warning("名称不能为空"); return; }
  if (!form.cron.trim()) { ElMessage.warning("Cron 表达式不能为空"); return; }
  if (form.target === "plan" && !form.plan_id) { ElMessage.warning("请选择场景"); return; }

  const body: any = {
    name: form.name,
    cron: form.cron,
    enabled: form.enabled,
  };
  if (form.target === "plan") {
    body.plan_id = form.plan_id;
  } else {
    const cfg: any = {};
    if (form.run_config.env) cfg.env = form.run_config.env;
    if (form.run_config.module) cfg.module = form.run_config.module;
    if (form.run_config.priority) cfg.priority = form.run_config.priority;
    body.run_config = cfg;
  }

  try {
    if (isEdit.value) {
      await api.updateSchedule(editId.value, body);
      ElMessage.success("已更新");
    } else {
      await api.createSchedule(body);
      ElMessage.success("已创建");
    }
    drawerVisible.value = false;
    loadList();
  } catch { /* 拦截器提示 */ }
}

async function remove(item: ScheduleItem) {
  await ElMessageBox.confirm(`确认删除「${item.name}」？`, "提示", { type: "warning" });
  await api.deleteSchedule(item.id);
  ElMessage.success("已删除");
  loadList();
}

async function toggle(item: ScheduleItem) {
  await api.updateSchedule(item.id, { enabled: !item.enabled });
  loadList();
}

const running = ref<string>("");
async function manualRun(item: ScheduleItem) {
  running.value = item.id;
  try {
    await api.runSchedule(item.id);
    ElMessage.success("已触发执行");
    loadList();
  } catch { /* 拦截器提示 */ } finally {
    running.value = "";
  }
}

function planName(id: string) {
  return plans.value.find(p => p.id === id)?.name || id || "-";
}
function fmtTime(t: string | null) {
  if (!t) return "-";
  return t.replace("T", " ");
}
</script>

<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
      <h3 style="margin: 0">定时任务</h3>
      <el-button type="primary" @click="openCreate">＋ 新建定时任务</el-button>
    </div>

    <el-table :data="items" v-loading="loading" stripe empty-text="暂无定时任务">
      <el-table-column prop="name" label="名称" min-width="130" />
      <el-table-column prop="cron" label="Cron" width="140">
        <template #default="{ row }">
          <code style="font-size: 12px">{{ row.cron }}</code>
        </template>
      </el-table-column>
      <el-table-column label="执行目标" min-width="120">
        <template #default="{ row }">
          <span v-if="row.plan_id">场景: {{ planName(row.plan_id) }}</span>
          <span v-else-if="row.run_config && Object.keys(row.run_config).length">自定义配置</span>
          <span v-else style="color:#909399">未配置</span>
        </template>
      </el-table-column>
      <el-table-column label="下次执行" width="160">
        <template #default="{ row }">{{ fmtTime(row.next_run_at) }}</template>
      </el-table-column>
      <el-table-column label="上次执行" width="160">
        <template #default="{ row }">{{ fmtTime(row.last_run_at) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="70">
        <template #default="{ row }">
          <el-switch :model-value="row.enabled" size="small" @change="toggle(row)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
          <el-button link type="success" size="small" :loading="running === row.id" @click="manualRun(row)">执行</el-button>
          <el-button link type="danger" size="small" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新建/编辑抽屉 -->
    <el-drawer v-model="drawerVisible" :title="isEdit ? '编辑定时任务' : '新建定时任务'" size="460px">
      <el-form label-position="top">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="例如：每日P0冒烟" />
        </el-form-item>
        <el-form-item label="Cron 表达式（分 时 日 月 周）">
          <div style="display: flex; gap: 8px; width: 100%">
            <el-input v-model="form.cron" placeholder="0 8 * * *" style="flex:1" />
            <el-button @click="doPreview" :loading="previewLoading">预览</el-button>
          </div>
          <div v-if="previewRuns.length" style="margin-top: 8px; font-size: 12px; color: #606266">
            <div v-for="(t, i) in previewRuns" :key="i">{{ i + 1 }}. {{ t.replace('T', ' ') }}</div>
          </div>
        </el-form-item>
        <el-form-item label="执行目标">
          <el-radio-group v-model="form.target">
            <el-radio value="plan">关联场景</el-radio>
            <el-radio value="config">自定义配置</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.target === 'plan'" label="选择场景">
          <el-select v-model="form.plan_id" placeholder="选择已有场景" style="width: 100%">
            <el-option v-for="p in plans" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <template v-if="form.target === 'config'">
          <el-form-item label="环境（可选）">
            <el-input v-model="form.run_config.env" placeholder="留空使用默认环境" />
          </el-form-item>
          <el-form-item label="模块（可选）">
            <el-input v-model="form.run_config.module" placeholder="按模块筛选" />
          </el-form-item>
          <el-form-item label="优先级（可选）">
            <el-input v-model="form.run_config.priority" placeholder="如 P0,P1" />
          </el-form-item>
        </template>
        <el-form-item>
          <el-switch v-model="form.enabled" active-text="启用" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="save">{{ isEdit ? '保存' : '创建' }}</el-button>
          <el-button @click="drawerVisible = false">取消</el-button>
        </el-form-item>
      </el-form>
    </el-drawer>
  </div>
</template>

<style scoped>
h3 { font-size: 16px; color: #303133; }
</style>
