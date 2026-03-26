<script lang="ts" setup>
import AlbumNav from "@/components/editor/AlbumNav.vue";
import AlbumToolbar from "@/components/editor/AlbumToolbar.vue";
import AlbumViewer from "@/components/AlbumViewer.vue";
import EditorFloatingBar from "@/components/editor/EditorFloatingBar.vue";
import EditorHeader from "@/components/editor/EditorHeader.vue";
import OnboardingBanner from "@/components/editor/OnboardingBanner.vue";
import { useUserQuery } from "@/queries/useUserQuery";
import { useAlbumQuery } from "@/queries/useAlbumQuery";
import { useAlbumDataQuery } from "@/queries/useAlbumDataQuery";
import { useLocale } from "@/composables/useLocale";
import { useEditorKeyboard } from "@/composables/useEditorKeyboard";
import { usePhotoFocus } from "@/composables/usePhotoFocus";
import { useUndoStack } from "@/composables/useUndoStack";
import { useMeta } from "quasar";
import { ref, computed, watch } from "vue";

useMeta({ title: "Editor" });

const DRAWER_WIDTH = 240;
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
const { data: albumData } = useAlbumDataQuery(selectedAlbumId);

useLocale(locale);
useEditorKeyboard();

const undoStack = useUndoStack();
const photoFocus = usePhotoFocus();
watch(selectedAlbumId, () => { undoStack.clear(); photoFocus.blur(); });
</script>

<template>
  <EditorHeader class="print-hide">
    <AlbumToolbar
      v-if="albumIds"
      v-model:album-id="selectedAlbumId"
      :album="album ?? undefined"
      :album-ids="albumIds"
      :all-steps="albumData?.steps"
    />
  </EditorHeader>

  <OnboardingBanner />

  <q-drawer
    side="left"
    :model-value="true"
    persistent
    bordered
    :width="DRAWER_WIDTH"
    class="print-hide"
  >
    <AlbumNav
      v-if="album && albumData"
      :steps="albumData.steps"
      :album-id="album.id"
      :colors="album.colors ?? undefined"
    />
    <div v-else class="fit flex flex-center">
      <q-spinner-dots color="primary" size="2rem" />
    </div>
  </q-drawer>

  <q-page class="editor-page" :style="{ '--drawer-width': DRAWER_WIDTH + 'px' }">
    <AlbumViewer v-if="album && albumData" :album="album" :data="albumData" />
    <EditorFloatingBar v-if="album" class="print-hide" />
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
