import EditorView from "@/pages/EditorView.vue";
import { readUser } from "@/client";
import { createRouter, createWebHistory } from "vue-router";

export const CREDENTIAL_KEY = "google_credential";

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
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
      component: EditorView,
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
  // Public routes other than landing skip auth entirely
  if (to.meta.public && to.name !== "landing") return;

  // New user after Google sign-in: has credential but no session yet
  if (to.name === "upload" && sessionStorage.getItem(CREDENTIAL_KEY)) return;

  // In-app navigations: session was already verified on initial load
  if (from.name) return;

  // Initial page load: verify session with server
  let user;
  try {
    ({ data: user } = await readUser());
  } catch {
    // Not authenticated: landing is fine, everything else → landing
    if (to.name === "landing") return;
    return { name: "landing" };
  }

  // Authenticated user on landing → redirect to editor or upload
  if (to.name === "landing") {
    return user.album_ids?.length && user.has_data
      ? { name: "editor" }
      : { name: "upload" };
  }

  // Redirect to upload if user has no albums or was evicted (has albums but no data)
  if (!user.album_ids?.length || !user.has_data) {
    return { name: "upload" };
  }
});

export default router;
