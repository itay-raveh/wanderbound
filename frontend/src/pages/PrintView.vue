<script lang="ts" setup>
import AlbumViewer from "@/components/AlbumViewer.vue";
import { usePrintBundleQuery } from "@/queries/queries";
import { useUserQuery } from "@/queries/useUserQuery";
import { useLocale } from "@/composables/useLocale";
import { ALLOWED_FONTS } from "@/utils/fonts";
import { useI18n } from "vue-i18n";
import { Dark } from "quasar";
import { computed, onMounted, onUnmounted } from "vue";
import { useRoute } from "vue-router";
import type { SegmentOutline } from "@/client";

const route = useRoute();
const aid = computed(() => (route.params.aid as string) || null);
const darkMode = computed(() => route.query.dark === "true");

onMounted(() => Dark.set(darkMode.value));

const { data: bundle, error } = usePrintBundleQuery(aid);
const { user: userData, locale } = useUserQuery();
const { t } = useI18n();
useLocale(locale);

const album = computed(() => bundle.value?.album);
const media = computed(() => bundle.value?.album.media ?? []);
const steps = computed(() => bundle.value?.steps ?? []);
const segmentOutlines = computed<SegmentOutline[]>(() => {
  if (!bundle.value) return [];
  return bundle.value.segments.map((s) => ({
    start_time: s.start_time,
    end_time: s.end_time,
    kind: s.kind,
    timezone_id: s.timezone_id,
    start_coord: s.points.length
      ? ([s.points[0].lat, s.points[0].lon] as [number, number])
      : ([0, 0] as [number, number]),
    end_coord: s.points.length
      ? ([
          s.points[s.points.length - 1].lat,
          s.points[s.points.length - 1].lon,
        ] as [number, number])
      : ([0, 0] as [number, number]),
  }));
});

/**
 * Force-load every registered self-hosted font face.
 * Our @font-face rules use font-display:block, but explicitly calling
 * FontFace.load() ensures the woff2 files are downloaded and activated
 * before we signal readiness to Playwright.
 */
async function loadFonts(): Promise<void> {
  const families = new Set([...ALLOWED_FONTS, "JetBrains Mono"]);
  const faces: Promise<FontFace>[] = [];
  for (const face of document.fonts) {
    if (families.has(face.family)) faces.push(face.load());
  }
  if (faces.length) {
    await Promise.all(faces);
    console.log("[print] loaded", faces.length, "font faces");
  } else {
    console.warn(
      "[print] no self-hosted font faces found - falling back to document.fonts.ready",
    );
    await document.fonts.ready;
  }
}

/**
 * Signal Playwright that the page is ready for PDF capture.
 *
 * Polls for: album container -> expected page count -> all images loaded,
 * then waits for fonts and a short map-tile grace before setting
 * window.__PRINT_READY__.
 */
let pollTimer = 0;

function waitForPrintReady() {
  const MAX_WAIT = 45_000;
  const startTime = Date.now();
  let waiting = false;

  // Kick off font loading immediately - don't wait for images
  const fontsReady = loadFonts();

  function schedulePoll(ms: number) {
    clearTimeout(pollTimer);
    pollTimer = window.setTimeout(poll, ms);
  }

  function poll() {
    if (waiting) return;
    if (Date.now() - startTime > MAX_WAIT) {
      console.warn("[print] timed out, forcing ready");
      setReady();
      return;
    }

    const container = document.querySelector<HTMLElement>(".album-container");
    if (!container) {
      schedulePoll(100);
      return;
    }

    const expected = parseInt(container.dataset.expectedPages || "0", 10);
    const actual = container.querySelectorAll(".page-container").length;
    if (actual < expected) {
      console.log("[print] pages:", actual, "/", expected);
      schedulePoll(500);
      return;
    }

    const pending = Array.from(
      document.querySelectorAll<HTMLImageElement>("[data-media] img"),
    ).filter((img) => !img.complete);
    if (pending.length > 0) {
      console.log("[print]", pending.length, "images still loading");
      schedulePoll(300);
      return;
    }

    // Wait for all Mapbox maps to finish rendering tiles.
    const unreadyMaps = document.querySelectorAll(
      "[data-map]:not([data-map-ready])",
    );
    if (unreadyMaps.length > 0) {
      console.log("[print]", unreadyMaps.length, "maps still rendering");
      schedulePoll(300);
      return;
    }

    // All DOM content + maps ready - wait for fonts before signaling
    waiting = true;
    console.log("[print] content ready,", actual, "pages - waiting for fonts");
    fontsReady
      .then(() => {
        console.log("[print] fonts confirmed");
        setReady();
      })
      .catch(() => {
        console.warn("[print] font load failed, proceeding");
        setReady();
      });
  }

  function setReady() {
    clearTimeout(pollTimer);
    // Remove trailing page break to prevent an empty last page in PDF output.
    const pages = document.querySelectorAll(".page-container");
    if (pages.length) {
      (pages[pages.length - 1] as HTMLElement).style.breakAfter = "auto";
    }
    (window as unknown as Record<string, boolean>).__PRINT_READY__ = true;
  }

  poll();
}

onMounted(waitForPrintReady);
onUnmounted(() => clearTimeout(pollTimer));
</script>

<template>
  <div class="print-view">
    <div v-if="error" class="status-message flex flex-center text-negative">
      {{ t("error.loadAlbum") }} {{ error.message }}
    </div>
    <AlbumViewer
      v-else-if="bundle"
      :album="album!"
      :media="media"
      :steps="steps"
      :segment-outlines="segmentOutlines"
      print-mode
      :photos-connected="!!userData?.google_photos_connected_at"
    />
    <div v-else class="status-message flex flex-center text-muted">
      {{ t("common.loadingAlbum") }}
    </div>
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
