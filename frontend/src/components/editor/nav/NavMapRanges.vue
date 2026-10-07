<script lang="ts" setup>
import { useI18n } from "vue-i18n";
import { symOutlinedAdd } from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();

defineEmits<{
  addMap: [];
}>();
</script>

<template>
  <button type="button" class="nav-add-map" @click="$emit('addMap')">
    <q-icon :name="symOutlinedAdd" size="var(--type-sm)" />
    <span>{{ t("nav.addMap") }}</span>
  </button>
</template>

<style lang="scss" scoped>
@use "@/styles/editor-secondary-action" as *;

.nav-add-map {
  @include editor-secondary-action;
}
</style>
