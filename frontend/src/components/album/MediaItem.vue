<script lang="ts" setup>
import { useAlbum } from "@/composables/useAlbum";
import { usePrintMode } from "@/composables/usePrintReady";
import { useVideoFrameMutation } from "@/queries/useVideoFrameMutation";
import { isVideo as checkVideo, mediaUrl, mediaSrcset, posterPath, SIZES_FULL, SIZES_HALF, THUMB_WIDTHS } from "@/utils/media";
import { computed, nextTick, ref } from "vue";
import { useI18n } from "vue-i18n";
import { matPlayArrow, matCheck, matChevronLeft, matChevronRight } from "@quasar/extras/material-icons";

const { t } = useI18n();

const props = defineProps<{
  media: string;
  cover?: boolean;
  cols?: 1 | 2;
}>();

const { albumId } = useAlbum();
const printMode = usePrintMode();
const imgLoading = computed(() => (printMode ? "eager" : "lazy"));

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
  // After a frame change, bust the srcset URLs too so the browser
  // doesn't serve stale cached thumbnails.
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
  <div class="media-item relative-position overflow-hidden non-selectable" data-media>
    <template v-if="isVideo && !printMode">
      <img
        v-show="!playing"
        :src="posterSrc"
        :srcset="imgSrcset"
        :sizes="imgSizes"
        :class="['fit', cover ? 'fit-cover' : 'fit-contain']"
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
      <div v-if="!playing" class="play-overlay absolute-full cursor-pointer flex flex-center" @click="togglePlay">
        <div class="play-icon flex flex-center">
          <q-icon :name="matPlayArrow" />
        </div>
      </div>
      <div v-if="playing" class="frame-bar row no-wrap items-center">
        <button class="frame-step-btn rtl-flip flex flex-center" :title="t('album.prevFrame')" @click="scrub(-FRAME_STEP)">
          <q-icon :name="matChevronLeft" />
        </button>
        <button class="set-frame-btn row no-wrap items-center" @click="setFrame">
          <span>{{ t("album.useAsPoster") }}</span>
          <q-icon :name="matCheck" size="1.1rem" />
        </button>
        <button class="frame-step-btn rtl-flip flex flex-center" :title="t('album.nextFrame')" @click="scrub(FRAME_STEP)">
          <q-icon :name="matChevronRight" />
        </button>
      </div>
    </template>
    <template v-else>
      <img
        :src="isVideo ? posterSrc : src"
        :srcset="imgSrcset"
        :sizes="imgSizes"
        :loading="imgLoading"
        :class="['fit', cover ? 'fit-cover' : 'fit-contain']"
        decoding="async"
      >
    </template>
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
}

.fit-cover {
  object-fit: cover;
}

.fit-contain {
  object-fit: contain;
}

.video-playing {
  object-fit: contain;
  background: black;
}

// Play button — scales with container so it looks right in both
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

// Frame selection toolbar — appears above native video controls
.frame-bar {
  position: absolute;
  bottom: 3.5rem; // clear native controls
  left: 0;
  right: 0;
  width: fit-content;
  margin: 0 auto;
  gap: var(--gap-sm);
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(8px);
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
}

.set-frame-btn {
  gap: var(--gap-sm-md);
  border: none;
  border-radius: var(--radius-full);
  background: white;
  color: #111;
  font-size: var(--type-sm);
  font-weight: 600;
  padding: var(--gap-sm-md) 0.9rem var(--gap-sm-md) 0.6rem;
  cursor: pointer;
  transition:
    background var(--duration-fast),
    transform 0.1s;

  &:hover {
    background: #e0e0e0;
  }

  &:active {
    transform: scale(0.96);
  }
}

@media print {
  .play-overlay,
  .frame-bar {
    display: none !important;
  }
}
</style>
