<script lang="ts" setup>
import { updateVideoFrame } from "@/client";
import {
  clearDraggedPhoto,
  draggedPhoto,
  draggedSourceCallback,
  setDraggedPhoto,
} from "@/utils/dragState";
import { computed, ref } from "vue";

const props = defineProps<{
  media: string;
  albumName: string;
  stepId: number;
}>();

const emit = defineEmits<{
  (e: "removeSelf"): void;
  (
    e: "insertAt",
    payload: { photo: string; position: "before" | "after" },
  ): void;
}>();

const isDragOver = ref(false);
const videoRef = ref<HTMLVideoElement | null>(null);

function onDragStart(e: DragEvent) {
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = "move";
  }
  setDraggedPhoto(props.media, () => {
    emit("removeSelf");
  });
}

function onDrop(e: DragEvent) {
  isDragOver.value = false;
  if (!draggedPhoto) return;

  if (draggedPhoto === props.media) {
    clearDraggedPhoto();
    return;
  }

  const target = e.currentTarget as HTMLElement;
  const rect = target.getBoundingClientRect();
  const midX = rect.left + rect.width / 2;
  const position = e.clientX < midX ? "before" : "after";

  emit("insertAt", { photo: draggedPhoto, position });

  if (draggedSourceCallback) {
    draggedSourceCallback();
  }
  clearDraggedPhoto();
}

const isVideo = computed(() => {
  return props.media.endsWith(".mp4");
});

// poster = the frame thumbnail (photo.path), videoSrc = actual video file (photo.src)
const posterUrl = computed(
  () => `/api/v1/${props.media.replace(".mp4", ".jpg")}`,
);
const videoSrcUrl = computed(() =>
  isVideo.value ? `/api/v1/${props.media}` : "",
);
const mediaUrl = computed(() => `/api/v1/${props.media}`);

function toggleVideo() {
  const wrapper = videoRef.value?.parentElement;
  if (!wrapper || !videoRef.value) return;
  const poster = wrapper.querySelector(".video-poster") as HTMLElement;
  const overlay = wrapper.querySelector(".play-overlay") as HTMLElement;
  const video = videoRef.value;

  if (video.style.display === "none") {
    poster.style.display = "none";
    overlay.style.display = "none";
    video.style.display = "block";
    void video.play();
  } else {
    video.pause();
    video.style.display = "none";
    poster.style.display = "block";
    overlay.style.display = "flex";
  }
}

async function setFrame() {
  if (!videoRef.value || !props.stepId) return;
  const video = videoRef.value;
  const timestamp = video.currentTime;

  await updateVideoFrame({
    path: { video: video.src },
    query: { timestamp },
  });

  // Switch back to poster view
  const poster = video.previousElementSibling
    ?.previousElementSibling as HTMLElement;
  const overlay = video.previousElementSibling as HTMLElement;
  if (poster && overlay) {
    video.pause();
    video.style.display = "none";
    poster.style.display = "block";
    overlay.style.display = "flex";
  }
}
</script>

<template>
  <div
    :class="{ 'drag-over': isDragOver }"
    class="item"
    data-media
    draggable="true"
    @dragstart="onDragStart"
    @dragenter.prevent="isDragOver = true"
    @dragover.prevent="isDragOver = true"
    @dragleave.prevent="isDragOver = false"
    @drop.prevent="onDrop"
  >
    <template v-if="isVideo">
      <div class="video-wrapper">
        <q-img
          :src="posterUrl"
          class="video-poster content"
          decoding="async"
          draggable
          style="object-fit: cover"
        />
        <div class="play-overlay" @click="toggleVideo">
          <div class="play-icon">▶</div>
        </div>
        <video
          ref="videoRef"
          :src="videoSrcUrl"
          class="video-player content"
          controls
          preload="none"
          style="object-fit: cover; display: none"
        ></video>
        <button class="set-frame-btn" @click="setFrame">Set Frame</button>
      </div>
    </template>
    <template v-else>
      <q-img
        :src="mediaUrl"
        class="content"
        decoding="async"
        draggable
        style="object-fit: cover"
      />
    </template>
  </div>
</template>

<style lang="scss" scoped>
.item {
  background-color: #f0f0f0;
  transition: all 0.2s ease;
  user-select: none;
  overflow: hidden;
  position: relative;
}

.item.drag-over {
  opacity: 0.5;
  outline: 4px dashed var(--q-primary);
  outline-offset: -4px;
}

.content {
  width: 100%;
  height: 100%;
}

.video-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
}

.video-poster {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
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
}

.play-overlay:hover {
  background: rgba(0, 0, 0, 0.5);
}

.play-icon {
  color: white;
  font-size: 2rem;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
}

.video-player {
  position: absolute;
  inset: 0;
}

.set-frame-btn {
  position: absolute;
  bottom: 4px;
  right: 4px;
  padding: 2px 8px;
  font-size: 0.7rem;
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid #ccc;
  border-radius: 3px;
  cursor: pointer;
  z-index: 2;
}

.set-frame-btn:hover {
  background: white;
}

@media print {
  .play-overlay,
  .set-frame-btn,
  video {
    display: none !important;
  }
}
</style>
