<script setup lang="ts">
import { computed, ref, useTemplateRef, watch } from "vue";
import { useElementSize } from "@vueuse/core";
import { useI18n } from "vue-i18n";
import type { AlbumMeta, SegmentOutline } from "@/client";
import { providePrintMode } from "@/composables/usePrintReady";
import { provideAlbum, useAlbum } from "@/composables/useAlbum";
import { useActiveSection } from "@/composables/useActiveSection";
import {
  parseChapterHeaderSectionKey,
  sectionKey,
} from "../album/albumSections";
import {
  buildEditorItems,
  buildPhysicalRenderItems,
  type ChapterRenderGroup,
} from "../album/albumRenderPlan";
import { buildPrintSpreads } from "../album/printSpreads";
import PreviewDialog from "../ui/PreviewDialog.vue";
import PrintPreviewPage from "./PrintPreviewPage.vue";
import { daysBetween, parseLocalDate } from "@/utils/date";
import { MM_PX, PAGE_WIDTH_MM, PAGE_HEIGHT_MM } from "@/utils/pageSize";
import {
  symOutlinedChevronLeft,
  symOutlinedChevronRight,
  symOutlinedZoomIn,
  symOutlinedZoomOut,
} from "@quasar/extras/material-symbols-outlined";

const props = defineProps<{
  album: AlbumMeta;
  groups: ChapterRenderGroup[];
  segmentOutlines: SegmentOutline[];
}>();
const emit = defineEmits<{ close: [] }>();
const { t } = useI18n();
const show = ref(true);
providePrintMode(1);
const albumContext = useAlbum();
const { mediaByName } = albumContext;
const { activeStepId, activeSectionKey } = useActiveSection();
const activeChapter = parseChapterHeaderSectionKey(
  activeSectionKey.value,
)?.chapterId;
const chapterId = ref(
  props.groups.find(
    (group) =>
      group.chapter.id === activeChapter ||
      group.sections.some(
        (section) => sectionKey(section) === activeSectionKey.value,
      ) ||
      group.steps.some((step) => step.id === activeStepId.value),
  )?.chapter.id ?? props.groups[0]?.chapter.id,
);
const group = computed(
  () =>
    props.groups.find((group) => group.chapter.id === chapterId.value) ??
    props.groups[0],
);
provideAlbum({
  ...albumContext,
  tripStart: computed(() => group.value?.steps[0]?.datetime ?? ""),
  totalDays: computed(() => {
    const steps = group.value?.steps ?? [];
    if (steps.length < 2) return 1;
    return Math.max(
      1,
      daysBetween(
        parseLocalDate(steps[0].datetime),
        parseLocalDate(steps[steps.length - 1].datetime),
      ) + 1,
    );
  }),
});
const spreads = computed(() =>
  group.value
    ? buildPrintSpreads(
        buildPhysicalRenderItems(
          buildEditorItems([group.value], mediaByName.value),
        ),
      )
    : [],
);
const position = ref(0);
const current = computed(() => spreads.value[position.value]);
const zoom = ref(1);
const pageAreas = useTemplateRef<HTMLElement[]>("pageAreas");
const { width, height } = useElementSize(() => pageAreas.value?.[0]);
const bleed = computed(() =>
  current.value?.covers
    ? (props.album.cover_bleed_mm ?? 0)
    : (props.album.interior_bleed_mm ?? 0),
);
const pageWidth = computed(() => (PAGE_WIDTH_MM + 2 * bleed.value) * MM_PX);
const pageHeight = computed(() => (PAGE_HEIGHT_MM + 2 * bleed.value) * MM_PX);
const scale = computed(() =>
  Math.max(
    0.01,
    Math.min(width.value / pageWidth.value, height.value / pageHeight.value),
  ),
);
const pageStyle = computed(() => ({
  width: `${pageWidth.value * scale.value}px`,
  height: `${pageHeight.value * scale.value}px`,
}));
watch(chapterId, () => {
  position.value = 0;
  zoom.value = 1;
});
watch(spreads, (value) => {
  position.value = Math.max(0, Math.min(position.value, value.length - 1));
});
function move(delta: number) {
  position.value = Math.max(
    0,
    Math.min(spreads.value.length - 1, position.value + delta),
  );
}
function onKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") return;
  event.stopPropagation();
  if (
    (event.ctrlKey || event.metaKey) &&
    ["z", "y"].includes(event.key.toLowerCase())
  ) {
    event.preventDefault();
    return;
  }
  if (
    event.target instanceof HTMLElement &&
    ["INPUT", "SELECT", "TEXTAREA"].includes(event.target.tagName)
  )
    return;
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  const rtl = document.documentElement.dir === "rtl";
  if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
    event.preventDefault();
    move((event.key === "ArrowRight") !== rtl ? 1 : -1);
  }
}
</script>

