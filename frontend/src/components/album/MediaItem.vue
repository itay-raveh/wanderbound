<script lang="ts" setup>
import type { PhotoQuality } from "@/utils/photoQuality";
import { useAlbum } from "@/composables/useAlbum";
import { usePhotoFocus, STEP_ID_KEY } from "@/composables/usePhotoFocus";
import { usePrintMode } from "@/composables/usePrintReady";
import { useVideoFrameMutation } from "@/queries/useVideoFrameMutation";
import { isVideo as checkVideo, mediaUrl, mediaSrcset, posterPath, SIZES_FULL, SIZES_HALF, THUMB_WIDTHS } from "@/utils/media";
import { computed, inject, nextTick, ref } from "vue";
import { useI18n } from "vue-i18n";
import { matPlayArrow, matCheck, matChevronLeft, matChevronRight, matWarning } from "@quasar/extras/material-icons";

const { t } = useI18n();

const props = withDefaults(defineProps<{
  media: string;
  fitCover?: boolean;
  cols?: 1 | 2;
  focusable?: boolean;
  alt?: string;
  quality?: PhotoQuality | null;
}>(), { focusable: true, alt: "" });

const { albumId } = useAlbum();
const printMode = usePrintMode();

const stepId = inject(STEP_ID_KEY, null);
const photoFocus = usePhotoFocus();
const canFocus = computed(() => props.focusable && !printMode && stepId != null);
const isFocused = computed(() => canFocus.value && photoFocus.focusedPhotoId.value === props.media);

const elRef = ref<HTMLElement | null>(null);

function handleClick() {
  if (!canFocus.value) return;
  photoFocus.focus(stepId!, props.media);
  elRef.value?.scrollIntoView({ block: "center", behavior: "smooth" });
}

const isVideo = computed(() => checkVideo(props.media));
const src = computed(() => mediaUrl(props.media, albumId.value));
const posterCacheBust = ref<number>();
const posterSrc = computed(() => {
  if (!isVideo.value) return "";
  const base = mediaUrl(posterPath(props.media), albumId.value);
  return posterCacheBust.value != null ? `${base}?v=${posterCacheBust.value}` : base;
});

const imgSrcset = computed(() => {
  if (printMode) return undefined;
  const name = isVideo.value ? posterPath(props.media) : props.media;
  const v = posterCacheBust.value;
  if (v != null) {
    const base = mediaUrl(name, albumId.value);
    return THUMB_WIDTHS.map((w) => `${base}?w=${w}&v=${v} ${w}w`).join(", ");
  }
  return mediaSrcset(name, albumId.value);
});
const imgSizes = computed(() => {
  if (!imgSrcset.value) return undefined;
  return (props.cols ?? 1) >= 2 ? SIZES_HALF : SIZES_FULL;
});

const playing = ref(false);
const videoRef = ref<HTMLVideoElement | null>(null);

const frameMutation = useVideoFrameMutation();

function togglePlay() {
  if (!videoRef.value) return;
  if (playing.value) {
    videoRef.value.pause();
    playing.value = false;
  } else {
    void videoRef.value.play();
    playing.value = true;
    void nextTick(() => videoRef.value?.focus());
  }
}

async function setFrame() {
  if (!videoRef.value) return;
  await frameMutation.mutateAsync({ name: props.media, timestamp: videoRef.value.currentTime });
  posterCacheBust.value = Date.now();
  videoRef.value.pause();
  playing.value = false;
}

const FRAME_STEP = 1 / 30; // ~1 frame at 30fps

function scrub(delta: number) {
  if (!videoRef.value) return;
  videoRef.value.pause();
  videoRef.value.currentTime = Math.max(0, videoRef.value.currentTime + delta);
}

function onVideoKey(e: KeyboardEvent) {
  if (e.key === "Enter") { e.preventDefault(); void setFrame(); }
  else if (e.key === "," || e.key === "<") { e.preventDefault(); scrub(-FRAME_STEP); }
  else if (e.key === "." || e.key === ">") { e.preventDefault(); scrub(FRAME_STEP); }
}
</script>

