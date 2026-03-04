<script lang="ts" setup>
defineProps<{
  value: string | number;
  unit: string;
  icon: string;
}>();
</script>

<template>
  <div class="column items-center">
    <q-icon :name="icon" class="text-weight-light" size="5rem" />
    <div class="text-primary text-weight-bold text-h5">{{ value }}</div>
    <div class="text-subtitle1">{{ unit }}</div>
  </div>
</template>
