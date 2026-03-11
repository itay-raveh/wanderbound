import MapboxLanguage from "@mapbox/mapbox-gl-language";
import mapboxgl from "mapbox-gl";

import { onBeforeUnmount, shallowRef, ref, type Ref } from "vue";

mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN;

export interface UseMapboxOptions {
  container: Ref<HTMLElement | null>;
  style?: string;
  interactive?: boolean;
  onReady?: (map: mapboxgl.Map) => void;
  preserveDrawingBuffer?: boolean;
  /** BCP 47 locale for map labels (e.g. "he-IL", "en-US"). Uses language part. */
  locale?: string;
}

export function useMapbox(options: UseMapboxOptions) {
  const map = shallowRef<mapboxgl.Map | null>(null);
  const imageData = ref<string | null>(null);

  function init() {
    if (!options.container.value || map.value) return;

    const m = new mapboxgl.Map({
      container: options.container.value,
      style: options.style ?? "mapbox://styles/mapbox/satellite-streets-v12",
      projection: "mercator",
      interactive: options.interactive ?? false,
      attributionControl: false,
      preserveDrawingBuffer: options.preserveDrawingBuffer ?? true,
      fadeDuration: 0,
    });

    // Set map labels to user's language
    const lang = options.locale?.split("-")[0] ?? navigator.language.split("-")[0];
    m.addControl(new MapboxLanguage({ defaultLanguage: lang }));

    m.on("idle", () => {
      try {
        imageData.value = m.getCanvas().toDataURL("image/png");
      } catch {
        // canvas tainted or not ready
      }
    });

    m.on("load", () => {
      options.onReady?.(m);
    });

    map.value = m;
  }

  function destroy() {
    map.value?.remove();
    map.value = null;
  }

  function fitBounds(coords: [number, number][], padding: number = 80) {
    if (!map.value || coords.length === 0) return;
    const bounds = new mapboxgl.LngLatBounds();
    for (const [lng, lat] of coords) {
      bounds.extend([lng, lat]);
    }
    map.value.fitBounds(bounds, { padding, duration: 0 });
  }

  onBeforeUnmount(destroy);

  return { map, imageData, init, fitBounds };
}
