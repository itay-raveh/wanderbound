<script lang="ts" setup>
import AlbumNav from "@/components/editor/AlbumNav.vue";
import AlbumToolbar from "@/components/editor/AlbumToolbar.vue";
import AlbumViewer from "@/components/AlbumViewer.vue";
import EditorHeader from "@/components/editor/EditorHeader.vue";
import InspectorDrawer from "@/components/editor/InspectorDrawer.vue";
import { useUserQuery } from "@/queries/useUserQuery";
import { useAlbumQuery } from "@/queries/useAlbumQuery";
import { useMediaQuery } from "@/queries/useMediaQuery";
import { useStepsQuery } from "@/queries/useStepsQuery";
import { useSegmentsQuery } from "@/queries/useSegmentsQuery";
import { useLocale } from "@/composables/useLocale";
import { useEditorKeyboard } from "@/composables/useEditorKeyboard";
import { usePhotoFocus } from "@/composables/usePhotoFocus";
import { useUndoStack } from "@/composables/useUndoStack";
import { useActiveSection } from "@/composables/useActiveSection";
import { useMeta } from "quasar";
import { useI18n } from "vue-i18n";
import { ref, computed, watch, onBeforeUnmount } from "vue";

const { t } = useI18n();

useMeta({ title: "Editor" });

const DRAWER_WIDTH = 280;
const LAST_ALBUM_KEY = "last-album-id";

let savedAlbumId: string | null = null;
try { savedAlbumId = localStorage.getItem(LAST_ALBUM_KEY); } catch {}
const selectedAlbumId = ref<string | null>(savedAlbumId);

watch(selectedAlbumId, (id) => {
  try {
    if (id) localStorage.setItem(LAST_ALBUM_KEY, id);
    else localStorage.removeItem(LAST_ALBUM_KEY);
  } catch {}
});

const { data: userData, locale } = useUserQuery();
const albumIds = computed(() => userData.value?.album_ids ?? null);
const { data: album } = useAlbumQuery(selectedAlbumId);
const { data: media } = useMediaQuery(selectedAlbumId);
const { data: steps } = useStepsQuery(selectedAlbumId);
const { data: segmentOutlines } = useSegmentsQuery(selectedAlbumId);

useLocale(locale);
useEditorKeyboard();
const undoStack = useUndoStack();
const photoFocus = usePhotoFocus();
watch(selectedAlbumId, () => { undoStack.clear(); photoFocus.blur(); resetActiveSection(); });

const { activeStepId, activeSectionKey, resetActiveSection } = useActiveSection();
onBeforeUnmount(resetActiveSection);
const activeStep = computed(() =>
  activeStepId.value != null
    ? steps.value?.find((s) => s.id === activeStepId.value)
    : undefined,
);
</script>

<template>
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
      :excluded-steps="album.excluded_steps ?? undefined"
      :colors="album.colors ?? undefined"
      :maps-ranges="album.maps_ranges ?? undefined"
    />
    <div v-else class="fit flex flex-center" role="status">
      <q-spinner-dots color="primary" size="2rem" :aria-label="t('album.loading', { name: '' })" />
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
