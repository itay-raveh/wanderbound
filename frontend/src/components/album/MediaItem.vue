<script lang="ts" setup>
import type { PhotoQuality } from "@/utils/photoQuality";
import { useAlbum } from "@/composables/useAlbum";
import { usePhotoFocus, STEP_ID_KEY } from "@/composables/usePhotoFocus";
import { registerQualityBadge } from "@/composables/usePhotoQuality";
import { usePrintMediaReady, usePrintMode } from "@/composables/usePrintReady";
import { PROGRAMMATIC_SCROLL_KEY } from "@/composables/useProgrammaticScroll";
import { useVideoFrameMutation } from "@/queries/useVideoFrameMutation";
import PanoramaActions from "./PanoramaActions.vue";
import { usePanoramaFrame } from "@/composables/usePanoramaFrame";
import { useElementVisibility, useResizeObserver } from "@vueuse/core";
import {
  isVideo as checkVideo,
  isPanorama,
  mediaUrl,
  mediaThumbUrl,
  posterPath,
  SIZES_FULL,
  SIZES_HALF,
  THUMB_WIDTHS,
} from "@/utils/media";
import {
  computed,
  inject,
  nextTick,
  onMounted,
  ref,
  watch,
  watchEffect,
} from "vue";
import { useI18n } from "vue-i18n";
import {
  matPlayArrow,
  matCheck,
  matChevronLeft,
  matChevronRight,
  matWarning,
} from "@quasar/extras/material-icons";

const { t } = useI18n();

const props = withDefaults(
  defineProps<{
    media: string;
    fitCover?: boolean;
    cols?: 1 | 2;
    focusable?: boolean;
    alt?: string;
    quality?: PhotoQuality | null;
    lazyRoot?: HTMLElement | null;
    lazy?: boolean;
    panoramaDestinationKind?: string;
    makeFullPage?: boolean;
    makePanoramaSpread?: boolean;
  }>(),
  { focusable: true, alt: "", lazy: true },
);

const emit = defineEmits<{
  "make-full-page": [media: string];
  "make-panorama-spread": [media: string];
}>();

const { albumId, mediaByName, placementMediaUrl } = useAlbum();
const openPanoramaDialog = usePanoramaFrame();
const printMode = usePrintMode();
const printMediaReady = usePrintMediaReady();
const supportsIntersectionObserver =
  typeof window !== "undefined" && "IntersectionObserver" in window;
const shouldLoadImmediately = computed(
  () =>
    (printMode && printMediaReady.value) ||
    (!printMode && (!props.lazy || !supportsIntersectionObserver)),
);

const programmaticScroll = inject(PROGRAMMATIC_SCROLL_KEY, ref(false));
const rootRef = ref<HTMLElement | null>(null);
const placementWidth = ref(0);
const placementHeight = ref(0);

function updatePlacementSize(): void {
  const bounds = rootRef.value?.getBoundingClientRect();
  if (!bounds || bounds.width <= 0 || bounds.height <= 0) return;
  placementWidth.value = bounds.width;
  placementHeight.value = bounds.height;
}

useResizeObserver(rootRef, updatePlacementSize);
onMounted(updatePlacementSize);
const visible = useElementVisibility(rootRef, {
  scrollTarget: computed(() => props.lazyRoot ?? null),
  rootMargin: "300px",
  once: true,
  initialValue: shouldLoadImmediately.value,
});
const loadImg = ref(shouldLoadImmediately.value);
watchEffect(() => {
  if (printMode) {
    if (printMediaReady.value) loadImg.value = true;
    return;
  }
  if (
    shouldLoadImmediately.value ||
    (visible.value && !programmaticScroll.value)
  ) {
    loadImg.value = true;
  }
});

const stepId = inject(STEP_ID_KEY, null);
const photoFocus = usePhotoFocus();
const canSelect = computed(() => props.focusable && !printMode);
const keyboardNavigable = computed(() => canSelect.value && stepId != null);
const isFocused = computed(
  () => canSelect.value && photoFocus.focusedPhotoId.value === props.media,
);

function handleClick() {
  if (!canSelect.value) return;
  photoFocus.focus(stepId, props.media);
}

function focusForReplacement() {
  handleClick();
  rootRef.value?.focus();
}

function handleEnter() {
  if (isVideo.value) togglePlay();
  else handleClick();
}

function handleSpace() {
  if (isVideo.value && (playing.value || isFocused.value)) togglePlay();
  else handleClick();
}

