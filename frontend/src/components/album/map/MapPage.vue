<script lang="ts" setup>
import AlbumPage from "@/components/album/AlbumPage.vue";
import type { SegmentOutline, StepRead as Step } from "@/client";
import { useAlbum } from "@/composables/useAlbum";
import { useMapbox } from "@/composables/useMapbox";
import { usePrintMode } from "@/composables/usePrintReady";
import { drawSegmentsAndMarkers } from "./mapSegments";
import { useUserQuery } from "@/queries/useUserQuery";
import { useSegmentPointsQuery } from "@/queries/useSegmentPointsQuery";
import { interiorBleedMm } from "@/composables/usePrintSettings";
import { safeMarginMm, mapSafeInsetPx } from "@/composables/useSafeMargin";
import { useI18n } from "vue-i18n";
import type { Map } from "mapbox-gl";
import { useTemplateRef, computed, ref, watch } from "vue";

const { t } = useI18n();

const props = defineProps<{
  steps: Step[];
  segmentOutlines: SegmentOutline[];
}>();

const { albumId } = useAlbum();
const { locale } = useUserQuery();

const fromTime = computed(() =>
  props.segmentOutlines.length
    ? Math.min(...props.segmentOutlines.map((s) => s.start_time))
    : 0,
);
const toTime = computed(() =>
  props.segmentOutlines.length
    ? Math.max(...props.segmentOutlines.map((s) => s.end_time))
    : 0,
);

const printMode = usePrintMode();
const loadSegments = ref(printMode);
const { data: segments } = useSegmentPointsQuery(
  fromTime,
  toTime,
  loadSegments,
  !printMode,
);
const container = useTemplateRef("map");
const { map, fitBounds } = useMapbox({
  container,
  locale,
  onReady: draw,
  preserveDrawingBuffer: printMode,
  deferInit: !printMode,
  onNearViewport: () => {
    loadSegments.value = true;
  },
});

function draw(m: Map) {
  if (!segments.value) return;
  m.resize();
  drawSegmentsAndMarkers(m, {
    segments: segments.value,
    steps: props.steps,
    albumId: albumId.value,
  });
  const coords: [number, number][] = props.steps.map((s) => [
    s.location.lon,
    s.location.lat,
  ]);
  fitBounds(coords, 60 + mapSafeInsetPx());
}

watch(segments, () => {
  const m = map.value;
  if (!m) return;
  if (m.isStyleLoaded()) draw(m);
  else m.once("load", () => draw(m));
});

watch(
  [safeMarginMm, interiorBleedMm],
  () => {
    const m = map.value;
    if (!m || !segments.value || !m.isStyleLoaded()) return;
    m.resize();
    const coords: [number, number][] = props.steps.map((s) => [
      s.location.lon,
      s.location.lat,
    ]);
    fitBounds(coords, 60 + mapSafeInsetPx());
  },
  { flush: "post" },
);
</script>

<template>
  <AlbumPage
    role="img"
    :aria-label="t('album.tripRouteMap')"
    class="map-page relative-position"
  >
    <div ref="map" class="map-background" />
  </AlbumPage>
</template>

<style scoped>
.map-background {
  position: absolute;
  inset: calc(-1 * var(--bleed));
}
</style>
