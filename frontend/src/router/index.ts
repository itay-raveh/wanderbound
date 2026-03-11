import EditorView from "@/pages/EditorView.vue";
import RegisterView from "@/pages/RegisterView.vue";
import PrintView from "@/pages/PrintView.vue";
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
      component: RegisterView,
    },
    {
      path: "/print/:aid",
      name: "print",
      component: PrintView,
    },
  ],
});

export default router;
