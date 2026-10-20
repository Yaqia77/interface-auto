<script setup lang="ts">
/** 用例管理：筛选 + 表格 + 行展开 + 编辑/新增抽屉（候选来自 /api/cases/meta，改动直写回存量 Excel）。 */
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api";
import type { CaseItem, CaseMeta } from "../types";

const loading = ref(false);
const cases = ref<CaseItem[]>([]);
const total = ref(0);
const meta = ref<CaseMeta | null>(null);
const filters = reactive({
  module: "",
  priority: [] as string[],
  keyword: "",
  onlyEnabled: true,
});

/* ================= 分页 + 模块列合并（后端返回全量筛选结果，前端切片展示） ================= */
const pageSize = ref(10);
const currentPage = ref(1);

/** 按模块排序使同模块用例相邻，供模块列纵向合并 */
const sortedCases = computed(() =>
  [...cases.value].sort(
    (a, b) => a.module.localeCompare(b.module, "zh") || a.case_id.localeCompare(b.case_id)
  )
);
const pagedCases = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return sortedCases.value.slice(start, start + pageSize.value);
});

/** 模块列同值纵向合并：仅合并块首行渲染，其余行隐藏（rowspan/colspan 为 0） */
function spanMethod({ row, column, rowIndex }: { row: CaseItem; column: any; rowIndex: number }) {
  if (column.property !== "module") return { rowspan: 1, colspan: 1 };
  const data = pagedCases.value;
  if (rowIndex > 0 && data[rowIndex - 1].module === row.module) return { rowspan: 0, colspan: 0 };
  let count = 1;
  while (rowIndex + count < data.length && data[rowIndex + count].module === row.module) count++;
  return { rowspan: count, colspan: 1 };
}

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
    currentPage.value = 1;
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
  ({ P0: "danger", P1: "warning", P2: "info", P3: "info", P4: "info", P5: "info" }[p] ?? "info");

const fmt = (v: unknown) => (v == null ? "—" : JSON.stringify(v, null, 2));

/* ================= 编辑抽屉 ================= */

interface KvRow { key: string; value: string }
interface AssertRow { op: string; path: string; expected: string }

const editVisible = ref(false);
const saving = ref(false);
const editing = ref<CaseItem | null>(null);   // 打开时的原始行（差分基准；新增/复制模式为 null）
const mode = ref<"edit" | "create">("edit");
const copyFrom = ref("");                      // 复制来源编号（仅提示用）

const form = reactive({
  case_id: "",
  module: "",
  api_name: "",
  case_desc: "",
  priority: "P0",
  run: true,
  method: "POST",
  url: "",
  timeout: "",
  body: "",
});

const hdrRows = ref<KvRow[]>([]);
const prmRows = ref<KvRow[]>([]);
const extRows = ref<KvRow[]>([]);
const asrtRows = ref<AssertRow[]>([]);

// 字面量含 {{ }}，定义为常量避免写进模板插值
const VAR_PH = "值，支持 {{变量}} 引用";
const PATH_PH = "status_code / response_text / $.data.code";
const varChip = (v: string) => "{{" + v + "}}";

const prioOptions = () => meta.value?.priorities ?? ["P0", "P1", "P2", "P3", "P4", "P5"];
const methodOptions = () => meta.value?.methods ?? ["GET", "POST", "PUT", "DELETE", "PATCH"];

/* ---------- 行数据 ⇄ JSON 值 转换 ---------- */

const objToRows = (o: Record<string, unknown> | null): KvRow[] =>
  Object.entries(o ?? {}).map(([key, value]) => ({ key, value: String(value ?? "") }));

const rowsToObj = (rows: KvRow[], label: string): Record<string, string> | null => {
  const out: Record<string, string> = {};
  for (const r of rows) {
    const k = r.key.trim();
    if (!k) continue;
    if (k in out) { ElMessage.error(`${label}存在重复的键：${k}`); return null; }
    out[k] = r.value;
  }
  return out;
};

/** 期望值字符串 → 单元格 JSON 值（轻量推断数字/布尔，其余按字符串；断言引擎自带跨类型比较） */
const parseExpected = (s: string): unknown => {
  const t = s.trim();
  if (/^-?\d+(\.\d+)?$/.test(t)) return Number(t);
  if (t === "true") return true;
  if (t === "false") return false;
  return t;
};

