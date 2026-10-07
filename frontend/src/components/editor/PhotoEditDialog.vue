<script setup lang="ts">
import type { AlbumMedia, PhotoEdit } from "@/client";
import PreviewDialog from "@/components/ui/PreviewDialog.vue";
import { usePhotoEditMutation } from "@/queries/usePhotoEditMutation";
import {
  cropAspect,
  largestCrop,
  moveCrop,
  resizeCrop,
  rotateCrop,
  rotatedSize,
  zoomCrop,
  type CropCorner,
} from "@/utils/photoEdit";
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";

const props = defineProps<{
  modelValue: boolean;
  albumId: string;
  media: AlbumMedia;
}>();
const emit = defineEmits<{ "update:modelValue": [value: boolean] }>();
const { t } = useI18n();
const mutation = usePhotoEditMutation();
const imageWidth = ref(0);
const imageHeight = ref(0);
const loadError = ref(false);
const draft = ref<PhotoEdit>({ angle: 0, x: 0, y: 0, width: 1, height: 1 });
const ratioLocked = ref(false);
const canvas = ref<HTMLElement | null>(null);
const sourceUrl = computed(
  () =>
    `/api/v1/albums/${encodeURIComponent(props.albumId)}/media/${encodeURIComponent(props.media.name)}/photo-source?d=${encodeURIComponent(props.media.updated_at ?? "")}`,
);
const size = computed(() =>
  rotatedSize(imageWidth.value || 1, imageHeight.value || 1, draft.value.angle),
);
const zoom = computed(() => {
  if (!imageWidth.value) return 1;
  const max = largestCrop(
    imageWidth.value,
    imageHeight.value,
    draft.value.angle,
    cropAspect(draft.value, imageWidth.value, imageHeight.value),
  );
  return max.width / draft.value.width;
});
const zoomLabel = computed(() => `${zoom.value.toFixed(2)}×`);
const applying = computed(() => mutation.asyncStatus.value === "loading");
const imageStyle = computed(() => ({
  width: `${(imageWidth.value / size.value.width) * 100}%`,
  height: `${(imageHeight.value / size.value.height) * 100}%`,
  transform: `translate(-50%, -50%) rotate(${draft.value.angle}deg)`,
}));
const cropStyle = computed(() => ({
  left: `${draft.value.x * 100}%`,
  top: `${draft.value.y * 100}%`,
  width: `${draft.value.width * 100}%`,
  height: `${draft.value.height * 100}%`,
}));

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    imageWidth.value = 0;
    imageHeight.value = 0;
    loadError.value = false;
  },
);

function onImageLoad(event: Event) {
  const image = event.target as HTMLImageElement;
  imageWidth.value = image.naturalWidth;
  imageHeight.value = image.naturalHeight;
  draft.value = props.media.photo_edit
    ? { ...props.media.photo_edit }
    : largestCrop(
        imageWidth.value,
        imageHeight.value,
        0,
        imageWidth.value / imageHeight.value,
      );
  ratioLocked.value = false;
}

function setAngle(value: number) {
  if (
    !Number.isFinite(value) ||
    value < -180 ||
    value > 180 ||
    !imageWidth.value
  )
    return;
  draft.value = rotateCrop(
    draft.value,
    value,
    imageWidth.value,
    imageHeight.value,
    ratioLocked.value ? imageWidth.value / imageHeight.value : undefined,
  );
}

function onAngleChange(event: Event) {
  const input = event.target as HTMLInputElement;
  setAngle(Number(input.value));
  input.value = draft.value.angle.toFixed(1);
}

function setZoom(value: number) {
  if (!Number.isFinite(value) || !imageWidth.value) return;
  draft.value = zoomCrop(
    draft.value,
    value,
    imageWidth.value,
    imageHeight.value,
  );
}

function setRatioLock(locked: boolean) {
  ratioLocked.value = locked;
  if (!locked || !imageWidth.value) return;
  const target = largestCrop(
    imageWidth.value,
    imageHeight.value,
    draft.value.angle,
    imageWidth.value / imageHeight.value,
  );
  const resized = zoomCrop(
    target,
    zoom.value,
    imageWidth.value,
    imageHeight.value,
  );
  draft.value = moveCrop(
    resized,
    draft.value.x + draft.value.width / 2 - 0.5,
    draft.value.y + draft.value.height / 2 - 0.5,
    imageWidth.value,
    imageHeight.value,
  );
}

function resetDraft() {
  if (!imageWidth.value) return;
  draft.value = largestCrop(
    imageWidth.value,
    imageHeight.value,
    0,
    imageWidth.value / imageHeight.value,
  );
  ratioLocked.value = false;
}

