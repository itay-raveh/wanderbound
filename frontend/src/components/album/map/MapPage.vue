<script lang="ts" setup>
import type { Segment, Step } from "@/client";
import { useAlbum } from "@/composables/useAlbum";
import { useMapbox } from "@/composables/useMapbox";
import { drawSegmentsAndMarkers } from "@/utils/mapSegments";
import { useUserQuery } from "@/queries/useUserQuery";
import { onMounted, useTemplateRef } from "vue";

const props = defineProps<{
  steps: Step[];
  segments: Segment[];
}>();

const { albumId } = useAlbum();
const { locale } = useUserQuery();
const container = useTemplateRef("map");
const { map, init, fitBounds, startResizeObserver } = useMapbox({ container, locale });

function doLoad() {
  const m = map.value;
  if (!m) return;
  m.resize();
  void drawSegmentsAndMarkers(m, {
    segments: props.segments,
    steps: props.steps,
    albumId: albumId.value,
  }).then(() => {
    // Fit bounds to step locations, not segment paths — a driving segment
    // spanning days could pull the viewport far beyond the relevant area.
    const coords: [number, number][] = props.steps.map((s) => [s.location.lon, s.location.lat]);
    fitBounds(coords, 60);
  });
}

onMounted(() => {
  init();
  startResizeObserver();
  map.value?.on("load", () => {
    requestAnimationFrame(doLoad);
  });
});
</script>

<template>
  <div ref="map" class="page-container map-page" />
</template>

<style lang="scss" scoped>
.map-page {
  position: relative;
  overflow: hidden;
}
</style>
