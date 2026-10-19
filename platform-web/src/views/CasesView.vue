<script setup lang="ts">
/** 用例管理：筛选 + 表格 + 行展开 + 编辑抽屉（改动直写回存量 Excel）。 */
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api";
import type { CaseItem } from "../types";

const loading = ref(false);
const cases = ref<CaseItem[]>([]);
const total = ref(0);
const filters = reactive({
  module: "",
  priority: [] as string[],
  keyword: "",
  onlyEnabled: true,
});

async function search() {
  loading.value = true;
  try {
    const resp = await api.listCases({
      module: filters.module || undefined,
      priority: filters.priority.length ? filters.priority.join(",") : undefined,
      keyword: filters.keyword || undefined,
      run: filters.onlyEnabled ? true : undefined,
    });
    cases.value = resp.items;
    total.value = resp.total;
  } finally {
    loading.value = false;
  }
}

function reset() {
  filters.module = "";
  filters.priority = [];
  filters.keyword = "";
  filters.onlyEnabled = true;
  search();
}

const prioType = (p: string) =>
  ({ P0: "danger", P1: "warning", P2: "info", P3: "info" }[p] ?? "info");

const fmt = (v: unknown) => (v == null ? "—" : JSON.stringify(v, null, 2));

/* ---------- 编辑抽屉 ---------- */

const editVisible = ref(false);
const saving = ref(false);
const editing = ref<CaseItem | null>(null);   // 打开时的原始行（差分基准）
const form = reactive({
  module: "",
  api_name: "",
  case_desc: "",
  priority: "P0",
  run: true,
  method: "POST",
  url: "",
  timeout: "",
  headers: "",
  params: "",
  body: "",
  extract: "",
  asserts: "",
});

const jsonFields = ["headers", "params", "body", "extract", "asserts"] as const;

/** JSON 文本 → 单元格值：空文本=null，非法时报错 */
function parseJsonField(name: string, text: string): { ok: boolean; value?: unknown } {
  const t = text.trim();
  if (!t) return { ok: true, value: null };
  try {
    return { ok: true, value: JSON.parse(t) };
  } catch {
    ElMessage.error(`「${name}」不是合法 JSON，请检查`);
    return { ok: false };
  }
}

const jsonText = (v: unknown) => (v == null ? "" : JSON.stringify(v, null, 2));

function openEdit(row: CaseItem) {
  editing.value = row;
  Object.assign(form, {
    module: row.module,
    api_name: row.api_name,
    case_desc: row.case_desc,
    priority: row.priority,
    run: row.run,
    method: row.method,
    url: row.url,
    timeout: row.timeout == null ? "" : String(row.timeout),
    headers: jsonText(row.headers),
    params: jsonText(row.params),
    body: jsonText(row.body),
    extract: jsonText(row.extract),
    asserts: jsonText(row.asserts),
  });
  editVisible.value = true;
}

/** 只提交与原始行不同的字段（后端 exclude_unset 语义） */
function buildChanges(): Record<string, unknown> | null {
  const row = editing.value!;
  const changes: Record<string, unknown> = {};
  const plain: Array<[keyof typeof form, string]> = [
    ["module", row.module], ["api_name", row.api_name], ["case_desc", row.case_desc],
    ["priority", row.priority], ["method", row.method], ["url", row.url],
  ];
  for (const [key, orig] of plain) {
    const v = String(form[key]).trim();
    if (!v) { ElMessage.error(`「${key}」不能为空`); return null; }
    if (v !== orig) (changes as Record<string, unknown>)[key] = v;
  }
  if (form.run !== row.run) changes.run = form.run;
  const to = form.timeout.trim();
  const origTo = row.timeout == null ? "" : String(row.timeout);
  if (to !== origTo) {
    if (!to) changes.timeout = null;
    else if (!(Number.isFinite(Number(to)) && Number(to) > 0)) {
      ElMessage.error("超时必须为正数（秒）"); return null;
    } else changes.timeout = Number(to);
  }
  const nameMap: Record<string, string> = { headers: "请求头", params: "查询参数", body: "请求体", extract: "变量提取", asserts: "断言" };
  for (const f of jsonFields) {
    const parsed = parseJsonField(nameMap[f], form[f] as string);
    if (!parsed.ok) return null;
    // 语义比较：parse 原始值与新值后规范化，避免格式差异造成伪改动
    const norm = (v: unknown) => JSON.stringify(v ?? null);
    if (norm(parsed.value) !== norm(row[f])) (changes as Record<string, unknown>)[f] = parsed.value;
  }
  if (Object.keys(changes).length === 0) { ElMessage.info("没有需要保存的改动"); return null; }
  return changes;
}

async function saveEdit() {
  const changes = buildChanges();
  if (!changes || !editing.value) return;
  saving.value = true;
  try {
    await api.updateCase(editing.value.case_id, changes);
    ElMessage.success(`已写回 Excel：${Object.keys(changes).join(", ")}`);
    editVisible.value = false;
    await search();
  } catch {
    /* 拦截器已提示后端 detail（400 逐行定位 / 409 占用与行锁） */
  } finally {
    saving.value = false;
  }
}

onMounted(search);
</script>

