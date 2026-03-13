<script lang="ts" setup>
import { useAlbumId } from "@/composables/useAlbumId";
import { usePrintMode } from "@/composables/usePrintReady";
import { useVideoFrameMutation } from "@/queries/useVideoFrameMutation";
import { isVideo as checkVideo, mediaUrl, mediaSrcset, posterPath, SIZES_FULL, SIZES_HALF } from "@/utils/media";
import { computed, nextTick, ref } from "vue";
import { matPlayArrow } from "@quasar/extras/material-icons";

const props = defineProps<{
  media: string;
  stepId: number;
  cover?: boolean;
  cols?: 1 | 2;
}>();

const albumId = useAlbumId();
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
  return mediaSrcset(isVideo.value ? posterPath(props.media) : props.media, albumId.value);
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
  <div class="media-item" data-media>
    <template v-if="isVideo && !printMode">
      <q-img
        v-show="!playing"
        :src="posterSrc"
        :srcset="imgSrcset"
        :sizes="imgSizes"
        class="fill"
        :fit="cover ? 'cover' : 'contain'"
        loading="eager"
      />
      <video
        v-show="playing"
        ref="videoRef"
        :src="src"
        class="fill video-playing"
        controls
        preload="none"
        @ended="playing = false"
        @keydown="onVideoKey"
      />
      <div v-if="!playing" class="play-overlay" @click="togglePlay">
        <q-icon :name="matPlayArrow" size="3rem" color="white" />
      </div>
      <q-btn
        v-if="playing"
        class="frame-btn"
        dense
        flat
        label="Set Frame"
        size="xs"
        text-color="white"
        @click="setFrame"
      />
    </template>
    <template v-else>
      <q-img
        :src="isVideo ? posterSrc : src"
        :srcset="imgSrcset"
        :sizes="imgSizes"
        :loading="imgLoading"
        class="fill"
        :fit="cover ? 'cover' : 'contain'"
      />
    </template>
  </div>
</template>

<style lang="scss" scoped>
.media-item {
  position: relative;
  overflow: hidden;
  user-select: none;
  cursor: grab;
  background: transparent;
  width: 100%;
  height: 100%;

  &:active {
    cursor: grabbing;
  }
}

.fill {
  width: 100%;
  height: 100%;
}

.video-playing {
  object-fit: contain;
  background: black;
}

.play-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;

  :deep(.q-icon) {
    background: rgba(0, 0, 0, 0.5);
    border-radius: 50%;
    padding: 0.5rem;
    transition: background 0.2s;
  }

  &:hover :deep(.q-icon) {
    background: rgba(0, 0, 0, 0.7);
  }
}

.frame-btn {
  position: absolute;
  bottom: 4px;
  right: 4px;
  background: rgba(0, 0, 0, 0.6);
  border-radius: 4px;
}

@media print {
  .play-overlay,
  .frame-btn {
    display: none !important;
  }
}
</style>
