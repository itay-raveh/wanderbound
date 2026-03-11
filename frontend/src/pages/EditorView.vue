<script lang="ts" setup>
import ConfigSidebar from "@/components/ConfigSidebar.vue";
import AlbumViewer from "@/components/AlbumViewer.vue";
import EditorHeader from "@/components/editor/EditorHeader.vue";
import { useUserQuery } from "@/queries/useUserQuery";
import { useAlbumQuery } from "@/queries/useAlbumQuery";
import { deleteUser } from "@/client";
import { ref, computed, watch } from "vue";
import { useRouter } from "vue-router";
import { useQuasar } from "quasar";

const router = useRouter();
const $q = useQuasar();

const LAST_ALBUM_KEY = "last-album-id";
const selectedAlbumId = ref<string | null>(localStorage.getItem(LAST_ALBUM_KEY));

watch(selectedAlbumId, (id) => {
  if (id) localStorage.setItem(LAST_ALBUM_KEY, id);
  else localStorage.removeItem(LAST_ALBUM_KEY);
});

const { data: userData, user, isKm, isCelsius, error: userError } = useUserQuery();
const albumIds = computed(() => userData.value?.album_ids ?? null);
const { data: album } = useAlbumQuery(selectedAlbumId);

watch(userError, (err) => {
  if (err) void router.push("/register");
});

async function onDeleteUser() {
  try {
    await deleteUser();
    await router.push("/register");
  } catch {
    $q.notify({ type: "negative", message: "Failed to delete user." });
  }
}
</script>

<template>
  <q-page class="editor-page">
    <EditorHeader
      class="print-hide"
      :user="user"
      :is-km="isKm"
      :is-celsius="isCelsius"
      @delete="onDeleteUser"
    />

    <div class="editor-content">
      <div class="sidebar-col print-hide">
        <ConfigSidebar
          v-if="albumIds"
          v-model:album-id="selectedAlbumId"
          :album="album ?? undefined"
          :albumIds="albumIds"
        />
      </div>

      <div class="viewer-col">
        <AlbumViewer v-if="album" :album="album" />
      </div>
    </div>
  </q-page>
</template>

<style lang="scss" scoped>
.editor-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  background: var(--bg);
}

.editor-content {
  display: flex;
  flex: 1;
  gap: 0.75rem;
  padding: 0.75rem;
  min-height: 0;
}

.sidebar-col {
  flex: 1;
  min-width: 18rem;
  max-width: 30rem;
  background: var(--bg-secondary);
  border-radius: 0.75rem;
  overflow-y: auto;
}

.viewer-col {
  flex: 2;
  min-width: 0;
  background: var(--bg-secondary);
  border-radius: 0.75rem;
  overflow-y: auto;
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

  .print-hide {
    display: none !important;
  }

  .editor-content {
    padding: 0;
  }
}
</style>
