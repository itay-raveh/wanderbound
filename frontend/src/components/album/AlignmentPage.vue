<script lang="ts" setup>
import { usePrintMode } from "@/composables/usePrintReady";
import { t } from "@/i18n";

const printMode = usePrintMode();
</script>

<template>
  <div class="alignment-item">
    <div class="page-container alignment-artwork">
      <img src="/topo-contours.svg" alt="" />
      <div v-if="!printMode" class="alignment-note" role="note">
        <strong>{{ t("panorama.alignment.title") }}</strong>
        <p>{{ t("panorama.alignment.body") }}</p>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.alignment-artwork {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.alignment-artwork img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0.18;
}

.alignment-note {
  position: relative;
  max-width: 34rem;
  padding: 2rem 2.5rem;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  background: color-mix(in srgb, var(--surface) 92%, transparent);
  box-shadow: var(--shadow-md);
  color: var(--text);
  font-family: var(--font-ui);
  text-align: center;
}

.alignment-note strong {
  display: block;
  color: var(--text-bright);
  font-size: var(--type-2xl);
  line-height: 1.2;
}

.alignment-note p {
  margin: var(--gap-lg) 0 0;
  color: var(--text-muted);
  font-size: var(--type-md);
  line-height: 1.5;
}
</style>
