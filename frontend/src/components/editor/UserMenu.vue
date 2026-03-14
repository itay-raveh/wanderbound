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
      <div v-else class="trigger-avatar-fallback">
        <q-icon :name="matPerson" size="1.125rem" />
      </div>
      <span class="trigger-name">{{ user.first_name }}</span>

      <div class="trigger-divider" />
      <q-icon :name="matSettings" size="1.125rem" class="trigger-gear" />

      <q-menu
        v-model="menuOpen"
        class="settings-popover"
        anchor="bottom right"
        self="top right"
        :offset="[0, 8]"
      >
        <div class="settings-card">
          <!-- Appearance -->
          <section class="card-section">
            <h4 class="section-title">Appearance</h4>
            <div class="seg-track">
              <button
                :class="{ active: !$q.dark.isActive }"
                class="seg-btn"
                @click="$q.dark.set(false)"
              >
                <q-icon :name="matLightMode" size="0.875rem" />
                Light
              </button>
              <button
                :class="{ active: $q.dark.isActive }"
                class="seg-btn"
                @click="$q.dark.set(true)"
              >
                <q-icon :name="matDarkMode" size="0.875rem" />
                Dark
              </button>
            </div>
          </section>

          <!-- Units -->
          <section class="card-section">
            <h4 class="section-title">Units</h4>
            <div class="unit-row">
              <span class="unit-label">Distance</span>
              <div class="seg-track compact">
                <button
                  :class="{ active: isKm }"
                  class="seg-btn"
                  @click="patch({ unit_is_km: true })"
                >km</button>
                <button
                  :class="{ active: !isKm }"
                  class="seg-btn"
                  @click="patch({ unit_is_km: false })"
                >mi</button>
              </div>
            </div>
            <div class="unit-row">
              <span class="unit-label">Temperature</span>
              <div class="seg-track compact">
                <button
                  :class="{ active: isCelsius }"
                  class="seg-btn"
                  @click="patch({ temperature_is_celsius: true })"
                >°C</button>
                <button
                  :class="{ active: !isCelsius }"
                  class="seg-btn"
                  @click="patch({ temperature_is_celsius: false })"
                >°F</button>
              </div>
            </div>
          </section>

          <!-- Language -->
          <section class="card-section">
            <h4 class="section-title">Language</h4>
            <div class="locale-wrapper">
              <q-select
                :model-value="user.locale"
                :options="LOCALE_OPTIONS"
                dense
                borderless
                emit-value
                map-options
                options-dense
                menu-anchor="bottom start"
                menu-self="top start"
                @update:model-value="patch({ locale: $event })"
              />
            </div>
          </section>

          <div class="card-divider" />

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
  gap: 0.5rem;
  padding: 0.35rem 0.6rem 0.35rem 0.35rem;
  border-radius: 2rem;
  border: 1px solid var(--border-color);
  background: var(--surface);
  cursor: pointer;
  transition: all 0.15s ease;
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
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.trigger-name {
  font-size: 0.8125rem;
  font-weight: 600;
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
  transition: all 0.25s ease;

  .settings-trigger:hover &,
  .settings-trigger.open & {
    color: var(--text);
    transform: rotate(45deg);
  }
}

// ─── Settings Card (rendered inside teleported QMenu, but scoped attrs are preserved) ───

.settings-card {
  padding: 0.75rem;
  min-width: 15rem;
}

.card-section {
  &:not(:first-child) {
    margin-top: 0.75rem;
  }
}

.section-title {
  font-size: 0.625rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-faint);
  margin: 0 0 0.4rem;
  padding: 0 0.125rem;
}

.seg-track {
  display: flex;
  gap: 2px;
  padding: 3px;
  border-radius: 0.5rem;
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
  padding: 0.375rem 0.75rem;
  border-radius: 0.375rem;
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-muted);
  transition: all 0.15s ease;

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
    padding: 0.25rem 0.5rem;
    font-weight: 600;
  }
}

.unit-row {
  display: flex;
  align-items: center;
  justify-content: space-between;

  &:not(:last-child) {
    margin-bottom: 0.375rem;
  }
}

.unit-label {
  font-size: 0.8125rem;
  color: var(--text);
}

.locale-wrapper {
  background: color-mix(in srgb, black 10%, var(--bg-secondary));
  border-radius: 0.5rem;
  padding: 0 0.5rem;

  :deep(.q-field__native > span) {
    font-size: 0.8125rem;
    color: var(--text);
  }

  :deep(.q-field__append) {
    color: var(--text-faint);
  }
}

.card-divider {
  height: 1px;
  background: var(--border-color);
  margin: 0.75rem 0;
}

.danger-btn {
  all: unset;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.375rem 0.5rem;
  border-radius: 0.375rem;
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--danger);
  box-sizing: border-box;
  transition: background 0.15s ease;

  &:hover {
    background: color-mix(in srgb, var(--danger) 12%, transparent);
  }
}
</style>

<style lang="scss">
/* QMenu creates its own wrapper element outside our template — must be unscoped */
.settings-popover {
  background: var(--bg-secondary) !important;
  border: 1px solid var(--border-color);
  border-radius: 0.75rem !important;
  box-shadow:
    0 8px 30px rgba(0, 0, 0, 0.12),
    0 2px 8px rgba(0, 0, 0, 0.06);
}
</style>
