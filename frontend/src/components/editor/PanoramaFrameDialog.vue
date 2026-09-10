<script lang="ts" setup>
import PreviewDialog from "@/components/ui/PreviewDialog.vue";
import type { AlbumMedia } from "@/client";
import {
  clampPanoramaFrame,
  MAX_PANORAMA_ZOOM,
  MIN_PANORAMA_ZOOM,
  MIN_PERSPECTIVE_FOV,
  panoramaCameraBounds,
  type PanoramaFrameDraft,
} from "@/panorama/frame";
import type { PanoramaViewerAdapter } from "@/panorama/view360Adapter";
import { useResizeObserver } from "@vueuse/core";
import { usePanoramaMutation } from "@/queries/usePanoramaMutation";
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";

const props = defineProps<{
  modelValue: boolean;
  albumId: string;
  media: AlbumMedia;
  aspectRatio: number;
  showSeam?: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  applied: [media: AlbumMedia];
}>();

const { t } = useI18n();
const mutation = usePanoramaMutation();
const viewerRoot = ref<HTMLElement | null>(null);
const draft = ref<PanoramaFrameDraft>({
  yaw: 0,
  pitch: 0,
  perspectiveFov: 70,
  zoom: 1,
});
const loading = ref(false);
const loadError = ref(false);
let adapter: PanoramaViewerAdapter | null = null;
let openGeneration = 0;

useResizeObserver(viewerRoot, () => adapter?.resize());

const panorama = computed(() => props.media.panorama);
const applying = computed(() => mutation.asyncStatus.value === "loading");
const projectionStyle = computed(() => ({
  "--panorama-zoom": String(draft.value.zoom),
}));
const perspectiveLabel = computed(
  () => `${Math.round(draft.value.perspectiveFov)}°`,
);
const zoomLabel = computed(() => `${draft.value.zoom.toFixed(2)}×`);

function savedFrame(): PanoramaFrameDraft {
  const config = panorama.value;
  if (!config) return { ...draft.value };
  return {
    yaw: config.yaw ?? 0,
    pitch: config.pitch ?? 0,
    perspectiveFov: config.perspective_fov ?? 70,
    zoom: config.zoom ?? 1,
  };
}

function normalizedFrame(frame: PanoramaFrameDraft): PanoramaFrameDraft {
  return clampPanoramaFrame(frame, props.media, props.aspectRatio);
}

function currentBounds(frame = draft.value) {
  return panoramaCameraBounds(frame, props.media, props.aspectRatio);
}

function panoramaSourceUrl(): string {
  return `/api/v1/albums/${encodeURIComponent(props.albumId)}/media/${encodeURIComponent(props.media.name)}/panorama-source`;
}

function cleanupAdapter(): void {
  openGeneration += 1;
  adapter?.destroy();
  adapter = null;
  loading.value = false;
}

async function loadViewer(frame: PanoramaFrameDraft): Promise<void> {
  cleanupAdapter();
  if (!props.modelValue) return;
  const generation = openGeneration;
  draft.value = { ...frame };
  loadError.value = false;
  loading.value = true;
  await nextTick();
  if (generation !== openGeneration || !viewerRoot.value) return;

  let nextAdapter: PanoramaViewerAdapter | null = null;
  try {
    const { createPanoramaViewerAdapter } =
      await import("@/panorama/view360Adapter");
    if (generation !== openGeneration || !viewerRoot.value) return;
    const createdAdapter = createPanoramaViewerAdapter(viewerRoot.value);
    nextAdapter = createdAdapter;
    adapter = createdAdapter;
    await createdAdapter.load({
      src: panoramaSourceUrl(),
      frame: draft.value,
      bounds: currentBounds(),
      onChange: (frame) => {
        draft.value = normalizedFrame(frame);
      },
    });
    if (generation !== openGeneration) {
      createdAdapter.destroy();
      return;
    }
    createdAdapter.resize();
  } catch {
    nextAdapter?.destroy();
    if (adapter === nextAdapter) adapter = null;
    if (generation === openGeneration) loadError.value = true;
  } finally {
    if (generation === openGeneration) loading.value = false;
  }
}

async function initializeViewer(): Promise<void> {
  const saved = normalizedFrame(savedFrame());
  await loadViewer(saved);
}

function setPerspective(value: number): void {
  const next = normalizedFrame({ ...draft.value, perspectiveFov: value });
  draft.value = next;
  adapter?.update(next, currentBounds(next));
}

