import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";

import { useResizeObserver } from "@vueuse/core";
import {
  getPrintCpuCount,
  getPrintTimeoutMs,
} from "@/composables/usePrintReady";
import { getSettings } from "@/config";
import {
  onBeforeUnmount,
  onMounted,
  shallowRef,
  toValue,
  watch,
  type MaybeRefOrGetter,
  type Ref,
} from "vue";

// Disable telemetry to avoid CORS errors from events.mapbox.com
Object.defineProperty(
  (mapboxgl as unknown as { config: object }).config,
  "EVENTS_URL",
  { value: null },
);

// Register RTL text plugin once (needed for Hebrew/Arabic label rendering)
mapboxgl.setRTLTextPlugin(
  "https://api.mapbox.com/mapbox-gl-js/plugins/mapbox-gl-rtl-text/v0.3.0/mapbox-gl-rtl-text.js",
  null, // no callback
  true, // lazy: only load when RTL text is encountered
);

const MAP_INIT_ROOT_MARGIN_PX = 200;
const MAP_VISIBILITY_SETTLE_MS = 100;
const MAX_CONCURRENT_PRINT_MAPS = 4;
const PRINT_MAPS_PER_CPU = 2;
const PRINT_PIXEL_RATIO = 2;
const PRINT_TILE_SETTLE_MS = 2_000;

let activePrintMaps = 0;
const queuedPrintMaps: Array<() => void> = [];
let printPixelRatioUsers = 0;

function maxConcurrentPrintMaps(): number {
  return Math.min(
    MAX_CONCURRENT_PRINT_MAPS,
    (getPrintCpuCount() ?? 2) * PRINT_MAPS_PER_CPU,
  );
}

function acquirePrintPixelRatio(): () => void {
  printPixelRatioUsers++;
  if (printPixelRatioUsers === 1) {
    Object.defineProperty(window, "devicePixelRatio", {
      configurable: true,
      value: PRINT_PIXEL_RATIO,
    });
  }
  let released = false;
  return () => {
    if (released) return;
    released = true;
    printPixelRatioUsers--;
    if (printPixelRatioUsers === 0)
      Reflect.deleteProperty(window, "devicePixelRatio");
  };
}

function enqueuePrintMap(start: (release: () => void) => void): () => void {
  let state: "queued" | "active" | "done" = "queued";

  const drain = () => {
    while (
      activePrintMaps < maxConcurrentPrintMaps() &&
      queuedPrintMaps.length > 0
    ) {
      queuedPrintMaps.shift()?.();
    }
  };
  const release = () => {
    if (state === "done") return;
    if (state === "queued") {
      const index = queuedPrintMaps.indexOf(run);
      if (index !== -1) queuedPrintMaps.splice(index, 1);
    } else {
      activePrintMaps--;
    }
    state = "done";
    drain();
  };
  const run = () => {
    if (state !== "queued") return;
    state = "active";
    activePrintMaps++;
    start(release);
  };

  queuedPrintMaps.push(run);
  drain();
  return release;
}

interface UseMapboxOptions {
  container: Ref<HTMLElement | null>;
  style?: string;
  interactive?: boolean;
  onReady?: (map: mapboxgl.Map) => void;
  preserveDrawingBuffer?: boolean;
  deferInit?: boolean;
  onNearViewport?: () => void;
  /** BCP 47 locale for map labels (e.g. "he-IL", "en-US"). Accepts ref/getter. */
  locale?: MaybeRefOrGetter<string>;
}

function langFromLocale(locale: string | undefined): string {
  return locale?.split("-")[0] || navigator.language.split("-")[0] || "en";
}

