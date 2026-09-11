<script setup lang="ts">
import {
  computed,
  onActivated,
  onDeactivated,
  onErrorCaptured,
  ref,
  watch,
} from "vue";
import { useTimeoutFn } from "@vueuse/core";
import { useI18n } from "vue-i18n";
import type { AlbumMeta, SegmentOutline } from "@/client";
import type { PhysicalRenderItem } from "../album/albumRenderPlan";
import { providePrintMapState } from "@/composables/usePrintReady";
import PhysicalAlbumPage from "../album/PhysicalAlbumPage.vue";

const props = defineProps<{
  item: PhysicalRenderItem;
  album: AlbumMeta;
  segmentOutlines: SegmentOutline[];
  width: number;
  height: number;
  scale: number;
}>();
const { t } = useI18n();
const isMap = computed(
  () =>
    props.item.type === "map" ||
    props.item.type === "hike" ||
    (props.item.type === "header" && props.item.headerKey === "full-map"),
);
const state = providePrintMapState();
const attempt = ref(0);
const active = ref(true);
const slow = ref(false);
const { start, stop } = useTimeoutFn(
  () => {
    slow.value = true;
  },
  15_000,
  {
    immediate: isMap.value,
  },
);
watch(state, (value) => {
  if (value !== "loading") stop();
});
onErrorCaptured(() => {
  if (isMap.value) {
    state.value = "error";
    stop();
    return false;
  }
});
function retry() {
  state.value = "loading";
  slow.value = false;
  attempt.value++;
  start();
}
onDeactivated(() => {
  active.value = false;
  stop();
});
onActivated(() => {
  if (active.value) return;
  active.value = true;
  if (isMap.value && state.value !== "ready") retry();
});
</script>

<template>
  <div
    class="page-scale"
    :dir="$q.lang.rtl ? 'rtl' : 'ltr'"
    :style="{
      width: `${width}px`,
      height: `${height}px`,
      transform: `scale(${scale})`,
    }"
  >
    <PhysicalAlbumPage
      v-if="!isMap || active || state === 'ready'"
      :key="attempt"
      :item="item"
      :album="album"
      :segment-outlines="segmentOutlines"
    />
  </div>
  <div v-if="isMap && state !== 'ready'" class="map-status">
    <p role="status">
      {{ t(state === "error" ? "print.mapFailed" : "print.mapLoading") }}
    </p>
    <q-btn
      v-if="state === 'error' || slow"
      outline
      no-caps
      :label="t('print.retryMap')"
      @click="retry"
    />
  </div>
</template>

<style scoped>
.page-scale {
  position: absolute;
  pointer-events: none;
  --editor-zoom: 1;
}
/* Scaling is anchored to the physical top-left corner in both reading directions. */
/* rtl:begin:ignore */
.page-scale {
  left: 0;
  top: 0;
  transform-origin: top left;
}
/* rtl:end:ignore */
.page-scale :deep(.page-container) {
  margin: 0;
  contain: none;
}
.page-scale :deep(.mapboxgl-ctrl-logo) {
  display: none;
}
.map-status {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--gap-md);
  padding: var(--gap-lg);
  background: var(--surface);
  color: var(--text-bright);
  text-align: center;
}
.map-status p {
  margin: 0;
}
</style>
