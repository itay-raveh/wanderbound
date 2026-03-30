<script lang="ts" setup>
import type { SegmentOutline, Step } from "@/client";
import { useAlbum } from "@/composables/useAlbum";
import { useMapbox } from "@/composables/useMapbox";
import { drawSegmentsAndMarkers } from "./mapSegments";
import { useUserQuery } from "@/queries/useUserQuery";
import { useSegmentPointsQuery } from "@/queries/useSegmentPointsQuery";
import { useI18n } from "vue-i18n";
import type { Map } from "mapbox-gl";
import { useTemplateRef, computed, watch } from "vue";

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

const { data: segments } = useSegmentPointsQuery(fromTime, toTime);

const container = useTemplateRef("map");
const { map, fitBounds } = useMapbox({ container, locale, onReady: draw });

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
  fitBounds(coords, 60);
}

watch(segments, () => {
  const m = map.value;
  if (!m) return;
  if (m.isStyleLoaded()) draw(m);
  else m.once("load", () => draw(m));
});
</script>

<template>
  <div ref="map" role="img" :aria-label="t('album.tripRouteMap')" class="page-container map-page relative-position overflow-hidden" />
</template>