const isVideo = computed(() => checkVideo(props.media));

const mediaCacheKey = computed(() => {
  const m = mediaByName.value.get(props.media);
  return m?.updated_at;
});

const albumMedia = computed(() => mediaByName.value.get(props.media));
const panorama = computed(() => albumMedia.value?.panorama);
const activePanorama = computed(() => panorama.value != null);
const hasPanoramaAction = computed(
  () =>
    !printMode &&
    !isVideo.value &&
    props.panoramaDestinationKind != null &&
    isPanorama(albumMedia.value),
);
const panoramaAspectRatio = computed<number | null>(() => {
  if (
    !props.panoramaDestinationKind ||
    placementWidth.value <= 0 ||
    placementHeight.value <= 0
  )
    return null;
  return placementWidth.value / placementHeight.value;
});

function openPanoramaFrame(): void {
  updatePlacementSize();
  if (!panoramaAspectRatio.value) return;
  openPanoramaDialog?.({
    media: props.media,
    aspectRatio: panoramaAspectRatio.value,
    showSeam: props.panoramaDestinationKind === "panorama_spread",
  });
}

const src = computed(() => {
  if (activePanorama.value) return placementMediaUrl(props.media);
  const base = mediaUrl(props.media, albumId.value);
  return mediaCacheKey.value
    ? `${base}?d=${encodeURIComponent(mediaCacheKey.value)}`
    : base;
});

const imageSrc = computed(() => {
  if (activePanorama.value) return src.value;
  if (printMode) return src.value;
  return mediaThumbUrl(
    isVideo.value ? posterPath(props.media) : props.media,
    albumId.value,
    THUMB_WIDTHS.at(-1),
    mediaCacheKey.value,
  );
});

const posterCacheBust = ref<number>();
const posterSrc = computed(() => {
  if (!isVideo.value) return "";
  const base = printMode
    ? mediaUrl(posterPath(props.media), albumId.value)
    : mediaThumbUrl(
        posterPath(props.media),
        albumId.value,
        THUMB_WIDTHS.at(-1),
        mediaCacheKey.value,
      );
  const params: string[] = [];
  if (printMode && mediaCacheKey.value)
    params.push(`d=${encodeURIComponent(mediaCacheKey.value)}`);
  if (posterCacheBust.value != null) params.push(`v=${posterCacheBust.value}`);
  if (!params.length) return base;
  return `${base}${base.includes("?") ? "&" : "?"}${params.join("&")}`;
});

const imgSrcset = computed(() => {
  if (printMode || activePanorama.value) return undefined;
  const name = isVideo.value ? posterPath(props.media) : props.media;
  const base = mediaUrl(name, albumId.value);
  const extra: string[] = [];
  if (mediaCacheKey.value)
    extra.push(`d=${encodeURIComponent(mediaCacheKey.value)}`);
  if (posterCacheBust.value != null) extra.push(`v=${posterCacheBust.value}`);
  const suffix = extra.length ? `&${extra.join("&")}` : "";
  return THUMB_WIDTHS.map((w) => `${base}?w=${w}${suffix} ${w}w`).join(", ");
});
const imgSizes = computed(() => {
  if (!imgSrcset.value) return undefined;
  return (props.cols ?? 1) >= 2 ? SIZES_HALF : SIZES_FULL;
});

const playing = ref(false);
const videoRef = ref<HTMLVideoElement | null>(null);

const frameMutation = useVideoFrameMutation();

async function returnToFramePicker() {
  playing.value = false;
  await nextTick();
  rootRef.value?.focus();
}

function togglePlay() {
  if (!videoRef.value) return;
  if (playing.value) {
    videoRef.value.pause();
    void returnToFramePicker();
  } else {
    void videoRef.value.play();
    playing.value = true;
    void nextTick(() => videoRef.value?.focus());
  }
}

async function setFrame() {
  if (!videoRef.value) return;
  await frameMutation.mutateAsync({
    name: props.media,
    timestamp: videoRef.value.currentTime,
  });
  posterCacheBust.value = Date.now();
  videoRef.value.pause();
  await returnToFramePicker();
}

const FRAME_STEP = 1 / 30; // ~1 frame at 30fps

function scrub(delta: number) {
  if (!videoRef.value) return;
  videoRef.value.pause();
  videoRef.value.currentTime = Math.max(0, videoRef.value.currentTime + delta);
}

