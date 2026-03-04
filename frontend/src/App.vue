<script lang="ts" setup>
import { RouterView } from "vue-router";
</script>

<template>
  <q-layout>
    <q-page-container>
      <RouterView />
    </q-page-container>
  </q-layout>
</template>

<style lang="scss">
body {
  font-family:
    "Inter",
    "Segoe UI",
    system-ui,
    -apple-system,
    sans-serif;
}
</style>
