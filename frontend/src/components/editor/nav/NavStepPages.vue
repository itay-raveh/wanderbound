<script setup lang="ts">
import type { AlbumMedia, StepRead } from "@/client";
import {
  gridPage,
  pageSlots,
  planStepPages,
  reorderStepTilePages,
  withSlots,
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
  symOutlinedEditNote,
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
const localPages = ref(plan.value.tilePages);
watch(plan, (value) => {
  localPages.value = value.tilePages;
});
const list = ref<HTMLElement | null>(null);
const status = ref("");
const pendingTextSlotId = ref<string | null>(null);

function showPage(index: number) {
  const pageIndex = 1 + plan.value.continuationPages.length + index;
  scrollToSection(`step-${props.step.id}-page-${pageIndex}`);
}

async function movePage(from: number, to: number) {
  const pages = reorderStepTilePages(plan.value, from, to);
  if (!pages || saving.value) return;
  const key = plan.value.tilePages[from].page.id;
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

function addText(index: number) {
  const selected = plan.value.tilePages[index];
  if (!selected || saving.value) return;
  const slot = {
    id: crypto.randomUUID(),
    kind: "text" as const,
    text: "",
    frame_orientation: "landscape" as const,
  };
  const pages = [...props.step.pages];
  const target = pages[selected.originalIdx];
  if (target.kind === "grid" && pageSlots(selected.page).length < 6) {
    pages[selected.originalIdx] = withSlots(target, [
      ...pageSlots(target),
      slot,
    ]);
  } else {
    pages.splice(selected.originalIdx + 1, 0, gridPage([slot]));
  }
  pendingTextSlotId.value = slot.id;
  mutation.mutate({ sid: props.step.id, update: { pages } });
}

watch(plan, (value) => {
  const slotId = pendingTextSlotId.value;
  if (!slotId) return;
  const index = value.tilePages.findIndex(({ page }) =>
    page.slots.some((slot) => slot.id === slotId),
  );
  if (index < 0) return;
  pendingTextSlotId.value = null;
  void nextTick(() => showPage(index));
});

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
        :key="page.id"
        :data-page-key="page.id"
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
            <template v-for="slot in page.slots" :key="slot.id">
              <img
                v-if="slot.kind === 'photo' && slot.media_name"
                :src="mediaThumbUrl(slot.media_name, step.aid)"
                alt=""
                loading="lazy"
                draggable="false"
              />
              <span v-else class="text-thumb" dir="auto">{{ slot.text }}</span>
            </template>
          </span>
        </button>
        <q-btn
          flat
          round
          dense
          :icon="symOutlinedMoreVert"
          :disable="saving"
          :aria-label="t('nav.pageActions', { number: index + 1 })"
        >
          <q-menu>
            <q-list dense role="menu">
              <q-item
                v-close-popup
                clickable
                role="menuitem"
                @click="addText(index)"
              >
                <q-item-section avatar
                  ><q-icon :name="symOutlinedEditNote"
                /></q-item-section>
                <q-item-section>{{ t("nav.addText") }}</q-item-section>
              </q-item>
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
.text-thumb {
  flex: 1;
  min-width: 0;
  padding: var(--gap-xs);
  overflow: hidden;
  color: var(--text);
  font-family: var(--font-album-body);
  font-size: var(--type-xs);
  line-height: 1.2;
  text-align: start;
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
