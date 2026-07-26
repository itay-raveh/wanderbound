<script lang="ts" setup>
import type { AlbumMedia, PanoramaDestination } from "@/client";
import {
  autoFitPanoramaFrame,
  clampPanoramaFrame,
  MAX_CAPTURED_FOV,
  MIN_CAPTURED_FOV,
  MIN_PANORAMA_ZOOM,
  MIN_PERSPECTIVE_FOV,
  panoramaCameraBounds,
  type PanoramaFrameDraft,
  type PanoramaSourceGeometry,
} from "@/panorama/frame";
import type { PanoramaViewerAdapter } from "@/panorama/view360Adapter";
import { usePanoramaMutation } from "@/queries/usePanoramaMutation";
import {
  computed,
  nextTick,
  onBeforeUnmount,
  ref,
  watch,
} from "vue";
import { useI18n } from "vue-i18n";

const props = defineProps<{
  modelValue: boolean;
  albumId: string;
  media: AlbumMedia;
  destination: PanoramaDestination;
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
const savedOnOpen = ref<PanoramaFrameDraft>({ ...draft.value });
const loading = ref(false);
const applying = ref(false);
const loadError = ref(false);
let adapter: PanoramaViewerAdapter | null = null;
let resizeObserver: ResizeObserver | null = null;
let openGeneration = 0;
let pinchStartDistance = 0;
let pinchStartZoom = 1;
let pinchOwned = false;

const panorama = computed(() => props.media.panorama);
const isSpread = computed(
  () => props.destination.kind === "panorama_spread",
);
const hasCapturedWidthControl = computed(
  () => panorama.value?.detection !== "gpano",
);
const viewportStyle = computed(() => ({
  aspectRatio: String(props.destination.aspect_ratio),
}));
const projectionStyle = computed(() => ({
  "--panorama-zoom": String(draft.value.zoom),
}));
const maximumZoom = computed(() =>
  Math.min(props.destination.width_px, props.destination.height_px),
);
const perspectiveLabel = computed(
  () => `${Math.round(draft.value.perspectiveFov)}°`,
);
const zoomLabel = computed(() => `${draft.value.zoom.toFixed(1)}×`);
const capturedWidthLabel = computed(
  () => `${Math.round(effectiveCapturedFov(draft.value))}°`,
);

function sourceGeometry(): PanoramaSourceGeometry {
  const config = panorama.value;
  if (!config) {
    return {
      sourceWidth: props.media.width,
      sourceHeight: props.media.height,
      capturedFov: 180,
    };
  }
  return {
    sourceWidth: config.source_width,
    sourceHeight: config.source_height,
    capturedFov: config.captured_fov,
    croppedAreaWidth: config.cropped_area_width,
    croppedAreaHeight: config.cropped_area_height,
    croppedAreaTop: config.cropped_area_top,
  };
}

function effectiveCapturedFov(frame: PanoramaFrameDraft): number {
  return frame.capturedFov ?? sourceGeometry().capturedFov;
}

function savedFrame(): PanoramaFrameDraft {
  const config = panorama.value;
  if (!config) return { ...draft.value };
  return {
    yaw: config.yaw ?? 0,
    pitch: config.pitch ?? 0,
    perspectiveFov: config.perspective_fov ?? 70,
    zoom: config.zoom ?? 1,
    ...(config.detection === "gpano"
      ? {}
      : { capturedFov: Math.round(config.captured_fov) }),
  };
}

function normalizedFrame(frame: PanoramaFrameDraft): PanoramaFrameDraft {
  return clampPanoramaFrame(
    frame,
    sourceGeometry(),
    props.destination.aspect_ratio,
    maximumZoom.value,
  );
}

function currentBounds(frame = draft.value) {
  return panoramaCameraBounds(
    frame,
    sourceGeometry(),
    props.destination.aspect_ratio,
  );
}

function panoramaSourceUrl(frame: PanoramaFrameDraft): string {
  const base = `/api/v1/albums/${encodeURIComponent(props.albumId)}/media/${encodeURIComponent(props.media.name)}/panorama-source`;
  if (panorama.value?.detection === "gpano") return base;
  return `${base}?captured_fov=${encodeURIComponent(Math.round(effectiveCapturedFov(frame)))}`;
}

function cleanupAdapter(): void {
  openGeneration += 1;
  resizeObserver?.disconnect();
  resizeObserver = null;
  adapter?.destroy();
  adapter = null;
  loading.value = false;
  pinchOwned = false;
  pinchStartDistance = 0;
}

async function loadViewer(frame: PanoramaFrameDraft): Promise<void> {
  cleanupAdapter();
  if (!props.modelValue || !panorama.value) return;
  const generation = openGeneration;
  draft.value = { ...frame };
  loadError.value = false;
  loading.value = true;
  await nextTick();
  if (generation !== openGeneration || !viewerRoot.value) return;

  let nextAdapter: PanoramaViewerAdapter | null = null;
  try {
    const { createPanoramaViewerAdapter } = await import(
      "@/panorama/view360Adapter"
    );
    if (generation !== openGeneration || !viewerRoot.value) return;
    const createdAdapter = createPanoramaViewerAdapter(viewerRoot.value);
    nextAdapter = createdAdapter;
    adapter = createdAdapter;
    await createdAdapter.load({
      src: panoramaSourceUrl(frame),
      frame: draft.value,
      bounds: currentBounds(),
      accessibleLabel: t("panorama.frame.preview"),
      onChange: (frame) => {
        draft.value = normalizedFrame(frame);
      },
    });
    if (generation !== openGeneration) {
      createdAdapter.destroy();
      return;
    }
    createdAdapter.resize();
    if (typeof ResizeObserver !== "undefined") {
      resizeObserver = new ResizeObserver(() => createdAdapter.resize());
      resizeObserver.observe(viewerRoot.value);
    }
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
  savedOnOpen.value = saved;
  await loadViewer(saved);
}

function setPerspective(value: number): void {
  const next = normalizedFrame({ ...draft.value, perspectiveFov: value });
  draft.value = next;
  adapter?.setPerspective(next.perspectiveFov, currentBounds(next));
}

function setZoom(value: number): void {
  const next = normalizedFrame({ ...draft.value, zoom: value });
  draft.value = next;
  adapter?.lookAt(next, currentBounds(next));
}

function setCapturedWidth(value: number): void {
  const next = normalizedFrame({ ...draft.value, capturedFov: value });
  void loadViewer(next);
}

function numberFromInput(event: Event): number {
  return Number((event.target as HTMLInputElement).value);
}

function resetFrame(): void {
  draft.value = autoFitPanoramaFrame(
    draft.value,
    sourceGeometry(),
    props.destination.aspect_ratio,
  );
  adapter?.reset(draft.value, currentBounds());
}

function cancel(): void {
  draft.value = { ...savedOnOpen.value };
  emit("update:modelValue", false);
}

async function apply(): Promise<void> {
  if (applying.value) return;
  applying.value = true;
  const frame = draft.value;
  try {
    const committed = await mutation.mutateAsync({
      aid: props.albumId,
      name: props.media.name,
      frame: {
        yaw: frame.yaw,
        pitch: frame.pitch,
        perspective_fov: frame.perspectiveFov,
        zoom: frame.zoom,
        ...(frame.capturedFov == null
          ? {}
          : { captured_fov: frame.capturedFov }),
      },
      destination: props.destination,
    });
    emit("applied", committed);
    emit("update:modelValue", false);
  } finally {
    applying.value = false;
  }
}

function onWheel(event: WheelEvent): void {
  event.preventDefault();
  const step = event.deltaY < 0 ? 0.1 : -0.1;
  setZoom(Math.round((draft.value.zoom + step) * 100) / 100);
}

function touchDistance(touches: TouchList): number {
  const first = touches[0];
  const second = touches[1];
  if (!first || !second) return 0;
  return Math.hypot(
    second.clientX - first.clientX,
    second.clientY - first.clientY,
  );
}

function onTouchStart(event: TouchEvent): void {
  if (!pinchOwned && event.touches.length < 2) return;
  event.preventDefault();
  event.stopPropagation();
  if (pinchOwned) return;
  pinchOwned = true;
  adapter?.cancelInteraction();
  pinchStartDistance = touchDistance(event.touches);
  pinchStartZoom = draft.value.zoom;
}

function onTouchMove(event: TouchEvent): void {
  if (!pinchOwned) return;
  event.preventDefault();
  event.stopPropagation();
  if (event.touches.length < 2 || pinchStartDistance <= 0) return;
  setZoom(pinchStartZoom * (touchDistance(event.touches) / pinchStartDistance));
}

function onTouchEnd(event: TouchEvent): void {
  if (!pinchOwned) return;
  event.preventDefault();
  event.stopPropagation();
  if (event.touches.length > 0) return;
  pinchOwned = false;
  pinchStartDistance = 0;
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
    @hide="cleanupAdapter"
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
          <span>{{ t("panorama.frame.perspective") }} {{ perspectiveLabel }}</span>
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
            @wheel="onWheel"
            @touchstart.capture="onTouchStart"
            @touchmove.capture="onTouchMove"
            @touchend.capture="onTouchEnd"
            @touchcancel.capture="onTouchEnd"
          >
            <div class="panorama-projection-layer" :style="projectionStyle">
              <div ref="viewerRoot" class="panorama-viewer-root" />
            </div>
            <div v-if="isSpread" class="spread-seam" aria-hidden="true" />
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
            <span class="control-help">{{ t("panorama.frame.perspectiveHelp") }}</span>
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

          <details v-if="hasCapturedWidthControl" class="advanced-controls">
            <summary>{{ t("panorama.frame.advanced") }}</summary>
            <label class="control-group captured-control">
              <span class="control-heading">
                <span>{{ t("panorama.frame.capturedWidth") }}</span>
                <output>{{ capturedWidthLabel }}</output>
              </span>
              <input
                name="captured-width"
                type="range"
                :min="MIN_CAPTURED_FOV"
                :max="MAX_CAPTURED_FOV"
                step="1"
                :value="effectiveCapturedFov(draft)"
                @input="setCapturedWidth(numberFromInput($event))"
              />
              <span class="control-help">{{ t("panorama.frame.capturedWidthHelp") }}</span>
            </label>
          </details>
        </div>
      </q-card-section>

      <q-card-actions class="panorama-actions" align="right">
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
          :disable="applying"
          :label="t('common.cancel')"
          @click="cancel"
        />
        <q-btn
          class="apply-button"
          color="primary"
          no-caps
          :disable="loading || loadError || applying"
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

.panorama-header {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: var(--gap-lg);
  padding: 1.25rem 1.5rem var(--gap-md-lg);
}

.panorama-title {
  margin: 0;
  color: var(--text-bright);
  font-size: 1.375rem;
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: -0.02em;
}

.panorama-subtitle,
.interaction-hint {
  margin: var(--gap-sm) 0 0;
  color: var(--text-muted);
}

.panorama-subtitle {
  max-width: 42rem;
  line-height: 1.5;
}

.frame-readout {
  display: flex;
  flex-wrap: wrap;
  justify-content: end;
  gap: var(--gap-sm);
  color: var(--text-muted);
  font-size: var(--type-sm);
  font-variant-numeric: tabular-nums;
}

.frame-readout span {
  padding: var(--gap-sm) var(--gap-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--surface);
}

.panorama-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 18rem;
  gap: 1.25rem;
  align-items: start;
  padding: var(--gap-md-lg) 1.5rem 1.25rem;
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
  color: #e5e7eb;
  text-align: center;
}

.viewport-error {
  color: #ffffff;
}

.interaction-hint {
  font-size: var(--type-sm);
}

.frame-controls {
  display: grid;
  gap: 1.25rem;
}

.control-group {
  display: grid;
  gap: var(--gap-md);
}

.control-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--gap-md);
  color: var(--text-bright);
  font-size: var(--type-sm);
  font-weight: 600;
}

