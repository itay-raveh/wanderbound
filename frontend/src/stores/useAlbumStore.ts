import { defineStore } from "pinia";
import { ref } from "vue";

export const useAlbumStore = defineStore("album", () => {
  const albumId = ref("");

  return { albumId };
});