const stringifyExpected = (v: unknown): string => (v == null ? "" : String(v));

const assertsToRows = (arr: unknown): AssertRow[] =>
  (Array.isArray(arr) ? arr : []).map((a) => {
    const r = Array.isArray(a) ? a : [];
    return { op: String(r[0] ?? ""), path: String(r[1] ?? ""), expected: stringifyExpected(r[2]) };
  });

const opNeedExpected = (op: string): boolean => {
  const info = meta.value?.assert_ops.find((o) => o.op === op);
  return info ? info.need_expected : true;
};

const rowsToAsserts = (): (string | unknown)[][] | null => {
  const out: (string | unknown)[][] = [];
  for (const [i, r] of asrtRows.value.entries()) {
    if (!r.op) { ElMessage.error(`第 ${i + 1} 条断言缺少操作符`); return null; }
    if (!r.path.trim()) { ElMessage.error(`第 ${i + 1} 条断言缺少取值路径`); return null; }
    out.push(opNeedExpected(r.op) ? [r.op, r.path.trim(), parseExpected(r.expected)] : [r.op, r.path.trim()]);
  }
  return out;
};

/** 空对象/空数组与 null 视为等价，避免格式差异造成伪改动 */
const normVal = (v: unknown): string => {
  if (v == null) return "null";
  if (typeof v === "object" && !Array.isArray(v) && Object.keys(v).length === 0) return "null";
  if (Array.isArray(v) && v.length === 0) return "null";
  return JSON.stringify(v);
};
const normAsserts = (arr: unknown): string => {
  const list = Array.isArray(arr) ? arr : [];
  return JSON.stringify(list.map((a) => {
    const r = Array.isArray(a) ? a : [];
    return r.length >= 3 ? [String(r[0]).toLowerCase(), String(r[1]), r[2]] : [String(r[0]).toLowerCase(), String(r[1])];
  }));
};

/* ---------- 请求头：key 选中候选时自动填充建议值 ---------- */

const hdrFocus = ref(0);

function onHdrKey(val: string, row: KvRow) {
  const hit = meta.value?.header_suggest.find((o) => o.key === val);
  if (hit && !row.value) row.value = hit.value;
}

function insertVar(v: string) {
  let idx = hdrFocus.value;
  if (!hdrRows.value.length) hdrRows.value.push({ key: "", value: "" });
  idx = Math.min(Math.max(idx, 0), hdrRows.value.length - 1);
  hdrRows.value[idx].value += varChip(v);
}

/* ---------- 打开 / 保存 ---------- */

const jsonText = (v: unknown) => (v == null ? "" : JSON.stringify(v, null, 2));

function openEdit(row: CaseItem) {
  mode.value = "edit";
  editing.value = row;
  Object.assign(form, {
    case_id: row.case_id,
    module: row.module,
    api_name: row.api_name,
    case_desc: row.case_desc,
    priority: row.priority,
    run: row.run,
    method: row.method,
    url: row.url,
    timeout: row.timeout == null ? "" : String(row.timeout),
    body: jsonText(row.body),
  });
  hdrRows.value = objToRows(row.headers);
  prmRows.value = objToRows(row.params);
  extRows.value = objToRows(row.extract);
  asrtRows.value = assertsToRows(row.asserts);
  editVisible.value = true;
}

/** 新增：预置一条最常见的基础断言与默认值，请求配置类字段留空引导填写 */
function openCreate() {
  mode.value = "create";
  editing.value = null;
  copyFrom.value = "";
  Object.assign(form, {
    case_id: "", module: "", api_name: "", case_desc: "", priority: "P2", run: true,
    method: "GET", url: "", timeout: "", body: "",
  });
  hdrRows.value = [];
  prmRows.value = [];
  extRows.value = [];
  asrtRows.value = [{ op: "eq", path: "status_code", expected: "200" }];
  editVisible.value = true;
}

/** 复制：按编辑态预填全字段后切到新增态，编号置空强制重新命名 */
function openCopy(row: CaseItem) {
  openEdit(row);
  mode.value = "create";
  editing.value = null;
  copyFrom.value = row.case_id;
  form.case_id = "";
}

