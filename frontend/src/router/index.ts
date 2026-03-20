import EditorView from "@/pages/EditorView.vue";
import { readUser } from "@/client";
import { createRouter, createWebHistory } from "vue-router";

export const CREDENTIAL_KEY = "google_credential";

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: "/",
      name: "editor",
      component: EditorView,
    },
    {
      path: "/login",
      name: "login",
      component: () => import("@/pages/LoginView.vue"),
      meta: { public: true },
    },
    {
      path: "/upload",
      name: "upload",
      component: () => import("@/pages/UploadView.vue"),
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
  if (to.meta.public) return;

  // New user after Google sign-in: has credential but no session yet
  if (to.name === "upload" && sessionStorage.getItem(CREDENTIAL_KEY)) return;

  // In-app navigations: session was already verified on initial load
  if (from.name) return;

  // Initial page load: verify session with server
  let user;
  try {
    ({ data: user } = await readUser());
  } catch {
    return { name: "login" };
  }

  if (!user.album_ids?.length) {
    return { name: "upload" };
  }
});

export default router;
