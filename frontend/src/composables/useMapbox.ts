import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";

import { frontendConfig } from "@/config";
import { useResizeObserver } from "@vueuse/core";
import {
  onBeforeUnmount,
  onMounted,
  shallowRef,
  toValue,
  watch,
  type MaybeRefOrGetter,
  type Ref,
} from "vue";

mapboxgl.accessToken = frontendConfig.VITE_MAPBOX_TOKEN ?? "";

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
  const map = shallowRef<mapboxgl.Map | null>(null);
  let pendingIdle: (() => void) | null = null;
  let initIdleHandle: number | null = null;
  let initTimeout: ReturnType<typeof setTimeout> | null = null;
  let visibilityTimeout: ReturnType<typeof setTimeout> | null = null;
  let initIntersectionObserver: IntersectionObserver | null = null;

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
      // Mark ready on error so PrintView doesn't wait forever.
      el.dataset.mapReady = "";
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
    delete el.dataset.mapReady;
    delete el.dataset.mapSnapshotReady;
    let attempts = 0;
    const markReady = () => {
      if (options.preserveDrawingBuffer) snapshotCanvasForPrint(el, m);
      el.dataset.mapReady = "";
      pendingIdle = null;
      if (idleFallback !== null) {
        clearTimeout(idleFallback);
        idleFallback = null;
      }
    };
    const check = () => {
      if (!m.areTilesLoaded() && ++attempts < 20) {
        m.once("idle", check);
        return;
      }
      markReady();
    };
    pendingIdle = check;
    m.once("idle", check);
    // Absolute fallback: mark ready after 30s even if idle never fires
    // (e.g. WebGL context loss). Prevents map staying invisible forever.
    idleFallback = setTimeout(() => {
      if (!el.dataset.mapReady) markReady();
    }, 30_000);
  }

  function snapshotCanvasForPrint(el: HTMLElement, m: mapboxgl.Map) {
    try {
      const canvas = m.getCanvas();
      if (canvas.width === 0 || canvas.height === 0) return;

      let snapshot = el.querySelector<HTMLImageElement>(
        ":scope > .mapbox-print-snapshot",
      );
      if (!snapshot) {
        snapshot = document.createElement("img");
        snapshot.className = "mapbox-print-snapshot";
        snapshot.alt = "";
        snapshot.setAttribute("aria-hidden", "true");
        el.prepend(snapshot);
      }
      snapshot.src = canvas.toDataURL("image/png");
      el.dataset.mapSnapshotReady = "";
    } catch (e) {
      console.warn("[mapbox] failed to snapshot print canvas:", e);
    }
  }

  function disarmIdleReady(m: mapboxgl.Map) {
    if (pendingIdle) {
      m.off("idle", pendingIdle);
      pendingIdle = null;
    }
    if (idleFallback !== null) {
      clearTimeout(idleFallback);
      idleFallback = null;
    }
  }

  function destroy() {
    if (map.value) disarmIdleReady(map.value);
    map.value?.remove();
    map.value = null;
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
