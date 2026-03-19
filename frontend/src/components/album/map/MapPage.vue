<script lang="ts" setup>
import type { Segment, Step } from "@/client";
import { useAlbum } from "@/composables/useAlbum";
import { useMapbox } from "@/composables/useMapbox";
import { drawSegmentsAndMarkers } from "./mapSegments";
import { useUserQuery } from "@/queries/useUserQuery";
import type { Map } from "mapbox-gl";
import { useTemplateRef, watch } from "vue";

const props = defineProps<{
  steps: Step[];
  segments: Segment[];
}>();

const { albumId } = useAlbum();
const { locale } = useUserQuery();
const container = useTemplateRef("map");
const { map, fitBounds } = useMapbox({ container, locale, onReady: draw });

function draw(m: Map) {
  m.resize();
  drawSegmentsAndMarkers(m, {
    segments: props.segments,
    steps: props.steps,
    albumId: albumId.value,
  });
  const coords: [number, number][] = props.steps.map((s) => [
    s.location.lon,
    s.location.lat,
  ]);
  fitBounds(coords, 60);
}

watch(
  [() => props.segments, () => props.steps],
  () => { if (map.value) draw(map.value); },
);
</script>

<template>
  <div ref="map" class="page-container map-page relative-position overflow-hidden" />
</template>