/** 采集当前抽屉表单为完整用例对象（新增用）；校验失败返回 null */
function collectAll(): Record<string, unknown> | null {
  const cid = form.case_id.trim();
  if (!cid) { ElMessage.error("用例编号不能为空"); return null; }
  const out: Record<string, unknown> = {};
  for (const key of ["module", "api_name", "priority", "method", "url"] as const) {
    const v = String(form[key]).trim();
    if (!v) { ElMessage.error(`「${key}」不能为空`); return null; }
    out[key] = v;
  }
  out.case_id = cid;
  out.case_desc = form.case_desc.trim() || "新建用例";
  out.run = form.run;
  const to = form.timeout.trim();
  if (to) {
    if (!(Number.isFinite(Number(to)) && Number(to) > 0)) { ElMessage.error("超时必须为正数（秒）"); return null; }
    out.timeout = Number(to);
  }
  if (form.body.trim()) {
    try { out.body = JSON.parse(form.body); }
    catch { ElMessage.error("「请求体」不是合法 JSON，请检查"); return null; }
  }
  const kvSpec: Array<[KvRow[], string, string]> = [
    [hdrRows.value, "headers", "请求头"],
    [prmRows.value, "params", "查询参数"],
    [extRows.value, "extract", "变量提取"],
  ];
  for (const [rows, field, label] of kvSpec) {
    const obj = rowsToObj(rows, label);
    if (obj === null) return null;
    out[field] = Object.keys(obj).length ? obj : null;
  }
  const asserts = rowsToAsserts();
  if (asserts === null) return null;
  if (asserts.length === 0) { ElMessage.error("至少保留一条断言"); return null; }
  out.asserts = asserts;
  return out;
}

