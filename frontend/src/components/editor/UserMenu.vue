<script lang="ts" setup>
import type { User } from "@/client";
import { useUserMutation } from "@/queries/useUserMutation";
import { ref } from "vue";
import DeleteDialog from "./DeleteDialog.vue";
import { matPerson, matStraighten, matThermostat, matLanguage, matDeleteOutline } from "@quasar/extras/material-icons";

const LOCALE_OPTIONS = [
  { label: "English (US)", value: "en_US" },
  { label: "English (UK)", value: "en_GB" },
  { label: "עברית", value: "he_IL" },
  { label: "العربية", value: "ar_SA" },
  { label: "Español", value: "es_ES" },
  { label: "Français", value: "fr_FR" },
  { label: "Deutsch", value: "de_DE" },
  { label: "Português", value: "pt_BR" },
  { label: "Italiano", value: "it_IT" },
  { label: "Nederlands", value: "nl_NL" },
  { label: "日本語", value: "ja_JP" },
  { label: "한국어", value: "ko_KR" },
  { label: "中文", value: "zh_CN" },
  { label: "Русский", value: "ru_RU" },
];

defineProps<{
  user: User;
  isKm: boolean;
  isCelsius: boolean;
}>();

defineEmits<{
  delete: [];
}>();

const { mutate: patch } = useUserMutation();
const showDeleteConfirm = ref(false);
const deleting = ref(false);
</script>

<template>
  <div class="user-pill">
    <q-avatar v-if="user.profile_image_path" size="1.5rem">
      <img :src="user.profile_image_path" :alt="user.first_name" />
    </q-avatar>
    <q-icon v-else :name="matPerson" size="1rem" />
    <span class="user-name">{{ user.first_name }}</span>

    <q-menu class="user-menu" anchor="bottom right" self="top right" :offset="[0, 4]">
      <div class="menu-content">
        <div class="menu-section">
          <div class="menu-row">
            <q-icon :name="matStraighten" size="1rem" />
            <span class="menu-label">{{ isKm ? 'Kilometers' : 'Miles' }}</span>
            <q-toggle
              :model-value="isKm"
              dense
              size="sm"
              @update:model-value="patch({ unit_is_km: $event })"
            />
          </div>
          <div class="menu-row">
            <q-icon :name="matThermostat" size="1rem" />
            <span class="menu-label">{{ isCelsius ? 'Celsius' : 'Fahrenheit' }}</span>
            <q-toggle
              :model-value="isCelsius"
              dense
              size="sm"
              @update:model-value="patch({ temperature_is_celsius: $event })"
            />
          </div>
          <div class="menu-row">
            <q-icon :name="matLanguage" size="1rem" />
            <q-select
              :model-value="user.locale"
              :options="LOCALE_OPTIONS"
              class="locale-select"
              dense
              borderless
              emit-value
              map-options
              options-dense
              @update:model-value="patch({ locale: $event })"
            />
          </div>
        </div>
        <div class="menu-divider" />
        <button class="menu-danger-btn" @click="showDeleteConfirm = true">
          <q-icon :name="matDeleteOutline" size="1rem" />
          Delete all data
        </button>
      </div>
    </q-menu>
  </div>

  <DeleteDialog v-model="showDeleteConfirm" :deleting="deleting" @confirm="$emit('delete')" />
</template>

<style lang="scss" scoped>
.user-pill {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.625rem 0.25rem 0.25rem;
  border-radius: 2rem;
  border: 1px solid var(--border-color);
  background: var(--surface);
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
  color: var(--text-muted);

  &:hover {
    background: var(--border-color);
  }
}

.user-name {
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--text);
}
</style>

<style lang="scss">
/* Teleported — must be unscoped */

.user-menu {
  background: var(--bg-secondary) !important;
  border: 1px solid var(--border-color);
  border-radius: 0.5rem !important;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
}

.menu-content {
  padding: 0.375rem;
  min-width: 12rem;
}

.menu-section {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.menu-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.375rem 0.5rem;
  border-radius: 0.375rem;
  color: var(--text);
  font-size: 0.8125rem;
}

.menu-label {
  flex: 1;
}

.menu-divider {
  height: 1px;
  background: var(--border-color);
  margin: 0.375rem 0;
}

.locale-select {
  flex: 1;
  min-width: 0;

  .q-field__native > span {
    font-size: 0.8125rem;
    color: var(--text);
  }

  .q-field__append {
    color: var(--text-faint);
  }
}

.menu-danger-btn {
  all: unset;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.375rem 0.5rem;
  border-radius: 0.375rem;
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--danger);
  box-sizing: border-box;
  transition: background 0.15s ease;

  &:hover {
    background: color-mix(in srgb, var(--danger) 12%, transparent);
  }
}
</style>
