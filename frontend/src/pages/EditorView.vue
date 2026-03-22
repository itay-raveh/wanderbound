<script lang="ts" setup>
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
import { ref, computed, watch } from "vue";

const LAST_ALBUM_KEY = "last-album-id";
const selectedAlbumId = ref<string | null>(localStorage.getItem(LAST_ALBUM_KEY));

watch(selectedAlbumId, (id) => {
  if (id) localStorage.setItem(LAST_ALBUM_KEY, id);
  else localStorage.removeItem(LAST_ALBUM_KEY);
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

  <q-page class="editor-page">
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
