<script lang="ts" setup>
import { chooseTextDir } from "@/utils/text";

defineProps<{
  text: string;
  stepName: string;
  locationName: string;
}>();
</script>

<template>
  <div class="page-container text-page">
    <div class="text-page-header">
      <span class="text-page-name">{{ stepName }}</span>
      <span class="text-page-location">{{ locationName }}</span>
      <span class="text-page-continued">continued...</span>
    </div>
    <div :dir="chooseTextDir(text)" class="text-page-body">
      {{ text }}
    </div>
  </div>
</template>

<style lang="scss" scoped>
.text-page {
  display: flex;
  flex-direction: column;
  background: var(--bg);
  color: var(--text);
}

.text-page-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 2rem 4rem 1rem;
  font-size: 0.85rem;
  color: var(--text-muted);
}

.text-page-name {
  font-weight: bold;
  text-transform: uppercase;
}

.text-page-continued {
  margin-left: auto;
  font-style: italic;
}

.text-page-body {
  flex: 1;
  padding: 0 4rem 3rem;
  font-size: 1rem;
  line-height: 1.6;
  white-space: pre-wrap;
  text-align: justify;
  column-width: 30rem;
  column-fill: auto;
  column-gap: 3rem;
}
</style>
