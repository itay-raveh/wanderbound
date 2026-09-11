<script setup lang="ts">
import { computed, ref, useId, useTemplateRef, watch } from "vue";
import { useElementSize, useResizeObserver } from "@vueuse/core";
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
import PrintPreviewPage from "./PrintPreviewPage.vue";
import { daysBetween, parseLocalDate } from "@/utils/date";
import { MM_PX, PAGE_WIDTH_MM, PAGE_HEIGHT_MM } from "@/utils/pageSize";
import {
  symOutlinedArrowBack,
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
const titleId = useId();
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
const viewport = useTemplateRef("viewport");
const spread = useTemplateRef("spread");
const captions = useTemplateRef<HTMLElement[]>("captions");
const { width, height } = useElementSize(viewport);
const spreadInsets = ref({ horizontal: 0, vertical: 0 });
function measureSpreadInsets() {
  if (!spread.value) return;
  const style = getComputedStyle(spread.value);
  const captionHeight = Math.max(
    0,
    ...(captions.value ?? []).map((caption) => {
      const style = getComputedStyle(caption);
      return (
        caption.offsetHeight +
        parseFloat(style.marginBlockStart) +
        parseFloat(style.marginBlockEnd)
      );
    }),
  );
  const insets = {
    horizontal:
      parseFloat(style.paddingInlineStart) +
      parseFloat(style.paddingInlineEnd) +
      (parseFloat(style.columnGap) || 0),
    vertical:
      parseFloat(style.paddingBlockStart) +
      parseFloat(style.paddingBlockEnd) +
      captionHeight,
  };
  if (
    insets.horizontal !== spreadInsets.value.horizontal ||
    insets.vertical !== spreadInsets.value.vertical
  )
    spreadInsets.value = insets;
}
useResizeObserver(viewport, measureSpreadInsets);
useResizeObserver(() => captions.value ?? [], measureSpreadInsets);
watch(current, measureSpreadInsets, { flush: "post" });
const bleed = computed(() =>
  current.value?.covers
    ? (props.album.cover_bleed_mm ?? 0)
    : (props.album.interior_bleed_mm ?? 0),
);
const pageWidth = computed(() => (PAGE_WIDTH_MM + 2 * bleed.value) * MM_PX);
const pageHeight = computed(() => (PAGE_HEIGHT_MM + 2 * bleed.value) * MM_PX);
const scale = computed(
  () =>
    Math.max(
      0.01,
      Math.min(
        (width.value - spreadInsets.value.horizontal) / (2 * pageWidth.value),
        (height.value - spreadInsets.value.vertical) / pageHeight.value,
      ),
    ) * zoom.value,
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
  <q-dialog
    v-model="show"
    maximized
    :aria-labelledby="titleId"
    @hide="emit('close')"
    @keydown="onKeydown"
  >
    <q-card class="print-preview">
      <header class="preview-header">
        <q-btn flat no-caps autofocus @click="show = false">
          <q-icon :name="symOutlinedArrowBack" class="rtl-flip q-me-sm" />
          {{ t("print.backToEditor") }}
        </q-btn>
        <h2 :id="titleId">{{ t("print.preview") }}</h2>
        <label v-if="groups.length > 1" class="chapter-picker">
          <select v-model="chapterId" :aria-label="t('print.chapter')">
            <option
              v-for="chapterGroup in groups"
              :key="chapterGroup.chapter.id"
              :value="chapterGroup.chapter.id"
            >
              {{ chapterGroup.chapter.title }}
            </option>
          </select>
        </label>
        <span v-else class="chapter-title">{{ group?.chapter.title }}</span>
      </header>
      <div
        ref="viewport"
        class="preview-workspace"
        role="region"
        :aria-label="t('print.preview')"
        tabindex="0"
      >
        <div
          v-if="current"
          ref="spread"
          class="spread"
          :dir="current.covers ? 'ltr' : $q.lang.rtl ? 'rtl' : 'ltr'"
          :class="{ 'cover-spread': current.covers }"
        >
          <figure
            v-for="(page, side) in current.pages"
            :key="side"
            class="preview-page"
            :style="{ width: pageStyle.width, order: side }"
          >
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
            <figcaption v-if="page" ref="captions">
              {{
                current.covers
                  ? t(side === 0 ? "print.backCover" : "print.frontCover")
                  : t("print.pageNumber", { number: page.number })
              }}
            </figcaption>
          </figure>
        </div>
        <p v-else class="empty-preview">{{ t("print.emptyPreview") }}</p>
      </div>
      <footer class="preview-footer">
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
        <nav
          class="spread-navigation"
          :aria-label="t('print.spreadNavigation')"
        >
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
      </footer>
    </q-card>
  </q-dialog>
</template>

<style scoped>
.print-preview {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg);
  color: var(--text);
}
.preview-header,
.preview-footer {
  display: flex;
  align-items: center;
  gap: var(--gap-lg);
  padding: var(--gap-md-lg) 1.5rem;
  flex-shrink: 0;
  background: var(--surface);
}
.preview-header {
  border-block-end: 1px solid var(--border-color);
}
.preview-header h2 {
  margin: 0;
  font-size: var(--type-xl);
  font-weight: 700;
  line-height: 1.2;
  color: var(--text-bright);
}
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
select {
  font: inherit;
  color: var(--text-bright);
  background: var(--bg);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: var(--gap-md);
  width: 100%;
}
.preview-workspace {
  flex: 1;
  min-height: 0;
  overflow: auto;
  scrollbar-color: var(--text-muted) var(--bg);
}
.spread {
  display: flex;
  justify-content: center;
  align-items: start;
  width: fit-content;
  min-height: 100%;
  margin-inline: auto;
  padding: 1.5rem;
  box-sizing: border-box;
}
.preview-page {
  margin: auto 0;
  flex-shrink: 0;
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
.preview-footer {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  border-block-start: 1px solid var(--border-color);
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
  justify-self: end;
  color: var(--text-muted);
  font-size: var(--type-sm);
}
.empty-preview {
  text-align: center;
  padding: 3rem;
}
.print-preview :focus-visible {
  outline: 2px solid var(--primary-text) !important;
  outline-offset: -2px;
}
.print-preview .q-btn,
.chapter-picker select {
  min-width: 2.75rem;
  min-height: 2.75rem;
}
@media (max-width: 75rem) {
  .preview-note {
    display: none;
  }
}
</style>
