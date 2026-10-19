<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { api } from "./api";
import type { EnvInfo } from "./types";

const route = useRoute();
const title = computed(() => (route.meta.title as string) ?? "interface-auto");

// 顶栏环境指示（全局共享的简化版：当前仅展示，切换在任务表单里做）
const envs = ref<EnvInfo[]>([]);
const currentEnv = ref<string>("");

onMounted(async () => {
  try {
    const resp = await api.listEnvs();
    envs.value = resp.envs;
    currentEnv.value = resp.default_env ?? resp.envs[0]?.name ?? "";
  } catch {
    /* 拦截器已提示 */
  }
});
</script>

<template>
  <el-container style="height: 100vh">
    <el-aside width="220px" class="side">
      <div class="logo">● Interface Auto 平台</div>
      <el-menu router :default-active="route.path" class="side-menu">
        <el-menu-item index="/cases">📋 用例管理</el-menu-item>
        <el-menu-item index="/execution">🚀 执行中心</el-menu-item>
      </el-menu>
      <div class="side-foot">P1 骨架 · 对接 FastAPI 后端</div>
    </el-aside>
    <el-container>
      <el-header class="topbar">
        <b>{{ title }}</b>
        <div style="margin-left: auto">
          <el-tag v-if="currentEnv" size="small">环境：{{ currentEnv }}</el-tag>
          <span v-if="envs.length > 1" style="color: #909399; font-size: 12px">
            （共 {{ envs.length }} 个环境）
          </span>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style>
body { margin: 0; font-family: "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif; }
.side { background: #2b3648; color: #bfcbd9; display: flex; flex-direction: column; }
.logo { height: 56px; display: flex; align-items: center; padding: 0 14px; font-weight: 600; color: #fff; background: #232c3d; font-size: 14px; }
.side-menu { border-right: none; flex: 1; }
.side-menu .el-menu-item { color: #bfcbd9; }
/* 企业后台经典选中态：主题蓝实底 + 白字 */
.side-menu .el-menu-item.is-active { color: #fff; background: #409eff; }
.side-menu .el-menu-item.is-active .el-icon { color: #fff; }
.side-menu .el-menu-item:not(.is-active):hover { background: #263042; color: #fff; }
.side-menu .el-menu-item { transition: background-color .15s ease, color .15s ease; }
.side-foot { padding: 12px 14px; font-size: 11px; color: #6b7a8f; border-top: 1px solid #232c3d; }
.topbar { display: flex; align-items: center; border-bottom: 1px solid #e4e7ed; background: #fff; }
.main { background: #f5f7fa; }
</style>
