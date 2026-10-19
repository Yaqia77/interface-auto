<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { api } from "./api";
import type { EnvInfo } from "./types";

const route = useRoute();
const title = computed(() => (route.meta.title as string) ?? "interface-auto");
// 菜单选中态归属：/report 等二级页通过 meta.active 指定高亮的菜单项
const activeMenu = computed(() => (route.meta.active as string) ?? route.path);

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
      <el-menu router :default-active="activeMenu" class="side-menu">
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
.side { background: #1f2b3e; color: #bfcbd9; display: flex; flex-direction: column; }
.logo { height: 56px; display: flex; align-items: center; padding: 0 14px; font-weight: 600; color: #fff; background: #16202e; font-size: 14px; letter-spacing: 0.5px; }
/* 关键：覆盖 el-menu 自身白底（默认 --el-menu-bg-color:#fff），整侧栏透色融入深色背景 */
.side-menu {
  border-right: none; flex: 1; background: transparent;
  --el-menu-bg-color: transparent;
  --el-menu-text-color: #c3ccd9;
  --el-menu-active-color: #fff;
  --el-menu-hover-bg-color: rgba(255, 255, 255, 0.07);
}
/* 企业后台经典选中态：主题蓝实底 + 白字 */
.side-menu .el-menu-item { height: 46px; line-height: 46px; margin: 4px 8px; border-radius: 6px; transition: background-color 0.15s ease, color 0.15s ease; }
.side-menu .el-menu-item.is-active { color: #fff; background: #409eff; font-weight: 600; }
.side-menu .el-menu-item.is-active:hover { background: #409eff; }
.side-menu .el-menu-item:not(.is-active):hover { color: #fff; }
.side-foot { padding: 12px 14px; font-size: 11px; color: #63718a; border-top: 1px solid #16202e; }
.topbar { display: flex; align-items: center; border-bottom: 1px solid #e4e7ed; background: #fff; }
.main { background: #f5f7fa; }
</style>
