<script setup lang="ts">
/** 用例管理：筛选 + 表格 + 行展开（请求/断言/提取详情，数据源即存量 Excel）。 */
import { onMounted, reactive, ref } from "vue";
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
      </el-table>
      <div style="margin-top: 10px; color: #909399; font-size: 13px">
        共 {{ total }} 条 ｜ 数据源：data/api_cases.xlsx（Excel 仍是唯一用例载体，平台只读展示）
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.mono { font-family: Consolas, Monaco, monospace; font-size: 12px; }
.json { margin: 0; font-family: Consolas, Monaco, monospace; font-size: 12px; white-space: pre-wrap; word-break: break-all; }
</style>
