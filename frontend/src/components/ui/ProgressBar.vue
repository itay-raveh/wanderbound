<script lang="ts" setup>
const props = defineProps<{ progress: number }>();
</script>

<template>
  <q-linear-progress
    :indeterminate="props.progress === 0"
    :value="props.progress"
    color="primary"
    size="0.25rem"
    class="progress-q"
  />
</template>

<style lang="scss" scoped>
.progress-q {
  border-radius: var(--radius-xs);
}
</style>
