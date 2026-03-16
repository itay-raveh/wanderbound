<script lang="ts" setup>
import type { Segment, Step } from "@/client";
import { useAlbum } from "@/composables/useAlbum";
import { useMapbox } from "@/composables/useMapbox";
import { drawSegmentsAndMarkers } from "./mapSegments";
import { useUserQuery } from "@/queries/useUserQuery";
import { useTemplateRef } from "vue";

const props = defineProps<{
  steps: Step[];
  segments: Segment[];
}>();

const { albumId } = useAlbum();
const { locale } = useUserQuery();
const container = useTemplateRef("map");
const { fitBounds } = useMapbox({
  container,
  locale,
  onReady: (m) => {
    m.resize();
    drawSegmentsAndMarkers(m, {
      segments: props.segments,
      steps: props.steps,
      albumId: albumId.value,
    });
    // Fit bounds to step locations, not segment paths — a driving segment
    // spanning days could pull the viewport far beyond the relevant area.
    const coords: [number, number][] = props.steps.map((s) => [
      s.location.lon,
      s.location.lat,
    ]);
    fitBounds(coords, 60);
  },
});
</script>

<template>
  <div ref="map" class="page-container map-page relative-position overflow-hidden" />
</template>
