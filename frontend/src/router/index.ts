import EditorView from "@/pages/EditorView.vue";
import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: "/",
      name: "editor",
      component: EditorView,
    },
    {
      path: "/register",
      name: "register",
      component: () => import("@/pages/RegisterView.vue"),
    },
    {
      path: "/print/:aid",
      name: "print",
      component: () => import("@/pages/PrintView.vue"),
    },
  ],
});

export default router;
