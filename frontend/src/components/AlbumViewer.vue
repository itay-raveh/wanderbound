<script lang="ts" setup>
import type {
  AlbumMedia,
  AlbumMeta,
  SegmentOutline,
  StepRead as Step,
} from "@/client";
import StepEntry from "./album/StepEntry.vue";
import CoverPage from "./album/CoverPage.vue";
import AlignmentPage from "./album/AlignmentPage.vue";
import PanoramaSpreadPage from "./album/PanoramaSpreadPage.vue";
import { provideAlbum } from "@/composables/useAlbum";
import { editorZoom, setEditorZoom } from "@/composables/useEditorZoom";
import { DEFAULT_BODY_FONT, DEFAULT_FONT, fontStack } from "@/utils/fonts";
import { daysBetween, parseLocalDate } from "@/utils/date";
import { indexSteps } from "@/utils/steps";
import { PAGE_HEIGHT_MM, MM_PX } from "@/utils/pageSize";
import {
  DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET,
  summarizeQuality,
} from "@/utils/photoQuality";
import { setSafeMargin } from "@/composables/useSafeMargin";
import { setQualitySummary } from "@/composables/usePhotoQuality";
import { visibleHeaderKeys } from "./album/albumSections";
import {
  buildChapterRenderGroups,
  buildEditorItems,
  buildPhysicalRenderItems,
  type ChapterRenderGroup,
} from "./album/albumRenderPlan";
import { useAlbumViewerEditor } from "./useAlbumViewerEditor";
import {
  PANORAMA_FRAME_KEY,
  type PanoramaFrameRequest,
} from "@/composables/usePanoramaFrame";
import {
  computed,
  defineAsyncComponent,
  defineComponent,
  h,
  provide,
  ref,
  watchEffect,
} from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();

const EmptyPage = defineComponent({
  render: () => h("div", { class: "page-container" }),
});

const MapPage = defineAsyncComponent({
  loader: () => import("./album/map/MapPage.vue"),
  errorComponent: EmptyPage,
  timeout: 10_000,
});
const HikeMapPage = defineAsyncComponent({
  loader: () => import("./album/map/HikeMapPage.vue"),
  errorComponent: EmptyPage,
  timeout: 10_000,
});
const OverviewPage = defineAsyncComponent({
  loader: () => import("./album/overview/OverviewPage.vue"),
  errorComponent: EmptyPage,
  timeout: 10_000,
});
const PanoramaFrameDialog = defineAsyncComponent(() =>
  import("./editor/PanoramaFrameDialog.vue").then((module) => module.default),
);
const props = defineProps<{
  album: AlbumMeta;
  media: AlbumMedia[];
  steps: Step[];
  segmentOutlines: SegmentOutline[];
  printMode?: boolean;
}>();

const albumId = computed(() => props.album.id);
const albumColors = computed(
  () => (props.album.colors ?? {}) as Record<string, string>,
);
const albumMedia = computed(() => props.media);
const panoramaFrame = ref<PanoramaFrameRequest | null>(null);
const panoramaFrameMedia = computed(() =>
  props.media.find((media) => media.name === panoramaFrame.value?.media),
);
const panoramaFrameOpen = computed({
  get: () => panoramaFrame.value != null,
  set: (open: boolean) => {
    if (!open) panoramaFrame.value = null;
  },
});
provide(PANORAMA_FRAME_KEY, (request) => {
  panoramaFrame.value = request;
});

const safeMarginMm = computed(() => props.album.safe_margin_mm ?? 0);
watchEffect(() => setSafeMargin(safeMarginMm.value));

const albumStyle = computed(() => {
  const sm = safeMarginMm.value;
  return {
    "--font-album": fontStack(props.album.font ?? DEFAULT_FONT),
    "--font-album-body": fontStack(props.album.body_font ?? DEFAULT_BODY_FONT),
    "--safe-margin": `${sm}mm`,
    ...(sm > 0
      ? {
          "--page-inset-x": `max(3rem, ${sm}mm)`,
          "--page-inset-y": `max(2.5rem, ${sm}mm)`,
        }
      : {}),
  };
});
const visibleSteps = computed(() => {
  const hidden = new Set(props.album.hidden_steps ?? []);
  if (!hidden.size) return props.steps;
  return props.steps.filter((s) => !hidden.has(s.id));
});
const visibleStepIndex = computed(() => indexSteps(visibleSteps.value));

