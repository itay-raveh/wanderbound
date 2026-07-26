<script lang="ts" setup>
import { usePrintMode } from "@/composables/usePrintReady";
import { useI18n } from "vue-i18n";

const { t } = useI18n();
const printMode = usePrintMode();
</script>

<template>
  <div class="alignment-item relative-position">
    <div class="page-container alignment-artwork">
      <img src="/topo-contours.svg" alt="" />
    </div>
    <div v-if="!printMode" class="alignment-help">
      {{ t("album.panoramaAlignment") }}
    </div>
  </div>
</template>

<style lang="scss" scoped>
.alignment-artwork {
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.alignment-artwork img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0.18;
}

.alignment-help {
  position: absolute;
  right: var(--gap-lg);
  bottom: calc(var(--gap-md-lg) + var(--gap-lg));
  max-width: 20rem;
  padding: var(--gap-md) var(--gap-md-lg);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface);
  color: var(--text);
  font: var(--type-sm) / 1.4 var(--font-ui);
}

@media print {
  .alignment-help {
    display: none;
  }
}
</style>
