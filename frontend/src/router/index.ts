import { authState } from "@/client";
import type { AuthenticateData } from "@/client";
import { useQueryCache } from "@pinia/colada";
import { createRouter, createWebHistory } from "vue-router";
import { queryKeys } from "@/queries/keys";

export type Provider = AuthenticateData["path"]["provider"];

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  scrollBehavior(to, _from, savedPosition) {
    if (savedPosition) return savedPosition;
    if (to.hash) return { el: to.hash, behavior: "smooth" };
    return { top: 0 };
  },
  routes: [
    {
      path: "/",
      name: "landing",
      component: () => import("@/pages/LandingView.vue"),
      meta: { public: true },
    },
    {
      path: "/editor",
      name: "editor",
      component: () => import("@/pages/EditorView.vue"),
    },
    {
      path: "/upload",
      name: "upload",
      component: () => import("@/pages/UploadView.vue"),
    },
    {
      path: "/legal",
      name: "legal",
      component: () => import("@/pages/LegalView.vue"),
      meta: { public: true },
    },
    {
      path: "/print/:aid",
      name: "print",
      component: () => import("@/pages/PrintView.vue"),
      meta: { public: true },
    },
    {
      path: "/:pathMatch(.*)*",
      redirect: "/",
    },
  ],
});

router.beforeEach(async (to, from) => {
  if (to.meta.public && to.name !== "landing") return;
  if (from.name) return;

  const { data: state } = await authState();
  const cache = useQueryCache();
  cache.setQueryData(queryKeys.authState(), state);
  if (state?.user) cache.setQueryData(queryKeys.user(), state.user);

  if (state?.state === "anonymous") {
    return to.name === "landing" ? undefined : { name: "landing" };
  }
  const needsUpload =
    state?.state === "pending_signup" || !state?.user?.is_processed;
  if (needsUpload) {
    return to.name === "upload" ? undefined : { name: "upload" };
  }
  if (to.name === "landing") return { name: "editor" };
});

export default router;