const tripStart = computed(() => visibleSteps.value[0]?.datetime ?? "");
const totalDays = computed(() => {
  const s = visibleSteps.value;
  if (s.length < 2) return 1;
  const first = parseLocalDate(s[0].datetime);
  const last = parseLocalDate(s[s.length - 1].datetime);
  return Math.max(1, daysBetween(first, last) + 1);
});
const mediaResolutionWarningPreset = computed(
  () =>
    props.album.media_resolution_warning_preset ??
    DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET,
);
const { mediaByName } = provideAlbum({
  albumId,
  colors: albumColors,
  media: albumMedia,
  tripStart,
  totalDays,
  mediaResolutionWarningPreset,
});

const activeHeaders = computed(() =>
  visibleHeaderKeys(props.album.hidden_headers ?? []),
);

const chapterRenderGroups = computed<ChapterRenderGroup[]>(() =>
  buildChapterRenderGroups(
    props.album,
    visibleSteps.value,
    props.segmentOutlines,
    activeHeaders.value,
  ),
);

if (!props.printMode) {
  watchEffect(() => {
    const summary = { caution: 0, warning: 0 };
    for (const group of chapterRenderGroups.value) {
      const chapterSummary = summarizeQuality(
        group.steps,
        group.chapter.front_cover_photo,
        group.chapter.back_cover_photo,
        mediaByName.value,
        mediaResolutionWarningPreset.value,
      );
      summary.caution += chapterSummary.caution;
      summary.warning += chapterSummary.warning;
    }
    setQualitySummary(summary);
  });
}

const pageH = computed(
  () => Math.round(PAGE_HEIGHT_MM * MM_PX * editorZoom.value) + 12,
);
const editorItems = computed(() =>
  buildEditorItems(chapterRenderGroups.value, mediaByName.value),
);
const physicalRenderItems = computed(() =>
  buildPhysicalRenderItems(editorItems.value),
);
const expectedPageCount = computed(() => physicalRenderItems.value.length);

function onWheel(e: WheelEvent) {
  if (!e.ctrlKey && !e.metaKey) return;
  e.preventDefault();
  const px = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
  setEditorZoom(editorZoom.value - px * 0.001);
}

const {
  setListRef,
  pageContentSuspended,
  scrollMargin,
  items,
  size,
  makeFullPage,
} = useAlbumViewerEditor({
  albumId,
  editorItems,
  pageHeight: pageH,
  visibleSteps,
  visibleStepIndex,
  printMode: Boolean(props.printMode),
});

</script>