export function useMapbox(options: UseMapboxOptions) {
  mapboxgl.accessToken = getSettings().MAPBOX_TOKEN ?? "";
  const map = shallowRef<mapboxgl.Map | null>(null);
  let pendingRender: (() => void) | null = null;
  let readinessTimer: ReturnType<typeof setTimeout> | null = null;
  let readinessGeneration = 0;
  let initIdleHandle: number | null = null;
  let initTimeout: ReturnType<typeof setTimeout> | null = null;
  let visibilityTimeout: ReturnType<typeof setTimeout> | null = null;
  let initIntersectionObserver: IntersectionObserver | null = null;
  let releasePrintSlot: (() => void) | null = null;
  let releasePrintPixelRatio: (() => void) | null = null;

  function init() {
    if (!options.container.value || map.value) return;

    const lang = langFromLocale(toValue(options.locale));
    const el = options.container.value;

    // Mark container as a map page so PrintView can wait for readiness.
    el.dataset.map = "";

    try {
      const m = new mapboxgl.Map({
        container: el,
        style: options.style ?? "mapbox://styles/mapbox/standard-satellite",
        projection: "mercator",
        interactive: options.interactive ?? false,
        attributionControl: false,
        preserveDrawingBuffer: options.preserveDrawingBuffer ?? false,
        performanceMetricsCollection: false,
        fadeDuration: 0,
        language: lang,
        config: {
          basemap: {
            showPointOfInterestLabels: false,
            showRoadsAndTransit: false,
            showRoadLabels: false,
            showPedestrianRoads: false,
            showTransitLabels: false,
          },
        },
      });

      map.value = m;

      m.on("load", () => {
        options.onReady?.(m);
      });

      // Signal readiness after all tiles from the initial render are loaded.
      armIdleReady(el, m);
    } catch (e) {
      console.warn("[mapbox] failed to initialise map:", e);
      if (options.preserveDrawingBuffer) {
        el.dataset.mapError = "initialization-failed";
        releasePrintMapSlot();
      } else {
        el.dataset.mapReady = "";
      }
    }
  }

  if (options.locale) {
    watch(
      () => toValue(options.locale),
      (newLocale) => {
        const m = map.value;
        if (!m) return;
        m.setLanguage(langFromLocale(newLocale));
      },
    );
  }

  let idleFallback: ReturnType<typeof setTimeout> | null = null;

  function armIdleReady(el: HTMLElement, m: mapboxgl.Map) {
    disarmIdleReady(m);
    const generation = ++readinessGeneration;
    let tilesLoadedAt: number | null = null;
    delete el.dataset.mapReady;
    delete el.dataset.mapSnapshotReady;
    delete el.dataset.mapError;
    const markReady = () => {
      if (generation !== readinessGeneration) return;
      el.dataset.mapReady = "";
      pendingRender = null;
      if (readinessTimer !== null) {
        clearTimeout(readinessTimer);
        readinessTimer = null;
      }
      if (idleFallback !== null) {
        clearTimeout(idleFallback);
        idleFallback = null;
      }
      if (options.preserveDrawingBuffer) disposePrintMap(el, m, true);
    };
    const markError = (code: string) => {
      if (generation !== readinessGeneration) return;
      el.dataset.mapError = code;
      pendingRender = null;
      if (readinessTimer !== null) {
        clearTimeout(readinessTimer);
        readinessTimer = null;
      }
      if (idleFallback !== null) {
        clearTimeout(idleFallback);
        idleFallback = null;
      }
      if (options.preserveDrawingBuffer) disposePrintMap(el, m, false);
    };
    const capture = async () => {
      if (generation !== readinessGeneration) return;
      pendingRender = null;
      if (await snapshotCanvasForPrint(el, m, generation)) markReady();
      else markError("snapshot-failed");
    };
    let captureStarted = false;
    const startCapture = () => {
      if (captureStarted || generation !== readinessGeneration) return;
      captureStarted = true;
      if (readinessTimer !== null) {
        clearTimeout(readinessTimer);
        readinessTimer = null;
      }
      if (pendingRender) {
        m.off("render", pendingRender);
        pendingRender = null;
      }
      void capture();
    };
    const check = () => {
      if (generation !== readinessGeneration) return;
      readinessTimer = null;
      if (!m.isStyleLoaded() || !m.areTilesLoaded()) {
        tilesLoadedAt = null;
        readinessTimer = setTimeout(check, 250);
        return;
      }
      if (!options.preserveDrawingBuffer) {
        markReady();
        return;
      }
      tilesLoadedAt ??= Date.now();
      if (!m.idle() && Date.now() - tilesLoadedAt < PRINT_TILE_SETTLE_MS) {
        readinessTimer = setTimeout(check, 250);
        return;
      }
      pendingRender = startCapture;
      m.once("render", pendingRender);
      m.triggerRepaint();
      readinessTimer = setTimeout(startCapture, 500);
    };
    readinessTimer = setTimeout(check, 0);
    // Preview maps remain fail-open so a lost WebGL context does not leave the
    // editor blank. Print maps must fail the export instead of hiding damage.
    idleFallback = setTimeout(
      () => {
        if (el.dataset.mapReady || el.dataset.mapError) return;
        if (options.preserveDrawingBuffer) markError("render-timeout");
        else markReady();
      },
      Math.max(300_000, getPrintTimeoutMs() - 60_000),
    );
  }

  function disposePrintMap(
    el: HTMLElement,
    m: mapboxgl.Map,
    preserveMarkers: boolean,
  ) {
    if (preserveMarkers) {
      const markers = el.querySelectorAll<HTMLElement>(".mapboxgl-marker");
      if (markers.length > 0) {
        const overlay = document.createElement("div");
        overlay.className = "mapbox-print-marker-overlay";
        overlay.setAttribute("aria-hidden", "true");
        for (const marker of markers) overlay.append(marker.cloneNode(true));
        el.append(overlay);
      }
    }
    disarmIdleReady(m);
    m.remove();
    if (map.value === m) map.value = null;
    releasePrintMapSlot();
  }

  function releasePrintMapSlot() {
    releasePrintSlot?.();
    releasePrintSlot = null;
    releasePrintPixelRatio?.();
    releasePrintPixelRatio = null;
  }

  async function snapshotCanvasForPrint(
    el: HTMLElement,
    m: mapboxgl.Map,
    generation: number,
  ): Promise<boolean> {
    try {
      const canvas = m.getCanvas();
      if (canvas.width === 0 || canvas.height === 0) return false;

      const cssWidth = canvas.clientWidth || el.clientWidth;
      const cssHeight = canvas.clientHeight || el.clientHeight;
      if (cssWidth === 0 || cssHeight === 0) return false;

      const blob = await new Promise<Blob | null>((resolve) =>
        canvas.toBlob(resolve, "image/jpeg", 0.95),
      );
      if (!blob || generation !== readinessGeneration) return false;

      const snapshot = document.createElement("img");
      snapshot.className = "mapbox-print-snapshot";
      snapshot.alt = "";
      snapshot.setAttribute("aria-hidden", "true");
      snapshot.decoding = "async";
      const objectUrl = URL.createObjectURL(blob);
      await new Promise<void>((resolve, reject) => {
        snapshot.addEventListener("load", () => resolve(), { once: true });
        snapshot.addEventListener(
          "error",
          () => reject(new Error("image load failed")),
          { once: true },
        );
        snapshot.src = objectUrl;
      });
      if (generation !== readinessGeneration) return false;
      el.prepend(snapshot);
      el.dataset.mapSnapshotReady = "";
      return true;
    } catch (e) {
      console.warn("[mapbox] failed to snapshot print canvas:", e);
      return false;
    }
  }

  function disarmIdleReady(m: mapboxgl.Map) {
    if (readinessTimer !== null) {
      clearTimeout(readinessTimer);
      readinessTimer = null;
    }
    if (pendingRender) {
      m.off("render", pendingRender);
      pendingRender = null;
    }
    if (idleFallback !== null) {
      clearTimeout(idleFallback);
      idleFallback = null;
    }
  }

  function destroy() {
    readinessGeneration++;
    if (map.value) disarmIdleReady(map.value);
    map.value?.remove();
    map.value = null;
    releasePrintMapSlot();
  }

  function fitBounds(
    coords: [number, number][],
    padding:
      | number
      | { top: number; bottom: number; left: number; right: number } = 80,
  ) {
    if (!map.value || coords.length === 0) return;

    const bounds = new mapboxgl.LngLatBounds();
    for (const [lng, lat] of coords) {
      bounds.extend([lng, lat]);
    }
    map.value.fitBounds(bounds, { padding, duration: 0 });

    // Re-arm readiness: the new viewport requires new tiles.
    const el = options.container.value;
    if (el) armIdleReady(el, map.value);
  }

  function scheduleInit() {
    if (options.preserveDrawingBuffer) {
      const el = options.container.value;
      if (el) el.dataset.map = "";
      releasePrintPixelRatio = acquirePrintPixelRatio();
      releasePrintSlot = enqueuePrintMap((release) => {
        releasePrintSlot = release;
        init();
      });
      return;
    }
    if (!options.deferInit) {
      init();
      return;
    }

    const scheduleIdleInit = () => {
      options.onNearViewport?.();
      if ("requestIdleCallback" in window) {
        initIdleHandle = window.requestIdleCallback(() => {
          initIdleHandle = null;
          init();
        });
        return;
      }
      initTimeout = setTimeout(() => {
        initTimeout = null;
        init();
      }, 0);
    };

    const el = options.container.value;
    if (!el || !("IntersectionObserver" in window)) {
      scheduleIdleInit();
      return;
    }

    initIntersectionObserver = new IntersectionObserver(
      (entries) => {
        if (
          !entries.some((entry) => entry.isIntersecting) ||
          visibilityTimeout !== null
        )
          return;
        // Header correction can briefly move an overscanned map through the viewport.
        // Recheck after layout settles before loading its full GPS payload.
        visibilityTimeout = setTimeout(() => {
          visibilityTimeout = null;
          const rect = el.getBoundingClientRect();
          if (
            rect.bottom < -MAP_INIT_ROOT_MARGIN_PX ||
            rect.top > window.innerHeight + MAP_INIT_ROOT_MARGIN_PX
          )
            return;
          initIntersectionObserver?.disconnect();
          initIntersectionObserver = null;
          scheduleIdleInit();
        }, MAP_VISIBILITY_SETTLE_MS);
      },
      { rootMargin: `${MAP_INIT_ROOT_MARGIN_PX}px` },
    );
    initIntersectionObserver.observe(el);
  }

  function cancelScheduledInit() {
    initIntersectionObserver?.disconnect();
    initIntersectionObserver = null;
    if (visibilityTimeout !== null) {
      clearTimeout(visibilityTimeout);
      visibilityTimeout = null;
    }
    if (initIdleHandle !== null) {
      window.cancelIdleCallback(initIdleHandle);
      initIdleHandle = null;
    }
    if (initTimeout !== null) {
      clearTimeout(initTimeout);
      initTimeout = null;
    }
  }

  useResizeObserver(options.container, () => map.value?.resize());

  onMounted(scheduleInit);
  onBeforeUnmount(() => {
    cancelScheduledInit();
    destroy();
  });

  return { map, fitBounds };
}
