import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/cases" },
    {
      path: "/cases",
      name: "cases",
      component: () => import("../views/CasesView.vue"),
      meta: { title: "用例管理" },
    },
    {
      path: "/execution",
      name: "execution",
      component: () => import("../views/ExecutionView.vue"),
      meta: { title: "执行中心" },
    },
    {
      // run_id 可能含 "/"（cli 历史批次 reports/run_xxx），用 query 传参规避动态路由歧义
      path: "/report",
      name: "report",
      component: () => import("../views/ReportView.vue"),
      meta: { title: "批次报告", active: "/execution" },
    },
  ],
});

export default router;