<template>
  <div>
    <el-card shadow="never" style="margin-bottom: 12px">
      <el-form inline @submit.prevent>
        <el-form-item label="模块">
          <el-input v-model="filters.module" placeholder="包含匹配" clearable style="width: 140px" />
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="filters.priority" multiple collapse-tags placeholder="全部" style="width: 160px">
            <el-option v-for="p in ['P0', 'P1', 'P2', 'P3']" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="关键字">
          <el-input v-model="filters.keyword" placeholder="编号/接口名/描述/URL" clearable style="width: 180px" />
        </el-form-item>
        <el-form-item label="仅启用">
          <el-switch v-model="filters.onlyEnabled" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <el-table :data="cases" v-loading="loading" row-key="case_id" size="small">
        <el-table-column type="expand">
          <template #default="{ row }">
            <el-descriptions :column="1" border size="small" style="padding: 8px 24px">
              <el-descriptions-item label="Headers">
                <pre class="json">{{ fmt(row.headers) }}</pre>
              </el-descriptions-item>
              <el-descriptions-item label="查询参数">
                <pre class="json">{{ fmt(row.params) }}</pre>
              </el-descriptions-item>
              <el-descriptions-item label="请求体">
                <pre class="json">{{ fmt(row.body) }}</pre>
              </el-descriptions-item>
              <el-descriptions-item label="变量提取">
                <pre class="json">{{ fmt(row.extract) }}</pre>
              </el-descriptions-item>
              <el-descriptions-item label="断言">
                <pre class="json">{{ fmt(row.asserts) }}</pre>
              </el-descriptions-item>
              <el-descriptions-item label="来源">
                {{ row.source }} 第 {{ row.row }} 行 ｜ 超时 {{ row.timeout ?? "默认" }}
              </el-descriptions-item>
            </el-descriptions>
          </template>
        </el-table-column>
        <el-table-column prop="case_id" label="用例编号" min-width="150">
          <template #default="{ row }"><span class="mono">{{ row.case_id }}</span></template>
        </el-table-column>
        <el-table-column prop="api_name" label="接口名称" min-width="140" />
        <el-table-column prop="case_desc" label="用例描述" min-width="180" show-overflow-tooltip />
        <el-table-column prop="module" label="模块" width="110" />
        <el-table-column label="优先级" width="80">
          <template #default="{ row }"><el-tag :type="prioType(row.priority)" size="small">{{ row.priority }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="method" label="方法" width="80" />
        <el-table-column prop="url" label="请求路径" min-width="160">
          <template #default="{ row }"><span class="mono">{{ row.url }}</span></template>
        </el-table-column>
        <el-table-column label="断言数" width="80">
          <template #default="{ row }">{{ (row.asserts ?? []).length }}</template>
        </el-table-column>
        <el-table-column label="启用" width="70">
          <template #default="{ row }">
            <el-tag :type="row.run ? 'success' : 'info'" size="small">{{ row.run ? "Y" : "N" }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div style="margin-top: 10px; color: #909399; font-size: 13px">
        共 {{ total }} 条 ｜ 数据源：data/api_cases.xlsx（Excel 仍是唯一用例载体，平台编辑直写回 Excel，校验不过不落盘）
      </div>
    </el-card>

    <!-- 编辑抽屉：保存时只提交与当前值不同的字段 -->
    <el-drawer v-model="editVisible" size="46%" :title="`编辑用例 ${editing?.case_id ?? ''}`">
      <el-form label-width="90px" @submit.prevent>
        <el-divider content-position="left">基本信息</el-divider>
        <el-form-item label="模块">
          <el-input v-model="form.module" />
        </el-form-item>
        <el-form-item label="接口名称">
          <el-input v-model="form.api_name" />
        </el-form-item>
        <el-form-item label="用例描述">
          <el-input v-model="form.case_desc" type="textarea" :rows="2" />
        </el-form-item>
        <el-row :gutter="8">
          <el-col :span="8">
            <el-form-item label="优先级">
              <el-select v-model="form.priority" style="width: 100%">
                <el-option v-for="p in ['P0', 'P1', 'P2', 'P3']" :key="p" :label="p" :value="p" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="方法">
              <el-select v-model="form.method" style="width: 100%">
                <el-option v-for="m in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']" :key="m" :label="m" :value="m" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="超时(秒)">
              <el-input v-model="form.timeout" placeholder="留空=默认" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="是否执行">
          <el-switch v-model="form.run" active-text="Y" inactive-text="N" />
        </el-form-item>
        <el-form-item label="请求路径">
          <el-input v-model="form.url" class="mono" />
        </el-form-item>

        <el-divider content-position="left">请求配置（JSON，留空=清除）</el-divider>
        <el-form-item v-for="f in jsonFields" :key="f" :label="{ headers: '请求头', params: '查询参数', body: '请求体', extract: '变量提取', asserts: '断言' }[f]">
          <el-input v-model="form[f]" type="textarea" :rows="f === 'asserts' ? 6 : 4" class="mono" spellcheck="false" />
        </el-form-item>

        <div style="color: #909399; font-size: 12px; margin-bottom: 10px">
          保存后直写回 {{ editing?.source }} 第 {{ editing?.row }} 行；后端会跑全文件格式校验，不通过不落盘
        </div>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存并写回 Excel</el-button>
      </el-form>
    </el-drawer>
  </div>
</template>

<style scoped>
.mono { font-family: Consolas, Monaco, monospace; font-size: 12px; }
.json { margin: 0; font-family: Consolas, Monaco, monospace; font-size: 12px; white-space: pre-wrap; word-break: break-all; }
</style>
