import mapboxgl from "mapbox-gl";

import { onBeforeUnmount, shallowRef, toValue, watch, type MaybeRefOrGetter, type Ref } from "vue";

mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN;

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

    const m = new mapboxgl.Map({
      container: options.container.value,
      style: options.style ?? "mapbox://styles/mapbox/satellite-streets-v12",
      projection: "mercator",
      interactive: options.interactive ?? false,
      attributionControl: false,
      preserveDrawingBuffer: options.preserveDrawingBuffer ?? true,
      fadeDuration: 0,
      language: lang,
    });

    m.on("load", () => {
      options.onReady?.(m);
    });

    map.value = m;
  }

  // Update language dynamically when locale changes
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
  let resizeRaf = 0;

  function startResizeObserver() {
    const el = options.container.value;
    if (!el) return;
    resizeObserver = new ResizeObserver(() => {
      cancelAnimationFrame(resizeRaf);
      resizeRaf = requestAnimationFrame(() => map.value?.resize());
    });
    resizeObserver.observe(el);
  }

  onBeforeUnmount(() => {
    resizeObserver?.disconnect();
    destroy();
  });

  return { map, init, fitBounds, startResizeObserver };
}
