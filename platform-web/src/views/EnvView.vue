<script setup lang="ts">
/** 环境配置：config.yaml 的只读视图（改配置需重启后端生效，用例级请求头优先于环境默认头）。 */
import { onMounted, ref } from "vue";
import { api } from "../api";
import type { EnvsResp } from "../types";

const loading = ref(true);
const resp = ref<EnvsResp | null>(null);

onMounted(async () => {
  try {
    resp.value = await api.listEnvs();
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div v-loading="loading">
    <el-row :gutter="12">
      <el-col :span="8" v-for="e in resp?.envs ?? []" :key="e.name">
        <el-card shadow="never" style="margin-bottom: 12px">
          <template #header>
            <b>{{ e.name }}</b>
            <el-tag v-if="e.name === resp?.default_env" type="success" size="small" style="margin-left: 8px">默认</el-tag>
          </template>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="base_url">
              <span class="mono">{{ e.base_url ?? "—" }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="超时">
              {{ e.timeout ?? "框架默认" }} 秒
            </el-descriptions-item>
            <el-descriptions-item label="SSL 校验">
              <el-tag :type="e.verify_ssl ? 'success' : 'warning'" size="small">
                {{ e.verify_ssl ? "开启" : "关闭（自签/ TLS 拦截）" }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="默认请求头">
              <div v-if="!Object.keys(e.default_headers ?? {}).length" style="color: #909399">（无）</div>
              <div v-for="(v, k) in e.default_headers" :key="k" class="mono hdr-line">
                {{ k }}: <span style="color: #606266">{{ v }}</span>
              </div>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card shadow="never" header="全局配置" style="margin-bottom: 12px">
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="报告产物">
              <el-tag v-if="resp?.report?.html" size="small" style="margin-right: 6px">pytest-html</el-tag>
              <el-tag v-if="resp?.report?.allure" size="small">allure-results</el-tag>
              <span v-if="!resp?.report?.html && !resp?.report?.allure" style="color: #909399">（均未开启）</span>
            </el-descriptions-item>
            <el-descriptions-item label="日志级别">
              <span class="mono">{{ resp?.log?.level ?? "INFO" }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="凭证变量文件">
              <span class="mono">{{ resp?.secret_vars_file ?? "—" }}</span>
              <div class="hint">文件内容不经过接口回显，仅展示路径</div>
            </el-descriptions-item>
          </el-descriptions>
          <div class="hint" style="margin-top: 10px">
            环境与会话配置来自 config/config.yaml，修改后重启后端生效；用例内 headers 与默认头合并时用例优先。
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.mono { font-family: Consolas, Monaco, monospace; font-size: 12px; }
.hdr-line { margin-bottom: 2px; word-break: break-all; }
.hint { color: #909399; font-size: 12px; margin-top: 2px; }
</style>