const qualityBadgeRef = ref<HTMLElement | null>(null);
watch(
  qualityBadgeRef,
  (el, _previous, onCleanup) => {
    if (!el) return;
    onCleanup(registerQualityBadge(el));
  },
  { flush: "post" },
);

function onVideoKey(e: KeyboardEvent) {
  if (e.key === "Enter") {
    e.preventDefault();
    void setFrame();
  } else if (e.key === "," || e.key === "<") {
    e.preventDefault();
    scrub(-FRAME_STEP);
  } else if (e.key === "." || e.key === ">") {
    e.preventDefault();
    scrub(FRAME_STEP);
  }
}
</script>

<template>
  <div
    ref="rootRef"
    :class="['media-item', { focused: isFocused, selectable: canSelect }]"
    class="relative-position overflow-hidden non-selectable"
    :data-media="media"
    :tabindex="keyboardNavigable ? 0 : undefined"
    :role="keyboardNavigable ? 'button' : undefined"
    :aria-label="keyboardNavigable ? alt || t('album.selectPhoto') : undefined"
    :aria-pressed="keyboardNavigable ? isFocused : undefined"
    @click="handleClick"
    @keydown.enter.self.prevent="keyboardNavigable && handleEnter()"
    @keydown.space.self.prevent="keyboardNavigable && handleSpace()"
  >
    <template v-if="isVideo && !printMode">
      <img
        v-show="!playing"
        :src="loadImg ? posterSrc : undefined"
        :srcset="loadImg ? imgSrcset : undefined"
        :sizes="imgSizes"
        :alt="alt"
        :class="['fit', fitCover ? 'fit-cover' : 'fit-contain']"
        :loading="shouldLoadImmediately ? 'eager' : 'lazy'"
        decoding="async"
      />
      <video
        v-show="playing"
        ref="videoRef"
        :src="src"
        class="fit video-playing"
        controls
        playsinline
        preload="none"
        @ended="returnToFramePicker"
        @keydown="onVideoKey"
      />
      <button
        v-if="!playing"
        class="play-overlay absolute-full cursor-pointer flex flex-center"
        :aria-label="t('album.playVideo')"
        @click.stop="togglePlay"
      >
        <div class="play-icon flex flex-center">
          <q-icon :name="matPlayArrow" />
        </div>
      </button>
      <div v-if="playing" class="frame-bar row no-wrap items-center">
        <button
          class="frame-step-btn rtl-flip flex flex-center"
          :aria-label="t('album.prevFrame')"
          @click="scrub(-FRAME_STEP)"
        >
          <q-icon :name="matChevronLeft" />
        </button>
        <button
          class="set-frame-btn row no-wrap items-center"
          @click="setFrame"
        >
          <span>{{ t("album.useAsPoster") }}</span>
          <q-icon :name="matCheck" size="1.1rem" />
        </button>
        <button
          class="frame-step-btn rtl-flip flex flex-center"
          :aria-label="t('album.nextFrame')"
          @click="scrub(FRAME_STEP)"
        >
          <q-icon :name="matChevronRight" />
        </button>
      </div>
    </template>
    <template v-else>
      <img
        :src="loadImg ? (isVideo ? posterSrc : imageSrc) : undefined"
        :srcset="loadImg ? imgSrcset : undefined"
        :sizes="imgSizes"
        :alt="alt"
        :loading="shouldLoadImmediately ? 'eager' : 'lazy'"
        :class="['fit', fitCover ? 'fit-cover' : 'fit-contain']"
        decoding="async"
      />
    </template>
    <button
      v-if="!printMode && quality && quality.tier !== 'ok'"
      ref="qualityBadgeRef"
      type="button"
      :class="['quality-badge', quality.tier, 'flex', 'flex-center']"
      :aria-label="t('externalMedia.replaceQuality')"
      @click.stop="focusForReplacement"
    >
      <q-icon :name="matWarning" />
      <q-tooltip>
        {{
          t(
            quality.tier === "warning"
              ? "quality.warningTooltip"
              : "quality.cautionTooltip",
            { dpi: quality.dpi },
          )
        }}
      </q-tooltip>
    </button>
    <PanoramaActions
      v-if="hasPanoramaAction"
      :media="media"
      :make-full-page="activePanorama && makeFullPage"
      :make-panorama-spread="activePanorama && makePanoramaSpread"
      @frame="openPanoramaFrame"
      @make-full-page="emit('make-full-page', $event)"
      @make-panorama-spread="emit('make-panorama-spread', $event)"
    />
  </div>
</template>

<style lang="scss" scoped src="./MediaItem.scss"></style>
