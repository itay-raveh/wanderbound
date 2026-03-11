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
const { map, init, fitBounds } = useMapbox({ container, locale: locale.value });

onMounted(() => {
  init();
  map.value?.on("load", () => {
    const m = map.value!;
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
  position: relative;
  overflow: hidden;
}
</style>
