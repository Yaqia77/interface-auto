import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/dashboard" },
    {
      path: "/dashboard",
      name: "dashboard",
      component: () => import("../views/DashboardView.vue"),
      meta: { title: "工作台" },
    },
    {
      path: "/stats",
      name: "stats",
      component: () => import("../views/StatsView.vue"),
      meta: { title: "统计报表" },
    },
    {
      path: "/cases",
      name: "cases",
      component: () => import("../views/CasesView.vue"),
      meta: { title: "用例管理" },
    },
    {
      path: "/plans",
      name: "plans",
      component: () => import("../views/PlansView.vue"),
      meta: { title: "测试场景" },
    },
    {
      path: "/execution",
      name: "execution",
      component: () => import("../views/ExecutionView.vue"),
      meta: { title: "执行中心" },
    },
    {
      path: "/envs",
      name: "envs",
      component: () => import("../views/EnvView.vue"),
      meta: { title: "环境配置" },
    },
    {
      path: "/secrets",
      name: "secrets",
      component: () => import("../views/SecretsView.vue"),
      meta: { title: "凭证管理" },
    },
    {
      path: "/notifications",
      name: "notifications",
      component: () => import("../views/NotificationsView.vue"),
      meta: { title: "通知配置" },
    },
    {
      // run_id 可能含 "/"（cli 历史批次 reports/run_xxx），用 query 传参规避动态路由歧义；
      // 无 runId 时报告页落「批次列表」选择页，作为侧栏独立入口。
      path: "/report",
      name: "report",
      component: () => import("../views/ReportView.vue"),
      meta: { title: "报告详情" },
    },
  ],
});

export default router;
