<script lang="ts" setup>
import AlbumPage from "@/components/album/AlbumPage.vue";
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { useDraggable } from "vue-draggable-plus";
import MediaItem from "../MediaItem.vue";
import { useAlbum } from "@/composables/useAlbum";
import { usePrintMode } from "@/composables/usePrintReady";
import { isPortraitByName } from "@/utils/media";
import { useElementVisibility } from "@vueuse/core";
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
import { symOutlinedClose } from "@quasar/extras/material-symbols-outlined";
import { matDeleteOutline } from "@quasar/extras/material-icons";
import PromptDialog from "@/components/ui/PromptDialog.vue";

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

const editingSlotId = ref<string | null>(null);
const draft = ref("");
const overflowing = ref(false);
const pendingRemovalId = ref<string | null>(null);
const showRemoveConfirm = ref(false);

function openTextEditor(slot: StepSlotLayout) {
  if (slot.kind !== "text") return;
  editingSlotId.value = slot.id;
  draft.value = slot.text ?? "";
  overflowing.value = false;
  void nextTick(() => {
    const input = containerRef.value?.querySelector<HTMLTextAreaElement>(
      `[data-text-slot="${slot.id}"]`,
    );
    if (!input) return;
    overflowing.value = input.scrollHeight > input.clientHeight + 1;
    input.focus({ preventScroll: true });
  });
}

function onTextInput(event: Event) {
  const input = event.target as HTMLTextAreaElement;
  const exceedsTile = input.scrollHeight > input.clientHeight + 1;
  if (exceedsTile && input.value.length >= draft.value.length) {
    input.value = draft.value;
    overflowing.value = true;
    return;
  }
  draft.value = input.value;
  overflowing.value = exceedsTile;
}

function cancelTextEdit() {
  editingSlotId.value = null;
  overflowing.value = false;
}

function saveText() {
  const id = editingSlotId.value;
  if (!id || overflowing.value) return;
  editingSlotId.value = null;
  const slot = pageSlots(props.page).find((current) => current.id === id);
  if (!slot) return;
  if (!draft.value.trim()) {
    if (slot.text) removeText(slot);
    return;
  }
  if (draft.value === slot.text) return;
  const slots = pageSlots(props.page).map((current) =>
    current.id === id
      ? {
          ...current,
          kind: "text" as const,
          media_name: null,
          text: draft.value,
        }
      : current,
  );
  emit("update:page", withSlots(props.page, slots));
}

onBeforeUnmount(saveText);

function removeText(slot: StepSlotLayout) {
  emit(
    "update:page",
    withSlots(
      props.page,
      pageSlots(props.page).filter((item) => item.id !== slot.id),
    ),
  );
}

function requestRemoveText(slot: StepSlotLayout) {
  pendingRemovalId.value = slot.id;
  showRemoveConfirm.value = true;
}

function confirmRemoveText() {
  showRemoveConfirm.value = false;
  const id = pendingRemovalId.value;
  pendingRemovalId.value = null;
  const slot = pageSlots(props.page).find((item) => item.id === id);
  if (slot) removeText(slot);
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
          <div v-if="printMode" class="tile-text" dir="auto">
            {{ originalSlot(value)?.text }}
          </div>
          <textarea
            v-else-if="editingSlotId === originalSlot(value)?.id"
            :data-text-slot="originalSlot(value)?.id"
            class="tile-text tile-input"
            dir="auto"
            :value="draft"
            :aria-label="t('textTile.label')"
            :maxlength="4000"
            @input="onTextInput"
            @blur="saveText"
            @keydown.esc.prevent.stop="cancelTextEdit"
            @keydown.ctrl.enter.prevent="saveText"
          />
          <div
            v-else
            class="tile-text tile-display"
            dir="auto"
            role="button"
            tabindex="0"
            :aria-label="`${t('textTile.edit')}: ${originalSlot(value)?.text || t('textTile.placeholder')}`"
            @click="openTextEditor(originalSlot(value)!)"
            @keydown.enter.prevent="openTextEditor(originalSlot(value)!)"
            @keydown.space.prevent="openTextEditor(originalSlot(value)!)"
          >
            {{ originalSlot(value)?.text || t("textTile.placeholder") }}
          </div>
          <p
            v-if="overflowing && editingSlotId === originalSlot(value)?.id"
            class="text-overflow"
            role="alert"
          >
            {{ t("textTile.overflow") }}
          </p>
          <div
            v-if="!printMode && editingSlotId !== originalSlot(value)?.id"
            class="album-actions"
          >
            <button
              type="button"
              class="album-action"
              :aria-label="t('textTile.remove')"
              @click="requestRemoveText(originalSlot(value)!)"
            >
              <q-icon :name="symOutlinedClose" />
              <q-tooltip>{{ t("textTile.remove") }}</q-tooltip>
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
        />
      </template>
    </div>
    <PromptDialog
      v-if="!printMode"
      v-model="showRemoveConfirm"
      :icon="matDeleteOutline"
      :title="t('textTile.removeConfirmTitle')"
      :body="t('textTile.removeConfirmBody')"
      :confirm-label="t('textTile.remove')"
      :cancel-label="t('common.cancel')"
      @confirm="confirmRemoveText"
    />
  </AlbumPage>
</template>

<style lang="scss" scoped>
@use "../AlbumActions.scss";

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
  font-size: var(--type-md);
  line-height: 1.5;
  text-align: start;
}

.tile-display {
  cursor: text;
}

.tile-display:focus-visible,
.tile-input:focus-visible {
  outline: 0.125rem dashed var(--q-primary);
  outline-offset: var(--gap-xs);
}

.tile-input {
  display: block;
  box-sizing: border-box;
  padding: 0;
  border: 0;
  resize: none;
  background: transparent;
  color: inherit;
  overflow: hidden;
}

.text-overflow {
  position: absolute;
  inset-block-end: var(--gap-md);
  inset-inline: var(--gap-md);
  margin: 0;
  padding: var(--gap-sm);
  background: var(--surface);
  color: var(--q-negative);
  font-size: var(--type-xs);
}

.text-item .album-actions {
  inset-inline-start: auto;
  inset-inline-end: var(--gap-md);
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
