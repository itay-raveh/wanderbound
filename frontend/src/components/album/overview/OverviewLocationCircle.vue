<script lang="ts" setup>
import { type Location } from "@/client";

defineProps<{ icon: string; location: Location }>();
</script>

<template>
  <div class="column">
    <q-avatar :icon="icon" class="q-mb-md" color="primary" size="4rem" />
    <div class="text-h6 text-weight-bold">{{ location.name }}</div>
    <div class="text-subtitle1">{{ location.detail }}</div>
  </div>
</template>
