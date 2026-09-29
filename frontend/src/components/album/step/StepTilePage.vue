<script lang="ts" setup>
import AlbumPage from "@/components/album/AlbumPage.vue";
import { computed, nextTick, ref, watch } from "vue";
import { useDraggable } from "vue-draggable-plus";
import MediaItem from "../MediaItem.vue";
import PreviewDialog from "@/components/ui/PreviewDialog.vue";
import { useAlbum } from "@/composables/useAlbum";
import { usePrintMode } from "@/composables/usePrintReady";
import { isPortraitByName } from "@/utils/media";
import { useElementVisibility, useResizeObserver } from "@vueuse/core";
import {
  enforceOrientationOrder,
  photoPageFit,
  photoPageFraction,
  resolveLayoutClass,
} from "@/utils/photoLayout";
import { mediaQuality } from "@/utils/photoQuality";
import type { StepPageLayoutOutput, StepSlotLayout } from "@/client";
import { pageSlots, withSlots } from "../stepPages";
import { useI18n } from "vue-i18n";
import {
  symOutlinedClose,
  symOutlinedEditNote,
} from "@quasar/extras/material-symbols-outlined";

const { mediaByName, mediaResolutionWarningPreset } = useAlbum();
const printMode = usePrintMode();
const { t } = useI18n();

const props = defineProps<{
  page: StepPageLayoutOutput;
}>();

const emit = defineEmits<{
  "update:page": [page: StepPageLayoutOutput];
  "make-full-page": [media: string];
  "make-panorama-spread": [media: string];
}>();
const token = (slot: StepSlotLayout) =>
  slot.kind === "text" ? slot.id : slot.media_name!;
const originalSlot = (value: string) =>
  pageSlots(props.page).find((slot) => token(slot) === value);
const isPortrait = (value: string) => {
  const slot = originalSlot(value);
  return slot?.kind === "text"
    ? slot.frame_orientation === "portrait"
    : isPortraitByName(value, mediaByName.value);
};

/** Local copy for instant drag feedback. Syncs from prop on external changes. */
const localPage = ref(
  enforceOrientationOrder(pageSlots(props.page).map(token), isPortrait),
);
watch(
  () => [props.page.slots, mediaByName.value] as const,
  () => {
    const enforced = enforceOrientationOrder(
      pageSlots(props.page).map(token),
      isPortrait,
    );
    if (
      enforced.length === localPage.value.length &&
      enforced.every((v, i) => v === localPage.value[i])
    )
      return;
    localPage.value = [...enforced];
  },
);

const containerRef = ref<HTMLElement | null>(null);
const pageVisible = useElementVisibility(containerRef, {
  rootMargin: "800px",
  initialValue: printMode,
});

function syncPage() {
  localPage.value = enforceOrientationOrder(localPage.value, isPortrait);
  emit(
    "update:page",
    withSlots(
      props.page,
      localPage.value.map(
        (value) =>
          originalSlot(value) ?? {
            id: crypto.randomUUID(),
            kind: "photo",
            media_name: value,
          },
      ),
    ),
  );
}

const dialogOpen = ref(false);
const editingSlot = ref<StepSlotLayout | null>(null);
const draft = ref("");
const measureText = ref<HTMLElement | null>(null);
const editingTile = ref<HTMLElement | null>(null);
const tileSize = ref({ width: 1, height: 1 });
const overflowing = ref(false);

function openTextEditor(slot: StepSlotLayout) {
  editingSlot.value = slot;
  draft.value = slot.kind === "text" ? (slot.text ?? "") : "";
  editingTile.value = containerRef.value?.children[
    localPage.value.indexOf(token(slot))
  ] as HTMLElement | null;
  updateTileSize();
  dialogOpen.value = true;
  void document.fonts.ready.then(checkOverflow);
}

function updateTileSize() {
  if (!editingTile.value) return;
  tileSize.value = {
    width: editingTile.value.clientWidth,
    height: editingTile.value.clientHeight,
  };
}
useResizeObserver(editingTile, updateTileSize);

async function checkOverflow() {
  await nextTick();
  const element = measureText.value;
  overflowing.value =
    !!element && element.scrollHeight > element.clientHeight + 1;
}
watch([dialogOpen, draft, tileSize], () => {
  void checkOverflow();
});

function saveText() {
  const slot = editingSlot.value;
  if (!slot || !draft.value.trim() || overflowing.value) return;
  const slots = pageSlots(props.page).map((current) =>
    current.id === slot.id
      ? {
          ...current,
          kind: "text" as const,
          media_name: null,
          text: draft.value,
          frame_orientation:
            current.kind === "photo" && current.media_name
              ? isPortraitByName(current.media_name, mediaByName.value)
                ? "portrait"
                : "landscape"
              : current.frame_orientation,
        }
      : current,
  );
  emit("update:page", withSlots(props.page, slots));
  dialogOpen.value = false;
}

