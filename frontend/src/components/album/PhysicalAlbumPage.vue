<script setup lang="ts">
import type { AlbumMeta, SegmentOutline } from "@/client";
import type { PhysicalRenderItem } from "./albumRenderPlan";
import AlbumPage from "./AlbumPage.vue";
import { defineAsyncComponent, defineComponent, h } from "vue";
import CoverPage from "./CoverPage.vue";
import StepEntry from "./StepEntry.vue";
import AlignmentPage from "./AlignmentPage.vue";
import PanoramaSpreadPage from "./PanoramaSpreadPage.vue";
const EmptyPage = defineComponent({ render: () => h(AlbumPage) });
const MapPage = defineAsyncComponent({
  loader: () => import("./map/MapPage.vue"),
  errorComponent: EmptyPage,
  timeout: 10_000,
});
const HikeMapPage = defineAsyncComponent({
  loader: () => import("./map/HikeMapPage.vue"),
  errorComponent: EmptyPage,
  timeout: 10_000,
});
const OverviewPage = defineAsyncComponent({
  loader: () => import("./overview/OverviewPage.vue"),
  errorComponent: EmptyPage,
  timeout: 10_000,
});
defineProps<{
  item: PhysicalRenderItem;
  album: AlbumMeta;
  segmentOutlines: SegmentOutline[];
}>();
</script>

<template>
  <CoverPage
    v-if="item.type === 'header' && item.headerKey === 'cover-front'"
    :album="album"
    :chapter="item.chapter"
    :steps="item.steps"
  />
  <CoverPage
    v-else-if="item.type === 'header' && item.headerKey === 'cover-back'"
    :album="album"
    :chapter="item.chapter"
    :steps="item.steps"
    is-back
  />
  <OverviewPage
    v-else-if="item.type === 'header' && item.headerKey === 'overview'"
    :album="album"
    :segments="item.segments"
    :steps="item.steps"
  />
  <div
    v-else-if="item.type === 'header' && item.headerKey === 'full-map'"
    class="map-wrapper"
  >
    <MapPage :segment-outlines="item.segments" :steps="item.steps" />
  </div>
  <div v-else-if="item.type === 'map'" class="map-wrapper">
    <MapPage
      :segment-outlines="item.section.segments"
      :steps="item.section.steps"
    />
  </div>
  <div v-else-if="item.type === 'hike'" class="map-wrapper">
    <HikeMapPage
      :segments="item.section.segments"
      :steps="item.section.steps"
      :hike-segment="item.section.hikeSegment"
      :all-segments="segmentOutlines"
    />
  </div>
  <StepEntry
    v-else-if="item.type === 'step-page' || item.type === 'grid'"
    :step="item.step"
    :page-index="item.pageIndex"
  />
  <AlignmentPage v-else-if="item.type === 'alignment'" />
  <PanoramaSpreadPage
    v-else-if="item.type === 'panorama-spread-left'"
    :media="item.media"
    side="left"
  />
  <PanoramaSpreadPage
    v-else-if="item.type === 'panorama-spread-right'"
    :media="item.media"
    side="right"
  />
</template>
