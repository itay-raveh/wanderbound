<script lang="ts" setup>
import AlbumNav from "@/components/editor/AlbumNav.vue";
import AlbumToolbar from "@/components/editor/AlbumToolbar.vue";
import AlbumViewer from "@/components/AlbumViewer.vue";
import EditorHeader from "@/components/editor/EditorHeader.vue";
import InspectorDrawer from "@/components/editor/InspectorDrawer.vue";
import { useUserQuery } from "@/queries/useUserQuery";
import {
  useAlbumQuery,
  useMediaQuery,
  useStepsQuery,
  useSegmentsQuery,
} from "@/queries/queries";
import { useLocale } from "@/composables/useLocale";
import { useEditorKeyboard } from "@/composables/useEditorKeyboard";
import { usePhotoFocus } from "@/composables/usePhotoFocus";
import { useUndoStack } from "@/composables/useUndoStack";
import { useActiveSection } from "@/composables/useActiveSection";
import { useMeta } from "quasar";
import { useI18n } from "vue-i18n";
import { ref, computed, watch, nextTick, onBeforeUnmount } from "vue";

const { t } = useI18n();

useMeta({ title: "Editor" });

import { LAST_ALBUM_KEY } from "@/utils/storage-keys";
const DRAWER_WIDTH = 280;

let savedAlbumId: string | null = null;
try {
  savedAlbumId = localStorage.getItem(LAST_ALBUM_KEY);
} catch {}
const selectedAlbumId = ref<string | null>(savedAlbumId);

watch(selectedAlbumId, (id) => {
  try {
    if (id) localStorage.setItem(LAST_ALBUM_KEY, id);
    else localStorage.removeItem(LAST_ALBUM_KEY);
  } catch {}
});

const { data: userData, locale, isDemo, exitDemo } = useUserQuery();
const albumIds = computed(() => userData.value?.album_ids ?? null);

// Auto-select first album when none saved (VueUse `whenever` pattern)
if (!selectedAlbumId.value) {
  const stop = watch(
    albumIds,
    (ids) => {
      if (ids?.length) {
        selectedAlbumId.value = ids[0]!;
        void nextTick(() => stop());
      }
    },
    { immediate: true },
  );
}

const { data: album } = useAlbumQuery(selectedAlbumId);
const { data: media } = useMediaQuery(selectedAlbumId);
const { data: steps } = useStepsQuery(selectedAlbumId);
const { data: segmentOutlines } = useSegmentsQuery(selectedAlbumId);

useLocale(locale);

useEditorKeyboard();
const undoStack = useUndoStack();
const photoFocus = usePhotoFocus();
watch(selectedAlbumId, () => {
  undoStack.clear();
  photoFocus.blur();
  resetActiveSection();
});

const { activeStepId, activeSectionKey, resetActiveSection } =
  useActiveSection();
onBeforeUnmount(resetActiveSection);
const activeStep = computed(() =>
  activeStepId.value != null
    ? steps.value?.find((s) => s.id === activeStepId.value)
    : undefined,
);
</script>

<template>
  <div v-if="isDemo" class="demo-banner print-hide">
    <span>{{ t("demo.bannerText") }}</span>
    <q-btn
      :label="t('demo.bannerCta')"
      flat
      dense
      no-caps
      color="white"
      class="demo-banner-cta"
      @click="exitDemo"
    />
  </div>

  <EditorHeader class="print-hide">
    <AlbumToolbar v-if="album" :album="album" />
  </EditorHeader>

  <q-drawer
    side="left"
    :model-value="true"
    persistent
    bordered
    :width="DRAWER_WIDTH"
    :aria-label="t('nav.stepNavigation')"
    class="print-hide"
  >
    <AlbumNav
      v-if="album && steps"
      v-model:album-id="selectedAlbumId"
      :album-ids="albumIds ?? undefined"
      :steps="steps"
      :hidden-steps="album.hidden_steps ?? undefined"
      :hidden-headers="album.hidden_headers ?? undefined"
      :colors="album.colors ?? undefined"
      :maps-ranges="album.maps_ranges ?? undefined"
    />
    <div v-else class="fit flex flex-center" role="status">
      <q-spinner-dots
        color="primary"
        size="2rem"
        :aria-label="t('album.loading', { name: '' })"
      />
    </div>
  </q-drawer>

  <q-drawer
    side="right"
    :model-value="true"
    persistent
    bordered
    :width="DRAWER_WIDTH"
    :aria-label="t('nav.inspector')"
    class="print-hide"
  >
    <InspectorDrawer
      v-if="album && media"
      :key="activeStep?.id ?? activeSectionKey ?? 'empty'"
      :album="album"
      :media="media"
      :step="activeStep"
      :section-key="activeSectionKey"
    />
  </q-drawer>

  <q-page class="editor-page">
    <AlbumViewer
      v-if="album && steps && media && segmentOutlines"
      :album="album"
      :media="media"
      :steps="steps"
      :segment-outlines="segmentOutlines"
    />
  </q-page>
</template>

<style lang="scss" scoped>
.demo-banner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--gap-md);
  padding: var(--gap-sm) var(--gap-lg);
  background: var(--q-primary);
  color: white;
  font-size: var(--type-sm);
}

.demo-banner-cta {
  text-decoration: underline;
}

.editor-page {
  background: var(--bg);
}

@media print {
  @page {
    size: A4 landscape;
  }

  * {
    margin: 0;
    padding: 0;
    print-color-adjust: exact;
    -webkit-print-color-adjust: exact;
  }
}
</style>
