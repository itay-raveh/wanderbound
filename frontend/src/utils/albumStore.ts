import { defineStore } from "pinia";
import type { Album } from "@/client";
import { ref } from "vue";

export const useAlbum = defineStore("album", () => {
  const album = ref<Album | null>(null);
  return { album };
});
