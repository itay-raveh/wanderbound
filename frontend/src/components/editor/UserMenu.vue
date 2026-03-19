<script lang="ts" setup>
import { deleteUser } from "@/client";
import { useUserQuery } from "@/queries/useUserQuery";
import { useUserMutation } from "@/queries/useUserMutation";
import { useQuasar } from "quasar";
import { ref } from "vue";
import { useRouter } from "vue-router";
import DeleteDialog from "./DeleteDialog.vue";
import {
  matPerson,
  matLightMode,
  matDarkMode,
  matDeleteOutline,
  matSettings,
} from "@quasar/extras/material-icons";

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

const router = useRouter();
const { user, isKm, isCelsius } = useUserQuery();
const { mutate: patch } = useUserMutation();
const $q = useQuasar();

const menuOpen = ref(false);
const showDeleteConfirm = ref(false);
const deleting = ref(false);

async function handleDelete() {
  deleting.value = true;
  try {
    await deleteUser();
    await router.push("/register");
  } catch {
    $q.notify({ type: "negative", message: "Failed to delete user." });
  } finally {
    deleting.value = false;
  }
}
</script>

<template>
  <template v-if="user">
    <button class="settings-trigger" :class="{ open: menuOpen }">
      <q-avatar v-if="user.profile_image_path" size="2rem" class="trigger-avatar">
        <img :src="user.profile_image_path" :alt="user.first_name" />
      </q-avatar>
      <div v-else class="trigger-avatar-fallback flex flex-center">
        <q-icon :name="matPerson" size="1.125rem" />
      </div>
      <span class="trigger-name text-weight-semibold text-body2">{{ user.first_name }}</span>

      <div class="trigger-divider" />
      <q-icon :name="matSettings" size="1.125rem" class="trigger-gear" />

      <q-menu
        v-model="menuOpen"
        anchor="bottom right"
        self="top right"
        :offset="[0, 8]"
      >
        <div class="settings-card">
          <!-- Appearance -->
          <section class="card-section">
            <h4 class="section-title text-overline text-faint">Appearance</h4>
            <div class="seg-track">
              <button
                :class="{ active: !$q.dark.isActive }"
                class="seg-btn"
                @click="$q.dark.isActive && $q.dark.set(false)"
              >
                <q-icon :name="matLightMode" size="0.875rem" />
                Light
              </button>
              <button
                :class="{ active: $q.dark.isActive }"
                class="seg-btn"
                @click="$q.dark.isActive || $q.dark.set(true)"
              >
                <q-icon :name="matDarkMode" size="0.875rem" />
                Dark
              </button>
            </div>
          </section>

          <!-- Units -->
          <section class="card-section">
            <h4 class="section-title text-overline text-faint">Units</h4>
            <div class="unit-row row no-wrap items-center justify-between">
              <span class="unit-label text-body2">Distance</span>
              <div class="seg-track compact">
                <button
                  :class="{ active: isKm }"
                  class="seg-btn"
                  @click="isKm || patch({ unit_is_km: true })"
                >km</button>
                <button
                  :class="{ active: !isKm }"
                  class="seg-btn"
                  @click="isKm && patch({ unit_is_km: false })"
                >mi</button>
              </div>
            </div>
            <div class="unit-row row no-wrap items-center justify-between">
              <span class="unit-label text-body2">Temperature</span>
              <div class="seg-track compact">
                <button
                  :class="{ active: isCelsius }"
                  class="seg-btn"
                  @click="isCelsius || patch({ temperature_is_celsius: true })"
                >°C</button>
                <button
                  :class="{ active: !isCelsius }"
                  class="seg-btn"
                  @click="isCelsius && patch({ temperature_is_celsius: false })"
                >°F</button>
              </div>
            </div>
          </section>

          <!-- Language -->
          <section class="card-section">
            <h4 class="section-title text-overline text-faint">Language</h4>
            <div class="locale-wrapper">
              <q-select
                class="compact-field"
                :model-value="user.locale"
                :options="LOCALE_OPTIONS"
                dense
                borderless
                emit-value
                map-options
                options-dense
                menu-anchor="bottom start"
                menu-self="top start"
                @update:model-value="$event !== user.locale && patch({ locale: $event })"
              />
            </div>
          </section>

          <q-separator class="q-my-sm" />

          <button class="danger-btn" @click="showDeleteConfirm = true">
            <q-icon :name="matDeleteOutline" size="1rem" />
            Delete all data
          </button>
        </div>
      </q-menu>
    </button>

    <DeleteDialog v-model="showDeleteConfirm" :deleting="deleting" @confirm="handleDelete" />
  </template>