type Drag = {
  mode: "move" | CropCorner;
  pointerX: number;
  pointerY: number;
  crop: PhotoEdit;
};
let drag: Drag | null = null;

function point(event: PointerEvent) {
  const bounds = canvas.value?.getBoundingClientRect();
  if (!bounds) return null;
  return {
    x: (event.clientX - bounds.left) / bounds.width,
    y: (event.clientY - bounds.top) / bounds.height,
  };
}

function startDrag(event: PointerEvent, mode: Drag["mode"]) {
  const at = point(event);
  if (!at || !imageWidth.value) return;
  event.stopPropagation();
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  drag = { mode, pointerX: at.x, pointerY: at.y, crop: { ...draft.value } };
}

function continueDrag(event: PointerEvent) {
  const at = point(event);
  if (!drag || !at) return;
  const { mode, crop, pointerX, pointerY } = drag;
  draft.value =
    mode === "move"
      ? moveCrop(
          crop,
          at.x - pointerX,
          at.y - pointerY,
          imageWidth.value,
          imageHeight.value,
        )
      : resizeCrop(
          crop,
          mode,
          at.x,
          at.y,
          imageWidth.value,
          imageHeight.value,
          ratioLocked.value ? imageWidth.value / imageHeight.value : undefined,
        );
}

function nudge(event: KeyboardEvent, corner?: CropCorner) {
  const step = event.shiftKey ? 0.05 : 0.01;
  const dx =
    event.key === "ArrowLeft" ? -step : event.key === "ArrowRight" ? step : 0;
  const dy =
    event.key === "ArrowUp" ? -step : event.key === "ArrowDown" ? step : 0;
  if (!dx && !dy) return;
  event.preventDefault();
  event.stopPropagation();
  if (corner) {
    const crop = draft.value;
    const x = (corner.endsWith("w") ? crop.x : crop.x + crop.width) + dx;
    const y = (corner.startsWith("n") ? crop.y : crop.y + crop.height) + dy;
    draft.value = resizeCrop(
      crop,
      corner,
      x,
      y,
      imageWidth.value,
      imageHeight.value,
      ratioLocked.value ? imageWidth.value / imageHeight.value : undefined,
    );
  } else {
    draft.value = moveCrop(
      draft.value,
      dx,
      dy,
      imageWidth.value,
      imageHeight.value,
    );
  }
}

async function apply() {
  if (applying.value || !imageWidth.value) return;
  const edit = draft.value;
  const reset =
    Math.abs(edit.angle) < 0.0001 &&
    Math.abs(edit.x) < 0.0001 &&
    Math.abs(edit.y) < 0.0001 &&
    Math.abs(edit.width - 1) < 0.0001 &&
    Math.abs(edit.height - 1) < 0.0001;
  await mutation.mutateAsync({
    aid: props.albumId,
    name: props.media.name,
    edit: reset ? null : edit,
  });
  emit("update:modelValue", false);
}
</script>

