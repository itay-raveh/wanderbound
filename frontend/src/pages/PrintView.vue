<script lang="ts" setup>
import AlbumViewer from "@/components/AlbumViewer.vue";
import { useAlbumQuery } from "@/queries/useAlbumQuery";
import { useAlbumDataQuery } from "@/queries/useAlbumDataQuery";
import { Dark } from "quasar";
import { computed, onMounted } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const aid = computed(() => (route.params.aid as string) || null);
const darkMode = computed(() => route.query.dark === "true");

onMounted(() => Dark.set(darkMode.value));

const { data: album, error } = useAlbumQuery(aid);
const { data: albumData } = useAlbumDataQuery(aid);
</script>

<template>
  <div class="print-view">
    <div v-if="error" class="status-message error">
      Failed to load album: {{ error.message }}
    </div>
    <AlbumViewer v-else-if="album && albumData" :album="album" :data="albumData" print-mode />
    <div v-else class="status-message">Loading album...</div>
  </div>
</template>

<style lang="scss">
.print-view {
  margin: 0;
  padding: 0;
}

.status-message {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  font-size: 1.5rem;
  color: var(--text-muted);

  &.error {
    color: var(--q-negative);
  }
}

@page {
  size: A4 landscape;
  margin: 0;
}
</style>
