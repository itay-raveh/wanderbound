<script lang="ts" setup>
import { usePrintMode } from "@/composables/usePrintReady";
import { useVideoFrameMutation } from "@/queries/useVideoFrameMutation";
import { mediaUrl } from "@/utils/media";
import { computed, ref } from "vue";

const props = defineProps<{
  media: string;
  albumId: string;
  stepId: number;
}>();

const printMode = usePrintMode();
const imgLoading = computed(() => (printMode ? "eager" : "lazy"));

const isVideo = computed(() => props.media.endsWith(".mp4"));
const src = computed(() => mediaUrl(props.media));
const posterSrc = computed(() => mediaUrl(props.media.replace(".mp4", ".jpg")));

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
  }
}

function setFrame() {
  if (!videoRef.value) return;
  frameMutation.mutate({ video: videoRef.value.src, timestamp: videoRef.value.currentTime });
  videoRef.value.pause();
  playing.value = false;
}
</script>

<template>
  <div class="media-item" data-media>
    <template v-if="isVideo && !printMode">
      <q-img
        v-show="!playing"
        :src="posterSrc"
        class="fill"
        fit="cover"
        loading="eager"
      />
      <video
        v-show="playing"
        ref="videoRef"
        :src="src"
        class="fill"
        preload="none"
        @ended="playing = false"
      />
      <div v-if="!playing" class="play-overlay" @click="togglePlay">
        <q-icon name="play_arrow" size="3rem" color="white" />
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
        :loading="imgLoading"
        class="fill"
        fit="cover"
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
  background: var(--surface);

  &:active {
    cursor: grabbing;
  }
}

.fill {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.play-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  background: rgba(0, 0, 0, 0.3);
  transition: background 0.2s;

  &:hover {
    background: rgba(0, 0, 0, 0.5);
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
