<script setup lang="ts">
import type { AlbumChapter, AlbumMeta, StepRead } from "@/client";
import AlbumPage from "./AlbumPage.vue";
import CoverArtwork from "./CoverArtwork.vue";
import { computed } from "vue";
const props = defineProps<{
  album: AlbumMeta;
  chapter: AlbumChapter;
  steps: StepRead[];
}>();
const spine = computed(() => props.chapter.spine_width_mm ?? 0);
</script>

<template>
  <AlbumPage
    cover
    :width-mm="594 + spine"
    class="wraparound"
    :style="{ '--spine': `${spine}mm` }"
  >
    <CoverArtwork
      class="wrap-back"
      :album="album"
      :chapter="chapter"
      :steps="steps"
      is-back
    />
    <CoverArtwork
      class="wrap-front"
      :album="album"
      :chapter="chapter"
      :steps="steps"
    />
    <div class="spine-guide" aria-hidden="true" />
    <div class="cover-safe-guide back-safe" aria-hidden="true" />
    <div class="cover-safe-guide front-safe" aria-hidden="true" />
  </AlbumPage>
</template>

<style scoped>
.wrap-back,
.wrap-front {
  position: absolute;
  top: 0;
}
/* Cover geometry is physical and must not mirror with the interface locale. */
/* rtl:begin:ignore */
.wrap-back {
  left: 0;
  --cover-photo-right: calc(var(--spine) / 2);
}
.wrap-front {
  left: calc(297mm + var(--spine));
  --cover-photo-left: calc(var(--spine) / 2);
}
.spine-guide {
  left: 297mm;
  width: var(--spine);
  top: 0;
  bottom: 0;
  border-inline: var(--guide-width, 1px) solid white;
  box-shadow: 0 0 0 var(--guide-width, 1px) black;
}
.cover-safe-guide {
  top: var(--safe-margin, 0mm);
  bottom: var(--safe-margin, 0mm);
  width: calc(297mm - 2 * var(--safe-margin, 0mm));
  border: var(--guide-width, 1px) dashed white;
  box-shadow: 0 0 0 var(--guide-width, 1px) black;
}
.back-safe {
  left: var(--safe-margin, 0mm);
}
.front-safe {
  left: calc(297mm + var(--spine) + var(--safe-margin, 0mm));
}
/* rtl:end:ignore */
.spine-guide,
.cover-safe-guide {
  display: none;
  position: absolute;
  box-sizing: border-box;
  pointer-events: none;
  z-index: 50;
}
</style>