<template>
  <div
    ref="elRef"
    :class="['media-item', { focused: isFocused }]"
    class="relative-position overflow-hidden non-selectable"
    :data-media="media"
    :tabindex="canFocus ? 0 : undefined"
    :role="canFocus ? 'button' : undefined"
    :aria-label="canFocus ? (alt || t('album.selectPhoto')) : undefined"
    :aria-pressed="canFocus ? isFocused : undefined"
    @click="handleClick"
    @keydown.enter="handleClick"
    @keydown.space.prevent="handleClick"
  >
    <template v-if="isVideo && !printMode">
      <img
        v-show="!playing"
        :src="posterSrc"
        :srcset="imgSrcset"
        :sizes="imgSizes"
        :alt="alt"
        :class="['fit', fitCover ? 'fit-cover' : 'fit-contain']"
        loading="eager"
        decoding="async"
      >
      <video
        v-show="playing"
        ref="videoRef"
        :src="src"
        class="fit video-playing"
        controls
        preload="none"
        @ended="playing = false"
        @keydown="onVideoKey"
      />
      <button v-if="!playing" class="play-overlay absolute-full cursor-pointer flex flex-center" :aria-label="t('album.playVideo')" @click="togglePlay">
        <div class="play-icon flex flex-center">
          <q-icon :name="matPlayArrow" />
        </div>
      </button>
      <div v-if="playing" class="frame-bar row no-wrap items-center">
        <button class="frame-step-btn rtl-flip flex flex-center" :aria-label="t('album.prevFrame')" @click="scrub(-FRAME_STEP)">
          <q-icon :name="matChevronLeft" />
        </button>
        <button class="set-frame-btn row no-wrap items-center" @click="setFrame">
          <span>{{ t("album.useAsPoster") }}</span>
          <q-icon :name="matCheck" size="1.1rem" />
        </button>
        <button class="frame-step-btn rtl-flip flex flex-center" :aria-label="t('album.nextFrame')" @click="scrub(FRAME_STEP)">
          <q-icon :name="matChevronRight" />
        </button>
      </div>
    </template>
    <template v-else>
      <img
        :src="isVideo ? posterSrc : src"
        :srcset="imgSrcset"
        :sizes="imgSizes"
        :alt="alt"
        loading="eager"
        :class="['fit', fitCover ? 'fit-cover' : 'fit-contain']"
        decoding="async"
      >
    </template>
    <div v-if="!printMode && quality && quality.tier !== 'ok'" :class="['quality-overlay', quality.tier]">
      <div class="quality-badge flex flex-center">
        <q-icon :name="matWarning" />
        <q-tooltip>{{ t(quality.tier === 'warning' ? 'quality.warningTooltip' : 'quality.cautionTooltip', { dpi: quality.dpi }) }}</q-tooltip>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.media-item {
  container-type: size;
  cursor: grab;
  background: transparent;
  width: 100%;
  height: 100%;

  &:active {
    cursor: grabbing;
  }

  &.focused {
    outline: 3px solid var(--q-primary);
    outline-offset: -3px;
  }

  &:focus-visible {
    outline: 2px solid var(--q-primary);
    outline-offset: -2px;
  }
}

.fit-cover {
  object-fit: cover;
}

.fit-contain {
  object-fit: contain;
}

.video-playing {
  object-fit: contain;
  background: black; /* letterbox — intentionally pure black, not theme-adaptive */
}

// Button reset — <button> replaces <div> for a11y but needs native chrome stripped.
// Don't use all:unset (it kills Quasar utility classes on the same element).
.play-overlay {
  background: none;
  border: none;
  padding: 0;
  font: inherit;
  color: inherit;
}

// Play button - scales with container so it looks right in both
// full-size page cells and the small unused-photos tray.

.play-icon {
  // Scale with the smaller container dimension, capped at 3.5rem
  --size: min(3.5rem, 40cqmin);
  width: var(--size);
  height: var(--size);
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.5);
  transition: background var(--duration-fast);

  :deep(.q-icon) {
    font-size: calc(var(--size) * 0.55);
    color: white;
  }

  .play-overlay:hover & {
    background: rgba(0, 0, 0, 0.7);
  }
}

// Frame selection toolbar - appears above native video controls
.frame-bar {
  position: absolute;
  bottom: 3.5rem; // clear native controls
  left: 0;
  right: 0;
  width: fit-content;
  margin: 0 auto;
  gap: var(--gap-sm);
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(10px);
  border-radius: var(--radius-full);
  padding: var(--gap-sm);
}

.frame-step-btn {
  width: 2rem;
  height: 2rem;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: rgba(255, 255, 255, 0.8);
  cursor: pointer;
  transition: background var(--duration-fast);

  :deep(.q-icon) {
    font-size: var(--type-lg);
  }

  &:hover {
    background: rgba(255, 255, 255, 0.15);
  }

  &:focus-visible {
    outline: 2px solid white;
    outline-offset: 2px;
  }
}

.set-frame-btn {
  gap: var(--gap-sm-md);
  border: none;
  border-radius: var(--radius-full);
  /* always on dark video backdrop — not theme-adaptive */
  background: white;
  color: #111;
  font-size: var(--type-sm);
  font-weight: 600;
  padding: var(--gap-sm-md) var(--gap-lg) var(--gap-sm-md) var(--gap-md-lg);
  cursor: pointer;
  transition:
    background var(--duration-fast),
    transform var(--duration-fast);

  /* always on dark backdrop — light-mode-only button */
  &:hover {
    background: color-mix(in srgb, white 85%, black);
  }

  &:active {
    transform: scale(0.96);
  }

  &:focus-visible {
    outline: 2px solid var(--q-primary);
    outline-offset: 2px;
  }
}

// Quality warning overlay — editor-only tint + badge
.quality-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 2;

  &.caution {
    background: color-mix(in srgb, var(--q-warning) 12%, transparent);
  }

  &.warning {
    background: color-mix(in srgb, var(--danger) 15%, transparent);
  }
}

.quality-badge {
  --size: min(2rem, 30cqmin);
  position: absolute;
  bottom: var(--gap-sm);
  right: var(--gap-sm);
  width: var(--size);
  height: var(--size);
  border-radius: 50%;
  pointer-events: auto;

  .caution & {
    background: color-mix(in srgb, var(--q-warning) 80%, black);
  }

  .warning & {
    background: color-mix(in srgb, var(--danger) 80%, black);
  }

  :deep(.q-icon) {
    font-size: calc(var(--size) * 0.55);
    color: white;
  }
}

@media print {
  .play-overlay,
  .frame-bar,
  .quality-overlay {
    display: none !important;
  }
}

@media (pointer: coarse) {
  .frame-step-btn {
    width: 2.75rem;
    height: 2.75rem;
  }

  .set-frame-btn {
    padding: var(--gap-md) var(--gap-lg) var(--gap-md) var(--gap-md-lg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .play-icon,
  .frame-step-btn,
  .set-frame-btn {
    transition: none;
  }
}
</style>
