<script lang="ts" setup>
import type { Step } from "@/client";
import type { JustifiedLine } from "@/composables/useTextLayout";
import { useAlbum } from "@/composables/useAlbum";
import { mediaQuality, PHOTO_PANEL_FRACTION } from "@/utils/photoQuality";
import MediaItem from "../MediaItem.vue";
import StepMetaPanel from "./StepMetaPanel.vue";
import { computed } from "vue";

const { mediaByName } = useAlbum();

const props = defineProps<{
  step: Step;
  sidebarLines?: JustifiedLine[];
}>();

const emit = defineEmits<{
  "update:name": [name: string];
  "update:description": [description: string];
}>();

const coverQuality = computed(() =>
  props.step.cover ? mediaQuality(props.step.cover, PHOTO_PANEL_FRACTION, mediaByName.value) : null,
);
</script>

<template>
  <div class="page-container step-main">
    <StepMetaPanel
      :step="step"
      :sidebar-lines="sidebarLines"
      class="meta-side"
      @update:name="emit('update:name', $event)"
      @update:description="emit('update:description', $event)"
    />

    <div class="content-panel">
      <MediaItem
        v-if="step.cover"
        :media="step.cover"
        fit-cover
        :focusable="false"
        :quality="coverQuality"
        class="cover-media"
      />
      <div v-else class="topo-filler" />
    </div>
  </div>
</template>

<style lang="scss" scoped>
.step-main {
  display: flex;
  background: var(--bg);
  color: var(--text);
  overflow: hidden;
}

.meta-side {
  flex: 0 0 var(--meta-width);
}

.content-panel {
  flex: 1;
  display: flex;
  min-height: 0;
}

.cover-media {
  cursor: default;
}

.topo-filler {
  flex: 1;
  min-height: 0;
  background: url('/topo-contours.svg') center / cover no-repeat;
  print-color-adjust: exact;
}
</style>