function removeText(slot: StepSlotLayout) {
  emit(
    "update:page",
    withSlots(
      props.page,
      pageSlots(props.page).filter((item) => item.id !== slot.id),
    ),
  );
}

if (!printMode) {
  const sortable = useDraggable(containerRef, localPage, {
    group: "photos",
    filter: ".text-item",
    animation: 0,
    immediate: false,
    onUpdate: syncPage,
    onAdd: syncPage,
  });
  let sortableActive = false;

  watch(
    pageVisible,
    (visible) => {
      if (visible && !sortableActive) {
        sortable.start();
        sortableActive = true;
      } else if (!visible && sortableActive) {
        sortable.destroy();
        sortableActive = false;
      }
    },
    { immediate: true },
  );
}

const layoutClass = computed(() =>
  resolveLayoutClass(localPage.value, isPortrait),
);
const photoFit = computed(() => photoPageFit(layoutClass.value));
const fullBleedPanorama = computed(() => {
  const media =
    localPage.value.length === 1 &&
    originalSlot(localPage.value[0])?.kind === "photo"
      ? localPage.value[0]
      : undefined;
  return media != null && mediaByName.value.get(media)?.panorama != null;
});

const photoQualities = computed(() =>
  localPage.value.map((value, i) =>
    originalSlot(value)?.kind === "text"
      ? null
      : mediaQuality(
          value,
          photoPageFraction(layoutClass.value, i),
          photoFit.value,
          mediaByName.value,
          mediaResolutionWarningPreset.value,
        ),
  ),
);
</script>

<template>
  <AlbumPage
    :number-placement="fullBleedPanorama ? 'image' : 'margin'"
    class="page"
  >
    <div
      ref="containerRef"
      :class="[
        'container',
        'page-content',
        layoutClass,
        `fit-${photoFit}`,
        { 'full-bleed-panorama': fullBleedPanorama },
      ]"
    >
      <template
        v-for="(value, i) in localPage"
        :key="originalSlot(value)?.id ?? value"
      >
        <div v-if="originalSlot(value)?.kind === 'text'" class="item text-item">
          <div class="tile-text" dir="auto">
            {{ originalSlot(value)?.text }}
          </div>
          <div v-if="!printMode" class="album-actions">
            <button
              type="button"
              class="album-action"
              :aria-label="t('textTile.edit')"
              @click="openTextEditor(originalSlot(value)!)"
            >
              <q-icon :name="symOutlinedEditNote" />
            </button>
            <button
              type="button"
              class="album-action"
              :aria-label="t('textTile.remove')"
              @click="removeText(originalSlot(value)!)"
            >
              <q-icon :name="symOutlinedClose" />
            </button>
          </div>
        </div>
        <MediaItem
          v-else
          :media="value"
          :quality="photoQualities[i]"
          :panorama-destination-kind="
            localPage.length === 1 ? 'full_page' : 'grid'
          "
          :make-full-page="localPage.length > 1"
          :make-panorama-spread="localPage.length === 1"
          class="item photo-item"
          @make-full-page="emit('make-full-page', $event)"
          @make-panorama-spread="emit('make-panorama-spread', $event)"
        >
          <template #actions>
            <button
              type="button"
              class="album-action"
              :aria-label="t('textTile.replace')"
              @click="openTextEditor(originalSlot(value)!)"
            >
              <q-icon :name="symOutlinedEditNote" />
              <q-tooltip>{{ t("textTile.replace") }}</q-tooltip>
            </button>
          </template>
        </MediaItem>
      </template>
    </div>
  </AlbumPage>
  <PreviewDialog
    v-if="!printMode"
    v-model="dialogOpen"
    :title="t('textTile.title')"
    :preview-label="t('textTile.preview')"
    :aspect-ratio="tileSize.width / tileSize.height"
    :apply-label="t('textTile.apply')"
    :apply-disabled="!draft.trim() || overflowing"
    @apply="saveText"
  >
    <div class="text-preview tile-text" dir="auto">{{ draft }}</div>
    <div
      class="item text-item text-measure"
      :style="{ width: `${tileSize.width}px`, height: `${tileSize.height}px` }"
    >
      <div ref="measureText" class="tile-text" dir="auto">{{ draft }}</div>
    </div>
    <template #controls>
      <q-input
        v-model="draft"
        type="textarea"
        dir="auto"
        autogrow
        outlined
        autofocus
        :label="t('textTile.label')"
        :maxlength="4000"
      />
      <p v-if="overflowing" role="alert">{{ t("textTile.overflow") }}</p>
    </template>
  </PreviewDialog>
