<script lang="ts" setup>
import type { StepRead as Step } from "@/client";
import { useDraggable } from "vue-draggable-plus";
import MediaItem from "../album/MediaItem.vue";
import { matPhotoLibrary } from "@quasar/extras/material-icons";
import { symOutlinedAddPhotoAlternate } from "@quasar/extras/material-symbols-outlined";
import { unusedUpdatePayload } from "@/composables/useStepLayout";
import {
  gridPage,
  pageSlots,
  photoSlot,
  planStepPages,
  withSlots,
} from "../album/stepPages";
import { useAlbum } from "@/composables/useAlbum";
import { useStepMutation } from "@/queries/useStepMutation";
import { useI18n } from "vue-i18n";
import { usePreferredReducedMotion } from "@vueuse/core";
import { computed, nextTick, ref, watch } from "vue";

const { t } = useI18n();

const props = defineProps<{
  step: Step;
  albumId: string;
}>();

const stepMut = useStepMutation(() => props.albumId);
const { mediaByName } = useAlbum();
const saving = computed(() => stepMut.asyncStatus.value === "loading");
const reducedMotion = usePreferredReducedMotion();
const availablePages = computed(() =>
  planStepPages(props.step, mediaByName.value).tilePages.flatMap(
    ({ page, originalIdx }, index) =>
      page.kind === "grid" &&
      pageSlots(props.step.pages[originalIdx]).length < 6
        ? [{ sourceIndex: originalIdx, number: index + 1 }]
        : [],
  ),
);

/** Local copy for instant drag feedback. Syncs from prop on external changes. */
const localUnused = ref([...props.step.unused]);
watch(
  () => props.step.unused,
  (val) => {
    if (
      val.length === localUnused.value.length &&
      val.every((v, i) => v === localUnused.value[i])
    )
      return;
    localUnused.value = [...val];
  },
);

function save() {
  stepMut.mutate({
    sid: props.step.id,
    update: unusedUpdatePayload(props.step, [...localUnused.value]),
  });
}

function placePhoto(photo: string, pageIndex: number | null) {
  if (saving.value || !props.step.unused.includes(photo)) return;
  const pages = [...props.step.pages];
  if (pageIndex === null) {
    pages.push(gridPage([photoSlot(photo)]));
  } else {
    const page = pages[pageIndex];
    if (!page || page.kind !== "grid" || pageSlots(page).length >= 6) return;
    pages[pageIndex] = withSlots(page, [...pageSlots(page), photoSlot(photo)]);
  }
  stepMut.mutate({
    sid: props.step.id,
    update: {
      pages,
      unused: props.step.unused.filter((name) => name !== photo),
    },
  });
  void nextTick(() => {
    requestAnimationFrame(() => {
      const tray = document.querySelector<HTMLElement>(".unused-drawer");
      const target =
        tray?.querySelector<HTMLElement>(".unused-place-button") ??
        tray?.querySelector<HTMLElement>(".drawer-header");
      target?.focus({ preventScroll: true });
    });
  });
}

const trackRef = ref<HTMLElement | null>(null);

useDraggable(
  trackRef,
  localUnused,
  computed(() => ({
    group: "photos",
    animation: reducedMotion.value === "reduce" ? 0 : 200,
    draggable: ".media-item",
    filter: ".unused-place-button",
    preventOnFilter: false,
    onUpdate: save,
    onAdd: save,
  })),
);
</script>

<template>
  <div class="unused-drawer" role="region" :aria-label="t('album.unused')">
    <div
      class="drawer-header row no-wrap items-center text-overline text-weight-semibold text-muted"
      tabindex="-1"
    >
      <q-icon :name="matPhotoLibrary" size="var(--type-md)" />
      <span>{{ t("album.unused") }}</span>
      <span>{{ localUnused.length }}</span>
      <q-tooltip>{{ t("album.unusedHint") }}</q-tooltip>
    </div>
    <div ref="trackRef" class="drawer-track column no-wrap">
      <MediaItem
        :show-photo-edit="false"
        v-for="photo in localUnused"
        :key="photo"
        :media="photo"
        :lazy-root="trackRef"
        :lazy="false"
      >
        <template #actions>
          <button
            type="button"
            class="album-action unused-place-button"
            :aria-label="t('album.placePhoto', { name: photo })"
            :disabled="saving"
          >
            <q-icon :name="symOutlinedAddPhotoAlternate" />
            <q-tooltip>{{ t("album.placePhoto", { name: photo }) }}</q-tooltip>
            <q-menu>
              <q-list dense role="menu">
                <q-item
                  v-for="page in availablePages"
                  :key="page.sourceIndex"
                  v-close-popup
                  clickable
                  role="menuitem"
                  @click="placePhoto(photo, page.sourceIndex)"
                >
                  <q-item-section>{{
                    t("nav.photoPage", { number: page.number })
                  }}</q-item-section>
                </q-item>
                <q-item
                  v-close-popup
                  clickable
                  role="menuitem"
                  @click="placePhoto(photo, null)"
                >
                  <q-item-section>{{ t("album.newPhotoPage") }}</q-item-section>
                </q-item>
              </q-list>
            </q-menu>
          </button>
        </template>
      </MediaItem>
      <div v-if="localUnused.length === 0" class="drawer-empty">
        {{ t("album.unusedEmpty") }}
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.unused-drawer {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  padding: var(--gap-md);
}

.drawer-header {
  gap: var(--gap-sm);
  margin-bottom: var(--gap-md);
  flex-shrink: 0;
}

.drawer-empty {
  grid-column: 1 / -1;
  min-height: 3.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--gap-md-lg) var(--gap-sm);
  border: var(--gap-xs) dashed var(--border-color);
  border-radius: var(--radius-sm);
  font-size: var(--type-xs);
  color: var(--text-muted);
  text-align: center;
  transition:
    min-height var(--duration-fast),
    border-color var(--duration-fast),
    color var(--duration-fast),
    background-color var(--duration-fast);
}

:global(body:has(.sortable-chosen)) .drawer-empty {
  min-height: 6rem;
  border-color: var(--q-primary);
  color: var(--primary-text);
  background-color: color-mix(in srgb, var(--q-primary) 8%, var(--surface));
}

.drawer-track {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--gap-sm);
  overflow-y: auto;

  // Hide video play overlay - just static thumbnails in the tray.
  :deep(.play-overlay) {
    display: none;
  }

  // Constrain SortableJS ghost clones dragged in from photo pages.
  > :deep(.media-item) {
    width: 100%;
    aspect-ratio: 4 / 3;
    border-radius: var(--radius-xs);
    overflow: hidden;
    cursor: grab;

    &:active {
      cursor: grabbing;
    }
  }
}

@media (prefers-reduced-motion: reduce) {
  .drawer-empty {
    transition: none;
  }
}
</style>