function setZoom(value: number): void {
  const next = normalizedFrame({ ...draft.value, zoom: value });
  draft.value = next;
  adapter?.update(next, currentBounds(next));
}

function numberFromInput(event: Event): number {
  return Number((event.target as HTMLInputElement).value);
}

async function apply(): Promise<void> {
  if (applying.value) return;
  const frame = draft.value;
  const committed = await mutation.mutateAsync({
    aid: props.albumId,
    name: props.media.name,
    frame: {
      yaw: frame.yaw,
      pitch: frame.pitch,
      perspective_fov: frame.perspectiveFov,
      zoom: frame.zoom,
      aspect_ratio: props.aspectRatio,
    },
  });
  emit("applied", committed);
  emit("update:modelValue", false);
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) void initializeViewer();
    else cleanupAdapter();
  },
  { immediate: true },
);

onBeforeUnmount(cleanupAdapter);
</script>

<template>
  <PreviewDialog
    :model-value="modelValue"
    :title="t('panorama.frame.title')"
    :preview-label="t('panorama.frame.preview')"
    :aspect-ratio="aspectRatio"
    :close-label="t('common.cancel')"
    :apply-label="t('panorama.frame.apply')"
    :applying="applying"
    :apply-disabled="loading || loadError"
    persistent
    @update:model-value="(value) => emit('update:modelValue', value)"
    @apply="apply"
  >
    <div class="panorama-projection-layer" :style="projectionStyle">
      <div ref="viewerRoot" class="panorama-viewer-root" />
    </div>
    <div v-if="showSeam" class="spread-seam" aria-hidden="true" />
    <div
      v-if="loading"
      class="viewport-status"
      role="status"
      aria-live="polite"
    >
      {{ t("panorama.frame.loading") }}
    </div>
    <div
      v-else-if="loadError"
      class="viewport-status viewport-error"
      role="alert"
    >
      {{ t("panorama.frame.unsupported") }}
    </div>
    <template #controls>
      <div class="frame-controls">
        <label class="control-group">
          <span class="control-heading">
            <span>{{ t("panorama.frame.perspective") }}</span>
            <output>{{ perspectiveLabel }}</output>
          </span>
          <input
            name="perspective"
            type="range"
            :min="MIN_PERSPECTIVE_FOV"
            max="179"
            step="1"
            :value="draft.perspectiveFov"
            @input="setPerspective(numberFromInput($event))"
          />
        </label>

        <label class="control-group">
          <span class="control-heading">
            <span>{{ t("panorama.frame.zoom") }}</span>
            <output>{{ zoomLabel }}</output>
          </span>
          <input
            name="zoom"
            type="range"
            :min="MIN_PANORAMA_ZOOM"
            :max="MAX_PANORAMA_ZOOM"
            step="any"
            :value="draft.zoom"
            @input="setZoom(numberFromInput($event))"
          />
        </label>
      </div>
    </template>
  </PreviewDialog>
</template>
<style lang="scss" scoped>
.panorama-projection-layer,
.panorama-viewer-root {
  position: absolute;
  inset: 0;
}

.panorama-projection-layer {
  transform: scale(var(--panorama-zoom));
  transform-origin: center;
}

.panorama-viewer-root {
  overflow: hidden;
  touch-action: none;
}

.spread-seam {
  position: absolute;
  z-index: 2;
  inset-block: 0;
  inset-inline-start: 50%;
  width: 1px;
  background: #ffffff;
  box-shadow: 0 0 0 1px #11131a;
  pointer-events: none;
}

.viewport-status {
  position: absolute;
  z-index: 3;
  inset: 0;
  display: grid;
  place-items: center;
  padding: var(--gap-lg);
  background: #252540;
  color: #ffffff;
  text-align: center;
}

.frame-controls,
.control-group {
  display: grid;
  gap: var(--gap-md);
}

.frame-controls {
  gap: 1.25rem;
}

.control-heading {
  display: flex;
  justify-content: space-between;
  color: var(--text-bright);
  font-weight: 600;
}

.control-heading output {
  color: var(--q-primary);
}

input[type="range"] {
  width: 100%;
  accent-color: var(--q-primary);
  direction: ltr;
}

input[type="range"]:focus-visible {
  outline: 0.125rem solid var(--q-primary);
  outline-offset: 0.125rem;
}

@media (max-width: 56rem) {
  .frame-controls {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 38rem) {
  .frame-controls {
    grid-template-columns: 1fr;
  }
}
</style>
