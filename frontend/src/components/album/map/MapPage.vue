<script lang="ts" setup>
import type { Segment, Step } from "@/client";
import { useMapbox } from "@/composables/useMapbox";
import { drawSegmentsAndMarkers } from "@/composables/useMapSegments";
import { onMounted, useTemplateRef } from "vue";
import "mapbox-gl/dist/mapbox-gl.css";

const props = defineProps<{
  steps: Step[];
  segments: Segment[];
}>();

const container = useTemplateRef("map");
const { map, init, fitBounds } = useMapbox({ container });

onMounted(() => {
  init();
  map.value?.on("load", () => {
    const m = map.value!;
    // Force recalculate size after CSS is applied
    m.resize();
    void drawSegmentsAndMarkers(m, {
      segments: props.segments,
      steps: props.steps,
      skipMapMatching: true,
    }).then((coords) => fitBounds(coords, 100));
  });
});
</script>

<template>
  <div ref="map" class="page-container map-page" />
</template>

<style lang="scss" scoped>
.map-page {
  padding: 0 !important;
  position: relative;
  overflow: hidden;
}
</style>
