<script lang="ts" setup>
import { type PsLocation } from "@/api";

defineProps<{ icon: string; location: PsLocation }>();
</script>

<template>
  <div class="column">
    <q-avatar :icon="icon" class="q-mb-md" color="primary" size="4rem" />
    <div class="text-h6 text-weight-bold">{{ location.name }}</div>
    <div class="text-subtitle1">{{ location.detail }}</div>
  </div>
</template>
