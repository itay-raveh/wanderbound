<script lang="ts" setup>
defineProps<{
  text: string;
  stepName: string;
  locationName: string;
}>();
</script>

<template>
  <div class="page-container text-page column no-wrap">
    <div class="text-page-header text-muted">
      <span class="text-weight-bold text-uppercase">{{ stepName }}</span>
      <span>{{ locationName }}</span>
      <span class="q-ml-auto text-italic">continued...</span>
    </div>
    <div dir="auto" class="text-page-body">
      {{ text }}
    </div>
  </div>
</template>

<style lang="scss" scoped>
.text-page {
  background: var(--bg);
  color: var(--text);
}

.text-page-header {
  display: flex;
  align-items: center;
  gap: var(--gap-lg);
  padding: 2rem 4rem 1rem;
  font-size: var(--type-sm);
}

.text-page-body {
  flex: 1;
  padding: 0 4rem var(--page-inset-y);
  font-size: var(--type-md);
  line-height: 1.6;
  white-space: pre-wrap;
  text-align: justify;
  column-width: 30rem;
  column-fill: auto;
  column-gap: var(--page-inset-x);
}
</style>
