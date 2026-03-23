import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";

import { onBeforeUnmount, onMounted, shallowRef, toValue, watch, type MaybeRefOrGetter, type Ref } from "vue";

mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN;

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

export interface UseMapboxOptions {
  container: Ref<HTMLElement | null>;
  style?: string;
  interactive?: boolean;
  onReady?: (map: mapboxgl.Map) => void;
  preserveDrawingBuffer?: boolean;
  /** BCP 47 locale for map labels (e.g. "he-IL", "en-US"). Accepts ref/getter. */
  locale?: MaybeRefOrGetter<string>;
}

function langFromLocale(locale: string | undefined): string {
  return locale?.split("-")[0] || navigator.language.split("-")[0] || "en";
}

export function useMapbox(options: UseMapboxOptions) {
  const map = shallowRef<mapboxgl.Map | null>(null);

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
          },
        },
      });

      map.value = m;

      m.on("load", () => {
        options.onReady?.(m);
      });

      // Signal readiness after all tiles from the initial render are loaded.
      m.once("idle", () => {
        el.dataset.mapReady = "";
      });
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

  function destroy() {
    map.value?.remove();
    map.value = null;
  }

  function fitBounds(
    coords: [number, number][],
    padding: number | { top: number; bottom: number; left: number; right: number } = 80,
  ) {
    if (!map.value || coords.length === 0) return;
    const bounds = new mapboxgl.LngLatBounds();
    for (const [lng, lat] of coords) {
      bounds.extend([lng, lat]);
    }
    map.value.fitBounds(bounds, { padding, duration: 0 });
  }

  // Auto-resize map when container dimensions change (CSS zoom settling, etc.)
  let resizeObserver: ResizeObserver | null = null;

  onMounted(() => {
    init();

    const el = options.container.value;
    if (el) {
      resizeObserver = new ResizeObserver(() => map.value?.resize());
      resizeObserver.observe(el);
    }
  });

  onBeforeUnmount(() => {
    resizeObserver?.disconnect();
    destroy();
  });

  return { map, fitBounds };
}