/** 只提交与原始行不同的字段（后端 exclude_unset 语义） */
function buildChanges(): Record<string, unknown> | null {
  const row = editing.value!;
  const changes: Record<string, unknown> = {};

  const plain: Array<["module" | "api_name" | "case_desc" | "priority" | "method" | "url", string]> = [
    ["module", row.module], ["api_name", row.api_name], ["case_desc", row.case_desc],
    ["priority", row.priority], ["method", row.method], ["url", row.url],
  ];
  for (const [key, orig] of plain) {
    const v = String(form[key]).trim();
    if (!v) { ElMessage.error(`「${key}」不能为空`); return null; }
    if (v !== orig) changes[key] = v;
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

  // JSON 文本域：body
  let bodyVal: unknown = null;
  if (form.body.trim()) {
    try { bodyVal = JSON.parse(form.body); }
    catch { ElMessage.error("「请求体」不是合法 JSON，请检查"); return null; }
  }
  if (normVal(bodyVal) !== normVal(row.body)) changes.body = bodyVal;

  // kv 行编辑器
  const kvSpec: Array<[KvRow[], Record<string, unknown> | null, string, string]> = [
    [hdrRows.value, row.headers, "headers", "请求头"],
    [prmRows.value, row.params, "params", "查询参数"],
    [extRows.value, row.extract, "extract", "变量提取"],
  ];
  for (const [rows, orig, field, label] of kvSpec) {
    const obj = rowsToObj(rows, label);
    if (obj === null) return null;
    if (normVal(obj) !== normVal(orig)) changes[field] = obj;
  }

  // 断言构建器（Excel 断言列不允许为空）
  const asserts = rowsToAsserts();
  if (asserts === null) return null;
  if (asserts.length === 0) { ElMessage.error("至少保留一条断言"); return null; }
  if (normAsserts(asserts) !== normAsserts(row.asserts)) changes.asserts = asserts;

  if (Object.keys(changes).length === 0) { ElMessage.info("没有需要保存的改动"); return null; }
  return changes;
}

async function saveEdit() {
  saving.value = true;
  try {
    if (mode.value === "create") {
      const data = collectAll();
      if (!data) return;
      await api.createCase(data);
      ElMessage.success(`已新增并写回 Excel：${data.case_id}`);
    } else {
      const changes = buildChanges();
      if (!changes || !editing.value) return;
      await api.updateCase(editing.value.case_id, changes);
      ElMessage.success(`已写回 Excel：${Object.keys(changes).join(", ")}`);
    }
    editVisible.value = false;
    await search();
    meta.value = await api.getCaseMeta();  // 模块/请求头候选可能因本次改动而新增
  } catch {
    /* 拦截器已提示后端 detail（400 逐行定位 / 409 占用、重号与行锁） */
  } finally {
    saving.value = false;
  }
}

async function removeCase(row: CaseItem) {
  try {
    await api.deleteCase(row.case_id);
    ElMessage.success(`已删除并写回 ${row.source}：${row.case_id}`);
    await search();
    meta.value = await api.getCaseMeta();
  } catch { /* 拦截器已提示 */ }
}

onMounted(async () => {
  search();
  try { meta.value = await api.getCaseMeta(); } catch { /* 拦截器已提示 */ }
});
</script>

<template>
  <div>
    <el-card shadow="never" style="margin-bottom: 12px">
      <el-form inline @submit.prevent>
        <el-form-item label="模块">
          <el-input v-model="filters.module" placeholder="包含匹配" clearable style="width: 140px" />
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="filters.priority" multiple collapse-tags placeholder="全部" style="width: 180px">
            <el-option v-for="p in prioOptions()" :key="p" :label="p" :value="p" />
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
          <el-button type="success" plain @click="openCreate">＋ 新增用例</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <el-table :data="pagedCases" v-loading="loading" row-key="case_id" size="small" :span-method="spanMethod">
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
        <el-table-column prop="module" label="模块" width="120" />
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
        <el-table-column label="操作" width="170">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" text type="primary" @click="openCopy(row)">复制</el-button>
            <el-popconfirm :title="'删除 ' + row.case_id + '？将从 Excel 整行移除'" width="260">
              <template #reference>
                <el-button size="small" text type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50, 100]"
        :total="total"
        layout="total, sizes, prev, pager, next, jumper"
        background
        size="small"
        style="margin-top: 12px; justify-content: flex-end"
        @size-change="currentPage = 1"
      />
      <div style="margin-top: 10px; color: #909399; font-size: 13px">
        共 {{ total }} 条 ｜ 数据源：data/api_cases.xlsx（Excel 仍是唯一用例载体，平台编辑直写回 Excel，校验不过不落盘）
      </div>
    </el-card>

    <!-- 编辑抽屉：下拉候选来自 /api/cases/meta，保存只提交差异字段 -->
    <el-drawer v-model="editVisible" size="52%" :title="mode === 'create' ? (copyFrom ? '复制新增用例' : '新增用例') : `编辑用例 ${editing?.case_id ?? ''}`">
      <el-form label-width="90px" @submit.prevent>
        <el-divider content-position="left">基本信息</el-divider>
        <el-form-item label="用例编号">
          <el-input v-model="form.case_id" :disabled="mode === 'edit'" class="mono"
                    :placeholder="copyFrom ? `新编号（原 ${copyFrom} 的配置已预填）` : '唯一编号，如 album_list_002（创建后不可改）'" />
        </el-form-item>
        <el-form-item label="模块">
          <el-select v-model="form.module" filterable allow-create default-first-option placeholder="选择或输入新模块" style="width: 100%">
            <el-option v-for="m in meta?.modules ?? []" :key="m" :label="m" :value="m" />
          </el-select>
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
                <el-option v-for="p in prioOptions()" :key="p" :label="p" :value="p" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="方法">
              <el-select v-model="form.method" style="width: 100%">
                <el-option v-for="m in methodOptions()" :key="m" :label="m" :value="m" />
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

        <el-divider content-position="left">请求头</el-divider>
        <div class="hint">常用 Header 从下拉选择并自动带出建议值；不在列表中的可直接输入新名称。点击变量标签可在聚焦的值框中插入引用。</div>
        <div v-for="(h, i) in hdrRows" :key="'h' + i" class="kv-row">
          <el-select v-model="h.key" filterable allow-create default-first-option placeholder="Header 名" style="width: 190px" @change="(v: string) => onHdrKey(v, h)">
            <el-option v-for="o in meta?.header_suggest ?? []" :key="o.key" :value="o.key" :label="o.key">
              <span class="opt-key">{{ o.key }}</span>
              <span class="opt-val">{{ o.value }}{{ o.used ? `（${o.used} 条在用）` : "（内置建议）" }}</span>
            </el-option>
          </el-select>
          <el-input v-model="h.value" :placeholder="VAR_PH" class="mono" style="flex: 1" @focus="hdrFocus = i" />
          <el-button text type="danger" @click="hdrRows.splice(i, 1)">✕</el-button>
        </div>
        <el-button size="small" @click="hdrRows.push({ key: '', value: '' })">＋ 添加请求头</el-button>
        <div v-if="meta?.variables?.length" class="var-chips">
          <el-tag v-for="v in meta.variables" :key="v" size="small" class="var-chip" @click="insertVar(v)">{{ varChip(v) }}</el-tag>
        </div>

        <el-divider content-position="left">查询参数</el-divider>
        <div v-for="(p, i) in prmRows" :key="'p' + i" class="kv-row">
          <el-input v-model="p.key" placeholder="参数名" class="mono" style="width: 190px" />
          <el-input v-model="p.value" :placeholder="VAR_PH" class="mono" style="flex: 1" />
          <el-button text type="danger" @click="prmRows.splice(i, 1)">✕</el-button>
        </div>
        <el-button size="small" @click="prmRows.push({ key: '', value: '' })">＋ 添加参数</el-button>

        <el-divider content-position="left">请求体（JSON，留空=清除）</el-divider>
        <el-input v-model="form.body" type="textarea" :rows="5" class="mono" spellcheck="false" />

        <el-divider content-position="left">变量提取</el-divider>
        <div class="hint">变量名 ← 响应 JSONPath，供后续用例 {{ varChip("变量名") }} 引用。</div>
        <div v-for="(x, i) in extRows" :key="'x' + i" class="kv-row">
          <el-input v-model="x.key" placeholder="变量名" class="mono" style="width: 190px" />
          <el-input v-model="x.value" :placeholder="PATH_PH" class="mono" style="flex: 1" />
          <el-button text type="danger" @click="extRows.splice(i, 1)">✕</el-button>
        </div>
        <el-button size="small" @click="extRows.push({ key: '', value: '' })">＋ 添加提取</el-button>

        <el-divider content-position="left">断言（至少一条）</el-divider>
        <div v-for="(a, i) in asrtRows" :key="'a' + i" class="kv-row">
          <el-select v-model="a.op" placeholder="操作符" style="width: 170px">
            <el-option v-for="o in meta?.assert_ops ?? []" :key="o.op" :value="o.op" :label="`${o.op} ${o.desc}`" />
          </el-select>
          <el-input v-model="a.path" :placeholder="PATH_PH" class="mono" style="flex: 1" />
          <el-input v-if="opNeedExpected(a.op)" v-model="a.expected" placeholder="期望值" class="mono" style="width: 170px" />
          <el-button text type="danger" @click="asrtRows.splice(i, 1)">✕</el-button>
        </div>
        <el-button size="small" @click="asrtRows.push({ op: 'eq', path: '', expected: '' })">＋ 添加断言</el-button>

        <div class="hint" style="margin: 14px 0 10px">
          <template v-if="mode === 'create'">保存后追加为 data/api_cases.xlsx 末行{{ copyFrom ? "（复制自 " + copyFrom + "，作为全新用例）" : "" }}；后端跑全文件格式校验，不通过不落盘。</template>
          <template v-else>保存后直写回 {{ editing?.source }} 第 {{ editing?.row }} 行；后端跑全文件格式校验，不通过不落盘。</template>
        </div>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">{{ mode === "create" ? "新增并写回 Excel" : "保存并写回 Excel" }}</el-button>
      </el-form>
    </el-drawer>
  </div>
</template>

<style scoped>
.mono { font-family: Consolas, Monaco, monospace; font-size: 12px; }
.json { margin: 0; font-family: Consolas, Monaco, monospace; font-size: 12px; white-space: pre-wrap; word-break: break-all; }
.kv-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.hint { color: #909399; font-size: 12px; margin-bottom: 8px; }
.opt-key { float: left; }
.opt-val { float: right; color: #a0a4a8; font-size: 12px; margin-left: 16px; }
.var-chips { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; }
.var-chip { cursor: pointer; font-family: Consolas, Monaco, monospace; }
</style>
