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
  ],
});

export default router;
