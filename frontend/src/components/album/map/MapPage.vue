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
    void drawSegmentsAndMarkers(map.value!, {
      segments: props.segments,
      steps: props.steps,
    }).then((coords) => fitBounds(coords, 100));
  });
});
</script>

<template>
  <div ref="map" class="page-container" />
</template>