<template>
  <!-- Print mode: everything in normal document flow for page breaks -->
  <div
    v-if="printMode && visibleSteps.length"
    class="album-container print-mode"
    :data-expected-pages="expectedPageCount"
    :style="albumStyle"
  >
    <template v-for="item in physicalRenderItems" :key="item.key">
      <CoverPage
        v-if="item.type === 'header' && item.headerKey === 'cover-front'"
        :album="album"
        :chapter="item.chapter"
        :steps="item.steps"
      />
      <CoverPage
        v-else-if="item.type === 'header' && item.headerKey === 'cover-back'"
        :album="album"
        :chapter="item.chapter"
        :steps="item.steps"
        is-back
      />
      <OverviewPage
        v-else-if="item.type === 'header' && item.headerKey === 'overview'"
        :album="album"
        :segments="item.segments"
        :steps="item.steps"
      />
      <div
        v-else-if="item.type === 'header' && item.headerKey === 'full-map'"
        class="map-wrapper"
      >
        <MapPage :segment-outlines="item.segments" :steps="item.steps" />
      </div>
      <div v-else-if="item.type === 'map'" class="map-wrapper">
        <MapPage
          :segment-outlines="item.section.segments"
          :steps="item.section.steps"
        />
      </div>
      <div v-else-if="item.type === 'hike'" class="map-wrapper">
        <HikeMapPage
          :segments="item.section.segments"
          :steps="item.section.steps"
          :hike-segment="item.section.hikeSegment"
          :all-segments="segmentOutlines"
        />
      </div>
      <StepEntry
        v-else-if="item.type === 'step-page' || item.type === 'grid'"
        :step="item.step"
        :page-index="item.pageIndex"
      />
      <AlignmentPage v-else-if="item.type === 'alignment'" />
      <PanoramaSpreadPage
        v-else-if="item.type === 'panorama-spread-left'"
        :media="item.media"
        side="left"
      />
      <PanoramaSpreadPage
        v-else-if="item.type === 'panorama-spread-right'"
        :media="item.media"
        side="right"
      />
    </template>
  </div>

  <!-- Editor mode: virtual scrolling - only visible sections are in the DOM -->
  <div
    v-else-if="visibleSteps.length"
    :class="['album-container', { 'has-safe-margin': safeMarginMm > 0 }]"
    :data-expected-pages="expectedPageCount"
    :style="[{ '--editor-zoom': String(editorZoom) }, albumStyle]"
    @wheel="onWheel"
  >
    <div
      :ref="setListRef"
      :style="{
        height: `${size}px`,
        position: 'relative',
        overflowAnchor: 'none',
      }"
    >
      <div
        :style="{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          transform: `translateY(${(items[0]?.start ?? 0) - scrollMargin}px)`,
        }"
      >
        <div
          v-for="vItem in items"
          :key="vItem.key as PropertyKey"
          :data-index="vItem.index"
          :style="{ minHeight: `${vItem.size}px` }"
        >
          <template v-if="!pageContentSuspended && editorItems[vItem.index]">
            <template
              v-for="item in [editorItems[vItem.index]!]"
              :key="item.key"
            >
            <CoverPage
              v-if="item.type === 'header' && item.headerKey === 'cover-front'"
              :album="album"
              :chapter="item.chapter"
              :steps="item.steps"
            />
            <CoverPage
              v-else-if="item.type === 'header' && item.headerKey === 'cover-back'"
              :album="album"
              :chapter="item.chapter"
              :steps="item.steps"
              is-back
            />
            <OverviewPage
              v-else-if="item.type === 'header' && item.headerKey === 'overview'"
              :album="album"
              :segments="item.segments"
              :steps="item.steps"
            />
            <div
              v-else-if="item.type === 'header' && item.headerKey === 'full-map'"
              class="map-wrapper"
            >
              <MapPage :segment-outlines="item.segments" :steps="item.steps" />
            </div>
            <div v-else-if="item.type === 'map'" class="map-wrapper">
              <MapPage
                :segment-outlines="item.section.segments"
                :steps="item.section.steps"
              />
            </div>
            <div v-else-if="item.type === 'hike'" class="map-wrapper">
              <HikeMapPage
                :segments="item.section.segments"
                :steps="item.section.steps"
                :hike-segment="item.section.hikeSegment"
                :all-segments="segmentOutlines"
              />
            </div>
            <StepEntry
              v-else-if="item.type === 'step-page' || item.type === 'grid'"
              :step="item.step"
              :page-index="item.pageIndex"
            />
            <AlignmentPage v-else-if="item.type === 'alignment'" />
            <div
              v-else-if="item.type === 'panorama-spread'"
              class="panorama-spread row no-wrap"
            >
              <PanoramaSpreadPage
                :media="item.media"
                side="left"
                @make-full-page="
                  makeFullPage(item.step, item.originalPageIndex, $event)
                "
              />
              <PanoramaSpreadPage :media="item.media" side="right" />
            </div>
            <StepEntry
              v-else-if="item.type === 'step-add-zone'"
              :step="item.step"
              add-zone-only
            />
            </template>
          </template>
        </div>
      </div>
    </div>
  </div>

  <div v-else class="fit relative-position">
    <q-inner-loading
      :label="t('album.loading', { name: album.chapters?.[0]?.title || album.id })"
      showing
    />
  </div>

  <PanoramaFrameDialog
    v-if="panoramaFrame && panoramaFrameMedia"
    v-model="panoramaFrameOpen"
    :album-id="albumId"
    :media="panoramaFrameMedia"
    :aspect-ratio="panoramaFrame.aspectRatio"
    :show-seam="panoramaFrame.showSeam"
  />
</template>

<style lang="scss" scoped src="./AlbumViewer.scss"></style>
