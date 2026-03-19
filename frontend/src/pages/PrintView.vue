<script lang="ts" setup>
import AlbumViewer from "@/components/AlbumViewer.vue";
import { useAlbumQuery } from "@/queries/useAlbumQuery";
import { useAlbumDataQuery } from "@/queries/useAlbumDataQuery";
import { useUserQuery } from "@/queries/useUserQuery";
import { useLocale } from "@/composables/useLocale";
import { useI18n } from "vue-i18n";
import { Dark } from "quasar";
import { computed, onMounted } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const aid = computed(() => (route.params.aid as string) || null);
const darkMode = computed(() => route.query.dark === "true");

onMounted(() => Dark.set(darkMode.value));

const { data: album, error } = useAlbumQuery(aid);
const { data: albumData } = useAlbumDataQuery(aid);
const { locale } = useUserQuery();
const { t } = useI18n();
useLocale(locale);

/**
 * Force-load every registered Inter font face.
 * Our @font-face rules use font-display:block, but explicitly calling
 * FontFace.load() ensures the woff2 files are downloaded and activated
 * before we signal readiness to Playwright.
 */
async function loadFonts(): Promise<void> {
  const faces: Promise<FontFace>[] = [];
  for (const face of document.fonts) {
    if (face.family === "Inter") faces.push(face.load());
  }
  if (faces.length) {
    await Promise.all(faces);
    console.log("[print] loaded", faces.length, "Inter font faces");
  } else {
    console.warn("[print] no Inter font faces found — falling back to document.fonts.ready");
    await document.fonts.ready;
  }
}

/**
 * Signal Playwright that the page is ready for PDF capture.
 *
 * Polls for: album container → expected page count → all images loaded,
 * then waits for fonts and a short map-tile grace before setting
 * window.__PRINT_READY__.
 */
function waitForPrintReady() {
  const MAX_WAIT = 45_000;
  const startTime = Date.now();
  let waiting = false;

  // Kick off font loading immediately — don't wait for images
  const fontsReady = loadFonts();

  function poll() {
    if (waiting) return;
    if (Date.now() - startTime > MAX_WAIT) {
      console.warn("[print] timed out, forcing ready");
      setReady();
      return;
    }

    const container = document.querySelector<HTMLElement>(".album-container");
    if (!container) { setTimeout(poll, 100); return; }

    const expected = parseInt(container.dataset.expectedPages || "0", 10);
    const actual = container.querySelectorAll(".page-container").length;
    if (actual < expected) {
      console.log("[print] pages:", actual, "/", expected);
      setTimeout(poll, 500);
      return;
    }

    const pending = Array.from(
      document.querySelectorAll<HTMLImageElement>("[data-media] img"),
    ).filter((img) => !img.complete);
    if (pending.length > 0) {
      console.log("[print]", pending.length, "images still loading");
      setTimeout(poll, 300);
      return;
    }

    // All DOM content ready — wait for fonts, then a short grace for map tiles
    waiting = true;
    console.log("[print] content ready,", actual, "pages — waiting for fonts");
    fontsReady
      .then(() => { console.log("[print] fonts confirmed"); setTimeout(setReady, 500); })
      .catch(() => { console.warn("[print] font load failed, proceeding"); setReady(); });
  }

  function setReady() {
    (window as unknown as Record<string, boolean>).__PRINT_READY__ = true;
  }

  poll();
}

onMounted(waitForPrintReady);
</script>

<template>
  <div class="print-view">
    <div v-if="error" class="status-message flex flex-center text-negative">
      {{ t("print.loadFailed") }} {{ error.message }}
    </div>
    <AlbumViewer v-else-if="album && albumData" :album="album" :data="albumData" print-mode />
    <div v-else class="status-message flex flex-center text-muted">{{ t("print.loading") }}</div>
  </div>
</template>

<style lang="scss">
html,
body,
#app {
  height: auto !important;
  overflow: visible !important;
  margin: 0 !important;
  padding: 0 !important;
  background: var(--page-bg, var(--bg)) !important;
}

// Force exact background/color rendering in print.
* {
  print-color-adjust: exact !important;
  -webkit-print-color-adjust: exact !important;
}


.status-message {
  height: 100vh;
  font-size: 1.5rem;
}

@page {
  size: A4 landscape;
  margin: 0;
}
</style>
