import { readUser } from "@/client";
import type { BodyUploadData } from "@/client";
import { useQueryCache } from "@pinia/colada";
import { useSessionStorage } from "@vueuse/core";
import { createRouter, createWebHistory } from "vue-router";
import { queryKeys } from "@/queries/keys";

import { AUTH_STATE_KEY } from "@/utils/storage-keys";

export type Provider = NonNullable<BodyUploadData["provider"]>;

interface AuthState {
  credential: string;
  provider: Provider;
}

const authState = useSessionStorage<AuthState | null>(AUTH_STATE_KEY, null);

export function getAuthState(): AuthState | null {
  return authState.value;
}

export function setAuthState(credential: string, provider: Provider): void {
  authState.value = { credential, provider };
}

export function clearAuthState(): void {
  authState.value = null;
}

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
  // Public routes other than landing skip auth entirely
  if (to.meta.public && to.name !== "landing") return;

  // New user after sign-in: has credential but no session yet
  if (to.name === "upload" && getAuthState()) return;

  // In-app navigations: session was already verified on initial load
  if (from.name) return;

  // Initial page load: verify session with server
  let user;
  try {
    ({ data: user } = await readUser());
    useQueryCache().setQueryData(queryKeys.user(), user);
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