</template>

<style lang="scss" scoped>
:deep(.page) {
  display: flex;
  align-items: center;
  justify-content: center;
}

.container {
  width: 100%;
  height: 100%;
  display: grid;
  gap: var(--photo-gap-lg);
  --page-content-inset-bottom: max(
    var(--photo-gap-lg),
    var(--safe-margin, 0mm)
  );
  padding-inline: var(--page-content-inset-bottom);
  padding-top: var(--page-content-inset-bottom);
  align-items: stretch;
  justify-items: stretch;
  box-sizing: border-box;
}

.item {
  display: flex;
  align-items: center;
  justify-content: center;
}

.text-item {
  position: relative;
  min-width: 0;
  min-height: 0;
  background: var(--page-bg);
  color: var(--text);
  padding: var(--page-inset-y);
  box-sizing: border-box;
}

.tile-text {
  width: 100%;
  height: 100%;
  overflow: hidden;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-family: var(--font-album-body);
  font-size: var(--type-2xl);
  line-height: 1.5;
  text-align: start;
}

.text-preview {
  padding: var(--page-inset-y);
  box-sizing: border-box;
  color: var(--text);
  background: var(--page-bg);
}

.text-measure {
  position: fixed;
  inset-block-start: -10000px;
  inset-inline-start: 0;
  visibility: hidden;
  pointer-events: none;
}

.text-item .album-actions {
  position: absolute;
  inset-block-start: var(--gap-md);
  inset-inline-end: var(--gap-md);
  display: flex;
  border: 1px solid var(--q-primary);
  background: var(--surface);
  color: var(--q-primary);
}

.text-item .album-action {
  width: 2.5rem;
  height: 2.5rem;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
}

.text-item .album-action:hover {
  background: color-mix(in srgb, var(--q-primary) 10%, transparent);
}

.text-item .album-action:focus-visible {
  outline: 0.125rem solid var(--q-primary);
  outline-offset: -0.125rem;
}

.container :deep(img) {
  object-fit: cover;
}

.container.fit-contain :deep(img) {
  object-fit: contain;
}

.container.full-bleed-panorama {
  position: absolute;
  inset: calc(-1 * var(--bleed));
  width: calc(100% + 2 * var(--bleed));
  height: calc(100% + 2 * var(--bleed));
  gap: 0;
  --page-content-inset-bottom: 0mm;
}

.container.full-bleed-panorama :deep(img) {
  object-fit: cover;
}

// -- 1 photo --

.layout-1p-0l,
.layout-0p-1l {
  grid-template-columns: 1fr;
  grid-template-rows: 1fr;
}

// -- 2 photos --

.layout-0p-2l,
.layout-1p-1l {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr;
}

.layout-2p-0l {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr;
}

// -- 3 photos: all same orientation --

.layout-3p-0l {
  grid-template-columns: 1fr 1fr 1fr;
  grid-template-rows: min-content;
  align-content: center;

  .item {
    aspect-ratio: 9 / 16;
    overflow: hidden;
  }
}

.layout-0p-3l {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;

  .item:first-child {
    grid-row: 1 / 3;
  }
}

// -- 3 photos: mixed (portraits sorted first) --

.layout-1p-2l {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;

  .item:first-child {
    grid-row: 1 / 3;
  }
}

.layout-2p-1l {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;

  .item:last-child {
    grid-column: 1 / 3;
  }
}

// -- 4 photos --

.layout-0p-4l,
.layout-2p-2l {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
}

.layout-1p-3l {
  grid-template-columns: auto auto;
  grid-template-rows: 1fr 1fr 1fr;
  justify-content: center;

  .item:first-child {
    grid-row: 1 / 4;
    aspect-ratio: 3 / 4;
    overflow: hidden;
  }

  .item:not(:first-child) {
    aspect-ratio: 16 / 9;
    overflow: hidden;
  }
}

.layout-3p-1l,
.layout-4p-0l {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
}

// -- 5 photos --

.layout-5 {
  grid-template-columns: 2fr 1fr 1fr;
  grid-template-rows: 1fr 1fr;

  .item:first-child {
    grid-row: 1 / 3;
  }
}

// -- 6 photos --

.layout-6 {
  grid-template-columns: 2fr 1fr 1fr;
  grid-template-rows: 1fr 1fr 1fr;

  .item:first-child {
    grid-row: 1 / 4;
  }
}
</style>
