<script setup lang="ts">
import type { AlbumMedia, StepRead } from "@/client";
import {
  planStepPages,
  reorderStepPhotoPages,
} from "@/components/album/stepPages";
import { useActiveSection } from "@/composables/useActiveSection";
import { useStepMutation } from "@/queries/useStepMutation";
import { mediaThumbUrl } from "@/utils/media";
import { computed, nextTick, ref, watch } from "vue";
import { useDraggable, type DraggableEvent } from "vue-draggable-plus";
import { usePreferredReducedMotion } from "@vueuse/core";
import { useI18n } from "vue-i18n";
import {
  symOutlinedArrowDownward,
  symOutlinedArrowUpward,
  symOutlinedDragIndicator,
  symOutlinedMoreVert,
} from "@quasar/extras/material-symbols-outlined";

const props = defineProps<{ step: StepRead; media: AlbumMedia[] }>();
const { t } = useI18n();
const { scrollToSection } = useActiveSection();
const mutation = useStepMutation(() => props.step.aid);
const saving = computed(() => mutation.asyncStatus.value === "loading");
const reducedMotion = usePreferredReducedMotion();
const mediaByName = computed(
  () => new Map(props.media.map((media) => [media.name, media])),
);
const plan = computed(() => planStepPages(props.step, mediaByName.value));
const localPages = ref(plan.value.photoPages);
watch(plan, (value) => {
  localPages.value = value.photoPages;
});
const list = ref<HTMLElement | null>(null);
const status = ref("");

function pageKey(media: string[]) {
  return JSON.stringify(media);
}

function showPage(index: number) {
  const pageIndex = 1 + plan.value.continuationPages.length + index;
  scrollToSection(`step-${props.step.id}-page-${pageIndex}`);
}

async function movePage(from: number, to: number) {
  const pages = reorderStepPhotoPages(plan.value, from, to);
  if (!pages || saving.value) return;
  const key = pageKey(plan.value.photoPages[from].page.media);
  status.value = "";
  mutation.mutate({ sid: props.step.id, update: { pages } });
  await nextTick();
  const row = [
    ...(list.value?.querySelectorAll<HTMLElement>("[data-page-key]") ?? []),
  ].find((element) => element.dataset.pageKey === key);
  row
    ?.querySelector<HTMLButtonElement>(".page-preview")
    ?.focus({ preventScroll: true });
  status.value = t("nav.pageMoved", { number: to + 1 });
}

useDraggable(
  list,
  localPages,
  computed(() => ({
    handle: ".page-drag-handle",
    draggable: ".page-row",
    animation: reducedMotion.value === "reduce" ? 0 : 150,
    disabled: saving.value,
    onUpdate: (event: DraggableEvent) => {
      if (event.oldIndex != null && event.newIndex != null) {
        void movePage(event.oldIndex, event.newIndex);
      }
    },
  })),
);
</script>

<template>
  <div v-show="localPages.length" class="step-photo-pages">
    <div
      ref="list"
      role="list"
      :aria-label="t('nav.photoPages')"
      class="page-list"
    >
      <div
        v-for="({ page }, index) in localPages"
        :key="pageKey(page.media)"
        :data-page-key="pageKey(page.media)"
        class="page-row"
        role="listitem"
      >
        <span
          class="page-drag-handle"
          :class="{ disabled: saving || localPages.length < 2 }"
          aria-hidden="true"
        >
          <q-icon :name="symOutlinedDragIndicator" size="1rem" />
        </span>
        <button
          class="page-preview"
          type="button"
          :aria-label="t('nav.photoPage', { number: index + 1 })"
          @click="showPage(index)"
        >
          <span
            class="page-thumbnails"
            :class="{ panorama: page.kind === 'panorama_spread' }"
          >
            <img
              v-for="name in page.media"
              :key="name"
              :src="mediaThumbUrl(name, step.aid)"
              alt=""
              loading="lazy"
              draggable="false"
            />
          </span>
        </button>
        <q-btn
          flat
          round
          dense
          :icon="symOutlinedMoreVert"
          :disable="saving || localPages.length < 2"
          :aria-label="t('nav.reorderPage', { number: index + 1 })"
        >
          <q-menu>
            <q-list dense role="menu">
              <q-item
                v-close-popup
                clickable
                role="menuitem"
                :disable="index === 0"
                @click="movePage(index, index - 1)"
              >
                <q-item-section avatar
                  ><q-icon :name="symOutlinedArrowUpward"
                /></q-item-section>
                <q-item-section>{{ t("nav.movePageUp") }}</q-item-section>
              </q-item>
              <q-item
                v-close-popup
                clickable
                role="menuitem"
                :disable="index === localPages.length - 1"
                @click="movePage(index, index + 1)"
              >
                <q-item-section avatar
                  ><q-icon :name="symOutlinedArrowDownward"
                /></q-item-section>
                <q-item-section>{{ t("nav.movePageDown") }}</q-item-section>
              </q-item>
            </q-list>
          </q-menu>
        </q-btn>
      </div>
    </div>
    <span class="sr-only" role="status">{{ status }}</span>
  </div>
</template>

<style scoped lang="scss">
.step-photo-pages {
  padding-block: var(--gap-sm) var(--gap-md);
  padding-inline: 2rem var(--gap-md);
  background: color-mix(in srgb, var(--text) 3%, transparent);
}
.page-list {
  display: grid;
  gap: var(--gap-xs);
}
.page-row {
  display: flex;
  align-items: center;
  gap: var(--gap-xs);
  border-radius: var(--radius-xs);
}
.page-row:focus-within,
.page-row:hover {
  background: color-mix(in srgb, var(--text) 6%, transparent);
}
.page-drag-handle {
  display: flex;
  align-self: stretch;
  align-items: center;
  cursor: grab;
  color: var(--text-muted);
  touch-action: none;
}
.page-drag-handle:active {
  cursor: grabbing;
}
.page-drag-handle.disabled {
  cursor: default;
  opacity: 0.4;
}
.page-preview {
  display: flex;
  flex: 1;
  min-width: 0;
  align-items: center;
  gap: var(--gap-md);
  padding: var(--gap-xs);
  border: 0;
  border-radius: var(--radius-xs);
  background: none;
  color: var(--text);
  font: inherit;
  cursor: pointer;
}
.page-preview:focus-visible {
  outline: 0.125rem solid var(--q-primary);
  outline-offset: 0.125rem;
}
.page-thumbnails {
  display: flex;
  width: 5rem;
  height: 3.5rem;
  gap: 0.125rem;
  overflow: hidden;
  border-radius: var(--radius-xs);
  background: var(--bg-secondary);
}
.page-thumbnails img {
  min-width: 0;
  flex: 1;
  width: 0;
  object-fit: cover;
}
.page-thumbnails.panorama {
  height: 2rem;
}
.sortable-ghost {
  opacity: 0.35;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
