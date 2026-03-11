<script lang="ts" setup>
import type { Segment, Step } from "@/client";
import { useMapbox } from "@/composables/useMapbox";
import { drawSegmentsAndMarkers } from "@/composables/useMapSegments";
import { useUserQuery } from "@/queries/useUserQuery";
import { onMounted, useTemplateRef } from "vue";
import "mapbox-gl/dist/mapbox-gl.css";

const props = defineProps<{
  steps: Step[];
  segments: Segment[];
}>();

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
  }).then((coords) => fitBounds(coords, 60));
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