</template>

<style lang="scss" scoped>
.settings-trigger {
  all: unset;
  display: flex;
  align-items: center;
  gap: var(--gap-md);
  padding: 0.35rem 0.6rem 0.35rem 0.35rem;
  border-radius: var(--radius-full);
  border: 1px solid var(--border-color);
  background: var(--surface);
  cursor: pointer;
  transition: background var(--duration-fast) ease, border-color var(--duration-fast) ease;
  color: var(--text-muted);

  &:hover,
  &.open {
    border-color: color-mix(in srgb, var(--text) 30%, transparent);
    background: var(--border-color);
  }
}

.trigger-avatar {
  flex-shrink: 0;
}

.trigger-avatar-fallback {
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  background: color-mix(in srgb, var(--q-primary) 15%, var(--surface));
  color: var(--q-primary);
  flex-shrink: 0;
}

.trigger-name {
  color: var(--text);
}

.trigger-divider {
  width: 1px;
  height: 1.25rem;
  background: var(--border-color);
  flex-shrink: 0;
}

.trigger-gear {
  color: var(--text-faint);
  transition: color var(--duration-normal) ease, transform var(--duration-normal) ease;

  .settings-trigger:hover &,
  .settings-trigger.open & {
    color: var(--text);
    transform: rotate(45deg);
  }
}

// Rendered inside teleported QMenu, but scoped attrs are preserved
.settings-card {
  padding: var(--gap-md-lg);
  min-width: 15rem;
}

.card-section {
  &:not(:first-child) {
    margin-top: var(--gap-md-lg);
  }
}

.section-title {
  margin: 0 0 var(--gap-md);
  padding: 0 0.125rem;
}

.seg-track {
  display: flex;
  gap: var(--gap-xs);
  padding: 3px;
  border-radius: var(--radius-md);
  background: color-mix(in srgb, black 10%, var(--bg-secondary));
}

.seg-btn {
  all: unset;
  cursor: pointer;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.3rem;
  padding: var(--gap-sm-md) var(--gap-md-lg);
  border-radius: var(--radius-sm);
  font-size: var(--type-sm);
  font-weight: 500;
  color: var(--text-muted);
  transition: background var(--duration-fast) ease, color var(--duration-fast) ease, box-shadow var(--duration-fast) ease;

  &:hover:not(.active) {
    color: var(--text);
  }

  &.active {
    background: var(--bg-secondary);
    color: var(--text-bright);
    box-shadow:
      0 1px 3px rgba(0, 0, 0, 0.1),
      0 0 0 0.5px rgba(0, 0, 0, 0.04);
  }
}

.seg-track.compact {
  width: 6rem;
  flex-shrink: 0;

  .seg-btn {
    padding: var(--gap-sm) var(--gap-md);
    font-weight: 600;
  }
}

.unit-row {
  &:not(:last-child) {
    margin-bottom: var(--gap-sm-md);
  }
}

.unit-label {
  color: var(--text);
}

.locale-wrapper {
  background: color-mix(in srgb, black 10%, var(--bg-secondary));
  border-radius: var(--radius-md);
  padding: 0 var(--gap-md);
}

.danger-btn {
  all: unset;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--gap-md);
  width: 100%;
  padding: var(--gap-sm-md) var(--gap-md);
  border-radius: var(--radius-sm);
  font-size: var(--type-sm);
  font-weight: 500;
  color: var(--danger);
  box-sizing: border-box;
  transition: background var(--duration-fast) ease;

  &:hover {
    background: color-mix(in srgb, var(--danger) 12%, transparent);
  }
}
</style>