.control-heading output {
  color: var(--q-primary);
  font-variant-numeric: tabular-nums;
}

input[type="range"] {
  width: 100%;
  accent-color: var(--q-primary);
  direction: ltr;
}

input[type="range"]:focus-visible,
.advanced-controls summary:focus-visible {
  outline: 0.125rem solid var(--q-primary);
  outline-offset: 0.125rem;
}

.control-help {
  color: var(--text-muted);
  font-size: var(--type-xs);
  line-height: 1.45;
}

.advanced-controls {
  padding-block-start: var(--gap-md-lg);
  border-block-start: 1px solid var(--border-color);
}

.advanced-controls summary {
  color: var(--text-muted);
  cursor: pointer;
  font-size: var(--type-sm);
  font-weight: 600;
}

.captured-control {
  margin-block-start: var(--gap-md-lg);
}

.panorama-actions {
  gap: var(--gap-sm);
  padding: var(--gap-md-lg) 1.5rem 1.25rem;
  border-block-start: 1px solid var(--border-color);
}

@media (max-width: 56rem) {
  .panorama-header {
    display: grid;
  }

  .frame-readout {
    justify-content: start;
  }

  .panorama-workspace {
    grid-template-columns: 1fr;
  }

  .frame-controls {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .advanced-controls {
    grid-column: 1 / -1;
  }
}

@media (max-width: 38rem) {
  .panorama-header,
  .panorama-workspace,
  .panorama-actions {
    padding-inline: 1.25rem;
  }

  .frame-controls {
    grid-template-columns: 1fr;
  }

  .advanced-controls {
    grid-column: auto;
  }
}

@media (prefers-reduced-motion: reduce) {
  .panorama-projection-layer {
    transition: none;
  }
}
</style>