<template>
  <PreviewDialog
    v-model="show"
    maximized
    :title="t('print.preview')"
    :preview-label="t('print.preview')"
    :close-label="t('print.backToEditor')"
    @hide="emit('close')"
    @keydown="onKeydown"
  >
    <template #header>
      <q-select
        v-if="groups.length > 1"
        v-model="chapterId"
        class="chapter-picker"
        :options="
          groups.map(({ chapter }) => ({
            label: chapter.title,
            value: chapter.id,
          }))
        "
        :aria-label="t('print.chapter')"
        outlined
        dense
        options-dense
        emit-value
        map-options
      />
      <span v-else class="chapter-title">{{ group?.chapter.title }}</span>
    </template>
    <template #workspace>
      <div
        v-if="current"
        class="spread"
        :style="{
          transform: `scale(${zoom})`,
          transformOrigin: $q.lang.rtl ? 'top right' : 'top left',
        }"
        :aria-label="t('print.preview')"
        role="region"
        tabindex="0"
        :dir="current.covers ? 'ltr' : $q.lang.rtl ? 'rtl' : 'ltr'"
        :class="{ 'cover-spread': current.covers }"
      >
        <figure
          v-for="(page, side) in current.pages"
          :key="side"
          class="preview-page"
          :style="{ gridColumn: side + 1, '--page-number': page?.number }"
        >
          <div ref="pageAreas" class="page-area">
            <div
              class="page-slot"
              :class="{ 'has-page': page }"
              :style="pageStyle"
            >
              <KeepAlive :key="chapterId" :max="2">
                <PrintPreviewPage
                  v-if="page"
                  :key="page.item.key"
                  :item="page.item"
                  :album="album"
                  :segment-outlines="segmentOutlines"
                  :width="pageWidth"
                  :height="pageHeight"
                  :scale="scale"
                />
              </KeepAlive>
            </div>
          </div>
          <figcaption v-if="page" :style="{ width: pageStyle.width }">
            {{
              current.covers
                ? t(side === 0 ? "print.backCover" : "print.frontCover")
                : t("print.pageNumber", { number: page.number })
            }}
          </figcaption>
        </figure>
      </div>
      <p v-else class="empty-preview">{{ t("print.emptyPreview") }}</p>
    </template>
    <template #actions>
      <div class="zoom-controls">
        <q-btn
          flat
          round
          dense
          :icon="symOutlinedZoomOut"
          :aria-label="t('print.zoomOut')"
          :disable="zoom <= 1"
          @click="zoom = Math.max(1, zoom - 0.5)"
        />
        <q-btn
          flat
          no-caps
          :label="
            zoom === 1 ? t('print.fitSpread') : `${Math.round(zoom * 100)}%`
          "
          :aria-label="t('print.fitSpread')"
          @click="zoom = 1"
        />
        <q-btn
          flat
          round
          dense
          :icon="symOutlinedZoomIn"
          :aria-label="t('print.zoomIn')"
          :disable="zoom >= 3"
          @click="zoom = Math.min(3, zoom + 0.5)"
        />
      </div>
      <nav class="spread-navigation" :aria-label="t('print.spreadNavigation')">
        <q-btn
          flat
          round
          :icon="symOutlinedChevronLeft"
          class="rtl-flip"
          :aria-label="t('print.previousSpread')"
          :disable="position === 0"
          @click="move(-1)"
        />
        <span role="status" aria-live="polite"
          >{{ current?.covers ? t("print.covers") : t("print.interior") }} ·
          {{
            t("print.spreadCount", {
              current: spreads.length ? position + 1 : 0,
              total: spreads.length,
            })
          }}</span
        >
        <q-btn
          flat
          round
          :icon="symOutlinedChevronRight"
          class="rtl-flip"
          :aria-label="t('print.nextSpread')"
          :disable="position >= spreads.length - 1"
          @click="move(1)"
        />
      </nav>
      <span class="preview-note">{{ t("print.previewNote") }}</span>
    </template>
  </PreviewDialog>
</template>

<style scoped>
.chapter-picker,
.chapter-title {
  margin-inline-start: auto;
  max-width: 35%;
}
.chapter-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-muted);
}
.chapter-picker {
  width: 20rem;
}
.spread {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-template-rows: minmax(0, 1fr) auto;
  width: 100%;
  flex-shrink: 0;
}
.preview-page {
  display: grid;
  grid-template-rows: subgrid;
  grid-row: 1 / 3;
  min-width: 0;
  margin: 0;
}
.page-area {
  min-height: 0;
  min-width: 0;
  display: grid;
  place-items: center;
}
.preview-page:first-child .page-area {
  justify-items: end;
}
.preview-page:last-child .page-area {
  justify-items: start;
}
.preview-page:first-child figcaption {
  justify-self: end;
}
.page-slot {
  position: relative;
}
.has-page {
  box-shadow: var(--shadow-md);
}
figcaption {
  text-align: center;
  margin-block-start: var(--gap-md-lg);
  font-size: var(--type-sm);
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}
.cover-spread {
  gap: var(--gap-lg);
}
.zoom-controls,
.spread-navigation {
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
}
.spread-navigation span {
  min-width: 10rem;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.preview-note {
  margin-inline: auto;
  color: var(--text-muted);
  font-size: var(--type-sm);
}
.empty-preview {
  text-align: center;
  padding: 3rem;
}
@media (max-width: 75rem) {
  .preview-note {
    display: none;
  }
}
</style>