<template>
  <PreviewDialog
    :model-value="modelValue"
    :title="t('photoEdit.title')"
    :preview-label="t('photoEdit.preview')"
    :aspect-ratio="size.width / size.height"
    :close-label="t('common.cancel')"
    :apply-label="t('photoEdit.apply')"
    :applying="applying"
    :apply-disabled="!imageWidth || loadError"
    @update:model-value="(value) => emit('update:modelValue', value)"
    @apply="apply"
  >
    <div
      ref="canvas"
      class="photo-edit-canvas"
      :style="{ aspectRatio: size.width / size.height }"
    >
      <img
        :src="sourceUrl"
        :style="imageStyle"
        :alt="t('photoEdit.preview')"
        class="source-image"
        draggable="false"
        @load="onImageLoad"
        @error="loadError = true"
      />
      <div
        v-if="imageWidth"
        class="crop-box"
        :style="cropStyle"
        role="group"
        tabindex="0"
        :aria-label="t('photoEdit.moveCrop')"
        @pointerdown="startDrag($event, 'move')"
        @pointermove="continueDrag"
        @pointerup="drag = null"
        @pointercancel="drag = null"
        @keydown="nudge($event)"
      >
        <button
          v-for="corner in ['nw', 'ne', 'sw', 'se'] as const"
          :key="corner"
          type="button"
          class="crop-handle"
          :class="corner"
          :aria-label="t('photoEdit.resizeCrop')"
          @pointerdown="startDrag($event, corner)"
          @pointermove="continueDrag"
          @pointerup="drag = null"
          @pointercancel="drag = null"
          @keydown="nudge($event, corner)"
        />
      </div>
      <div v-if="loadError" class="photo-edit-status" role="alert">
        {{ t("photoEdit.loadError") }}
      </div>
    </div>
    <template #controls>
      <div class="preview-control-stack">
        <p class="scope-note">{{ t("photoEdit.scope") }}</p>
        <label class="preview-control-group">
          <span class="preview-control-heading">{{
            t("photoEdit.rotation")
          }}</span>
          <input
            class="preview-control-range"
            type="range"
            min="-180"
            max="180"
            step="0.1"
            :value="draft.angle"
            :aria-label="t('photoEdit.rotation')"
            @input="setAngle(Number(($event.target as HTMLInputElement).value))"
          />
          <span class="angle-entry">
            <input
              type="number"
              min="-180"
              max="180"
              step="0.1"
              :value="draft.angle.toFixed(1)"
              :aria-label="t('photoEdit.angleExact')"
              @change="onAngleChange"
            />
            <span aria-hidden="true">°</span>
          </span>
        </label>
        <label class="preview-control-group">
          <span class="preview-control-heading">
            <span>{{ t("photoEdit.zoom") }}</span>
            <output class="preview-control-output">{{ zoomLabel }}</output>
          </span>
          <input
            class="preview-control-range"
            type="range"
            min="1"
            max="8"
            step="0.01"
            :value="zoom"
            :aria-label="t('photoEdit.zoom')"
            @input="setZoom(Number(($event.target as HTMLInputElement).value))"
          />
          <small>{{ t("photoEdit.zoomHint") }}</small>
        </label>
        <label class="ratio-lock">
          <input
            type="checkbox"
            :checked="ratioLocked"
            @change="setRatioLock(($event.target as HTMLInputElement).checked)"
          />
          {{ t("photoEdit.ratioLock") }}
        </label>
        <button type="button" class="reset-button" @click="resetDraft">
          {{ t("photoEdit.reset") }}
        </button>
      </div>
    </template>
  </PreviewDialog>
</template>

<style scoped>
.photo-edit-canvas {
  position: relative;
  width: 100%;
  overflow: hidden;
  background: var(--bg-deep);
  touch-action: none;
}
.source-image {
  position: absolute;
  left: 50%;
  top: 50%;
  max-width: none;
  transform-origin: center;
  user-select: none;
  pointer-events: none;
}
.crop-box {
  position: absolute;
  border: 2px solid var(--text-bright);
  box-shadow: 0 0 0 100vmax color-mix(in srgb, var(--bg-deep) 58%, transparent);
  cursor: move;
  touch-action: none;
}
.crop-box::before,
.crop-box::after {
  position: absolute;
  content: "";
  pointer-events: none;
}
.crop-box::before {
  inset-inline-start: 33.333%;
  inset-block: 0;
  width: 33.333%;
  border-inline: 1px solid
    color-mix(in srgb, var(--text-bright) 55%, transparent);
}
.crop-box::after {
  inset-block-start: 33.333%;
  inset-inline: 0;
  height: 33.333%;
  border-block: 1px solid
    color-mix(in srgb, var(--text-bright) 55%, transparent);
}
.crop-handle {
  position: absolute;
  width: 1rem;
  height: 1rem;
  border: 2px solid var(--text-bright);
  background: var(--q-primary);
  cursor: nwse-resize;
  touch-action: none;
}
.crop-handle.nw {
  top: -0.5rem;
  left: -0.5rem;
}
.crop-handle.ne {
  top: -0.5rem;
  right: -0.5rem;
  cursor: nesw-resize;
}
.crop-handle.sw {
  bottom: -0.5rem;
  left: -0.5rem;
  cursor: nesw-resize;
}
.crop-handle.se {
  bottom: -0.5rem;
  right: -0.5rem;
}
.scope-note {
  margin: 0;
  color: var(--text-muted);
  font-size: var(--type-sm);
}
.angle-entry {
  display: flex;
  align-items: center;
  gap: var(--gap-xs);
}
.angle-entry input {
  width: 5rem;
  padding: var(--gap-sm);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg);
  color: var(--text-bright);
  font: inherit;
  direction: ltr;
}
.ratio-lock {
  display: flex;
  align-items: center;
  gap: var(--gap-md);
  color: var(--text);
}
.ratio-lock input {
  accent-color: var(--q-primary);
}
.reset-button {
  width: fit-content;
  padding: var(--gap-sm) 0;
  border: 0;
  background: none;
  color: var(--primary-text);
  font: inherit;
  cursor: pointer;
}
.photo-edit-status {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  padding: var(--gap-lg);
  background: var(--bg);
  color: var(--text-bright);
}
@media (max-width: 56rem) {
  .scope-note {
    grid-column: 1 / -1;
  }
}
</style>
