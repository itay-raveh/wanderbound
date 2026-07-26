<script lang="ts" setup>
import type { AlbumMedia } from "@/client";
import {
  autoFitPanoramaFrame,
  clampPanoramaFrame,
  MIN_PANORAMA_ZOOM,
  MIN_PERSPECTIVE_FOV,
  panoramaCameraBounds,
  type PanoramaFrameDraft,
} from "@/panorama/frame";
import type { PanoramaViewerAdapter } from "@/panorama/view360Adapter";
import { useResizeObserver } from "@vueuse/core";
import {
  useDisablePanoramaMutation,
  usePanoramaMutation,
} from "@/queries/usePanoramaMutation";
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
const disableMutation = useDisablePanoramaMutation();
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
const disabling = computed(
  () => disableMutation.asyncStatus.value === "loading",
);
const viewportStyle = computed(() => ({
  aspectRatio: String(props.aspectRatio),
}));
const projectionStyle = computed(() => ({
  "--panorama-zoom": String(draft.value.zoom),
}));
const maximumZoom = computed(() =>
  Math.min(props.media.width, props.media.height),
);
const perspectiveLabel = computed(
  () => `${Math.round(draft.value.perspectiveFov)}°`,
);
const zoomLabel = computed(() => `${draft.value.zoom.toFixed(1)}×`);

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
  return clampPanoramaFrame(
    frame,
    props.media,
    props.aspectRatio,
    maximumZoom.value,
  );
}

function currentBounds(frame = draft.value) {
  return panoramaCameraBounds(
    frame,
    props.media,
    props.aspectRatio,
  );
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

function resetFrame(): void {
  draft.value = autoFitPanoramaFrame(
    draft.value,
    props.media,
    props.aspectRatio,
  );
  adapter?.update(draft.value, currentBounds());
}

function cancel(): void {
  emit("update:modelValue", false);
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

async function disablePanorama(): Promise<void> {
  if (disabling.value) return;
  const committed = await disableMutation.mutateAsync({
    aid: props.albumId,
    name: props.media.name,
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
  <q-dialog
    :model-value="modelValue"
    aria-labelledby="panorama-frame-title"
    aria-describedby="panorama-frame-description"
    persistent
    @update:model-value="(value) => emit('update:modelValue', value)"
  >
    <q-card class="panorama-dialog">
      <q-card-section class="panorama-header">
        <div>
          <h2 id="panorama-frame-title" class="panorama-title">
            {{ t("panorama.frame.title") }}
          </h2>
          <p id="panorama-frame-description" class="panorama-subtitle">
            {{ t("panorama.frame.body") }}
          </p>
        </div>
        <div class="frame-readout" aria-live="polite">
          <span
            >{{ t("panorama.frame.perspective") }} {{ perspectiveLabel }}</span
          >
          <span>{{ t("panorama.frame.zoom") }} {{ zoomLabel }}</span>
        </div>
      </q-card-section>

      <q-card-section class="panorama-workspace">
        <div class="preview-column">
          <div
            class="panorama-viewport"
            :style="viewportStyle"
            :aria-label="t('panorama.frame.preview')"
            role="region"
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
          </div>
          <p class="interaction-hint">{{ t("panorama.frame.hint") }}</p>
        </div>

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
            <span class="control-help">{{
              t("panorama.frame.perspectiveHelp")
            }}</span>
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
              :max="maximumZoom"
              step="0.1"
              :value="draft.zoom"
              @input="setZoom(numberFromInput($event))"
            />
            <span class="control-help">{{ t("panorama.frame.zoomHelp") }}</span>
          </label>
        </div>
      </q-card-section>

      <q-card-actions class="panorama-actions" align="right">
        <q-btn
          v-if="panorama"
          class="disable-button"
          flat
          no-caps
          color="negative"
          :disable="applying || disabling"
          :loading="disabling"
          :label="t('panorama.frame.disable')"
          @click="disablePanorama"
        />
        <q-btn
          class="reset-button"
          flat
          no-caps
          :label="t('panorama.frame.reset')"
          @click="resetFrame"
        />
        <q-btn
          class="cancel-button"
          flat
          no-caps
          :disable="applying || disabling"
          :label="t('common.cancel')"
          @click="cancel"
        />
        <q-btn
          class="apply-button"
          color="primary"
          no-caps
          :disable="loading || loadError || applying || disabling"
          :loading="applying"
          :label="t('panorama.frame.apply')"
          @click="apply"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>
<style lang="scss" scoped>
.panorama-dialog {
  width: min(76rem, 96vw);
  max-width: none;
  max-height: 94vh;
  overflow: auto;
}

.panorama-header,
.panorama-actions {
  padding: 1.25rem 1.5rem;
}

.panorama-header {
  display: flex;
  justify-content: space-between;
  gap: var(--gap-lg);
}

.panorama-title {
  margin: 0;
  color: var(--text-bright);
  font-size: 1.375rem;
  font-weight: 700;
}

.panorama-subtitle,
.interaction-hint {
  margin: var(--gap-sm) 0 0;
  color: var(--text-muted);
}

.frame-readout {
  display: flex;
  gap: var(--gap-md);
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.panorama-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 18rem;
  gap: 1.25rem;
  align-items: start;
  padding: 0 1.5rem 1.25rem;
}

.preview-column {
  min-width: 0;
}

.panorama-viewport {
  position: relative;
  width: 100%;
  overflow: hidden;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: #11131a;
  touch-action: none;
}

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

.control-help {
  color: var(--text-muted);
  font-size: var(--type-xs);
}

.panorama-actions {
  gap: var(--gap-sm);
  border-block-start: 1px solid var(--border-color);
}

@media (max-width: 56rem) {
  .panorama-header,
  .panorama-workspace {
    grid-template-columns: 1fr;
  }

  .panorama-header {
    display: grid;
  }

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
