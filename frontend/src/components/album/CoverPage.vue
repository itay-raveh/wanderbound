<script setup lang="ts">
import type { AlbumChapter, AlbumMeta, StepRead } from "@/client";
import { usePrintMode } from "@/composables/usePrintReady";
import { previewCoverChapterId } from "@/composables/usePrintSettings";
import { t } from "@/i18n";
import { symOutlinedViewWeek } from "@quasar/extras/material-symbols-outlined";
import AlbumPage from "./AlbumPage.vue";
import CoverArtwork from "./CoverArtwork.vue";
const printMode = usePrintMode();
defineProps<{
  album: AlbumMeta;
  chapter: AlbumChapter;
  steps: StepRead[];
  isBack?: boolean;
}>();
</script>
<template>
  <AlbumPage cover>
    <CoverArtwork
      :album="album"
      :chapter="chapter"
      :steps="steps"
      :is-back="isBack"
    >
      <template v-if="!printMode" #actions>
        <button
          type="button"
          class="album-action"
          :aria-label="t('print.previewCover')"
          @click="previewCoverChapterId = chapter.id"
        >
          <q-icon :name="symOutlinedViewWeek" />
          <q-tooltip>{{ t("print.previewCover") }}</q-tooltip>
        </button>
      </template>
    </CoverArtwork>
  </AlbumPage>
</template>

<style lang="scss" scoped src="./AlbumActions.scss"></style>
