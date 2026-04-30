<script lang="ts" setup>
import { deleteUser, logout } from "@/client";
import { useUserQuery } from "@/queries/useUserQuery";
import { useUserMutation } from "@/queries/useUserMutation";
import { getLocaleOptions, resolveLocale } from "@/composables/useLocale";
import { useQuasar } from "quasar";
import { useI18n } from "vue-i18n";
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import DeleteDialog from "./DeleteDialog.vue";
import SegmentedControl from "@/components/ui/SegmentedControl.vue";

import {
  matPerson,
  matLightMode,
  matDarkMode,
  matBrightnessAuto,
  matDeleteOutline,
  matDownload,
  matSettings,
  matLogout,
  matUploadFile,
} from "@quasar/extras/material-icons";
import { useDarkMode } from "@/composables/useDarkMode";
import { useDataExport } from "@/composables/useDataExport";

const router = useRouter();
const darkMode = useDarkMode();
const { user, isKm, isCelsius, isDemo, exitDemo, clearAllAuthState } =
  useUserQuery();
const { mutate: patch } = useUserMutation();
const $q = useQuasar();
const { t } = useI18n();

const exportStream = useDataExport();
const menuOpen = ref(false);
const showDeleteConfirm = ref(false);
const deleting = ref(false);
const localeFilter = ref("");

const filteredLocaleOptions = computed(() => {
  const options = getLocaleOptions();
  const q = localeFilter.value.toLowerCase();
  if (!q) return options;
  return options.filter(
    (o) =>
      o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q),
  );
});

function onLocaleFilter(val: string, update: (fn: () => void) => void) {
  update(() => {
    localeFilter.value = val;
  });
}

async function handleSignOut() {
  try {
    await logout();
  } catch {
    /* server down - cookie will expire naturally */
  }
  await clearAllAuthState();
  await router.push({ name: "landing" });
}

async function handleDelete() {
  deleting.value = true;
  try {
    await deleteUser();
    await clearAllAuthState();
    await router.push({ name: "landing" });
  } catch {
    $q.notify({ type: "negative", message: t("settings.deleteFailed") });
  } finally {
    deleting.value = false;
  }
}
</script>

<template>
  <template v-if="user">
    <button
      type="button"
      class="settings-trigger"
      :class="{ open: menuOpen }"
      :aria-label="`${user.first_name} - ${t('settings.menu')}`"
      :aria-expanded="menuOpen"
      aria-haspopup="menu"
    >
      <template v-if="!isDemo">
        <q-avatar
          v-if="user.profile_image_url"
          size="2rem"
          class="trigger-avatar"
        >
          <img
            :src="user.profile_image_url"
            :alt="user.first_name"
            referrerpolicy="no-referrer"
          />
        </q-avatar>
        <div v-else class="trigger-avatar-fallback flex flex-center">
          <q-icon :name="matPerson" size="1.125rem" />
        </div>
      </template>
      <span class="trigger-name text-weight-semibold text-body2">{{
        user.first_name
      }}</span>

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
            <SegmentedControl
              v-model="darkMode"
              :options="[
                {
                  label: t('settings.light'),
                  value: 'light',
                  icon: matLightMode,
                },
                {
                  label: t('settings.system'),
                  value: 'system',
                  icon: matBrightnessAuto,
                },
                { label: t('settings.dark'), value: 'dark', icon: matDarkMode },
              ]"
              :aria-label="t('settings.appearance')"
            />
          </section>

          <!-- Locale -->
          <section class="card-section">
            <div class="locale-wrapper">
              <q-select
                class="compact-field"
                :model-value="resolveLocale(user.locale)"
                :options="filteredLocaleOptions"
                dense
                borderless
                emit-value
                map-options
                options-dense
                use-input
                input-debounce="0"
                menu-anchor="bottom start"
                menu-self="top start"
                @filter="onLocaleFilter"
                @update:model-value="
                  $event !== user.locale && patch({ locale: $event })
                "
              />
            </div>
            <div class="unit-row row no-wrap items-center justify-between">
              <span class="unit-label text-body2">{{
                t("settings.distance")
              }}</span>
              <SegmentedControl
                :model-value="isKm"
                :options="[
                  { label: t('units.km'), value: true },
                  { label: t('units.mi'), value: false },
                ]"
                :aria-label="t('settings.distance')"
                compact
                @update:model-value="patch({ unit_is_km: $event })"
              />
            </div>
            <div class="unit-row row no-wrap items-center justify-between">
              <span class="unit-label text-body2">{{
                t("settings.temperature")
              }}</span>
              <SegmentedControl
                :model-value="isCelsius"
                :options="[
                  { label: '°C', value: true },
                  { label: '°F', value: false },
                ]"
                :aria-label="t('settings.temperature')"
                compact
                @update:model-value="patch({ temperature_is_celsius: $event })"
              />
            </div>
          </section>

          <!-- Account (collapsible) -->
          <details class="card-section account-details">
            <summary class="section-title">{{ t("settings.account") }}</summary>

            <button
              v-if="!isDemo"
              class="menu-item-btn"
              @click="
                menuOpen = false;
                router.push({ name: 'upload' });
              "
            >
              <q-icon :name="matUploadFile" size="1rem" />
              {{ t("settings.reuploadData") }}
            </button>

            <button
              class="menu-item-btn"
              @click="
                menuOpen = false;
                exportStream.start();
              "
            >
              <q-icon :name="matDownload" size="1rem" />
              {{ t("settings.exportData") }}
            </button>

            <button class="danger-btn" @click="showDeleteConfirm = true">
              <q-icon :name="matDeleteOutline" size="1rem" />
              {{ t("settings.deleteAll") }}
            </button>
          </details>

          <q-separator class="q-my-sm" />

          <button v-if="isDemo" class="menu-item-btn" @click="exitDemo">
            <q-icon :name="matLogout" size="1rem" />
            {{ t("demo.bannerCta") }}
          </button>
          <button v-else class="menu-item-btn" @click="handleSignOut">
            <q-icon :name="matLogout" size="1rem" />
            {{ t("settings.signOut") }}
          </button>
        </div>
      </q-menu>
    </button>

    <DeleteDialog
      v-model="showDeleteConfirm"
      :deleting="deleting"
      @confirm="handleDelete"
    />
  </template>
</template>

<style lang="scss" scoped>
.settings-trigger {
  all: unset;
  display: flex;
  align-items: center;
  gap: var(--gap-md);
  padding: var(--gap-sm-md) var(--gap-md) var(--gap-sm-md) var(--gap-sm-md);
  border-radius: var(--radius-full);
  border: 1px solid color-mix(in srgb, var(--text) 18%, transparent);
  background: var(--surface);
  cursor: pointer;
  transition:
    background var(--duration-fast) ease,
    border-color var(--duration-fast) ease;
  color: var(--text-muted);

  &:hover,
  &.open {
    border-color: color-mix(in srgb, var(--text) 30%, transparent);
    background: var(--border-color);
  }

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.125rem;
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
  transition:
    color var(--duration-normal) ease,
    transform var(--duration-normal) ease;

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
  overflow: visible;
}

.card-section {
  &:not(:first-child) {
    margin-top: var(--gap-md-lg);
  }
}

.section-title {
  margin: 0 0 var(--gap-md);
  padding: 0 var(--gap-xs);
  font-size: var(--type-xs);
  font-weight: 600;
  color: var(--text-muted);
  text-transform: none;
  letter-spacing: normal;
}

.account-details {
  > summary {
    cursor: pointer;
    list-style: none;
    display: flex;
    align-items: center;
    gap: var(--gap-sm);

    &::after {
      content: "›";
      font-size: var(--type-sm);
      color: var(--text-faint);
      transition: transform var(--duration-fast) ease;
    }

    &::-webkit-details-marker {
      display: none;
    }
  }

  &[open] > summary::after {
    transform: rotate(90deg);
  }

  > :not(summary) {
    margin-top: var(--gap-sm-md);
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
  background: color-mix(in srgb, var(--text) 8%, var(--bg-secondary));
  border-radius: var(--radius-md);
  padding: 0 var(--gap-md);
  margin-bottom: var(--gap-md-lg);
}

.menu-item-btn,
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
  box-sizing: border-box;
  transition: background var(--duration-fast) ease;

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: -1px;
  }
}

.menu-item-btn {
  color: var(--text-muted);

  &:hover {
    background: color-mix(in srgb, var(--text) 8%, transparent);
    color: var(--text);
  }
}

.danger-btn {
  color: var(--danger);

  &:hover {
    background: color-mix(in srgb, var(--danger) 12%, transparent);
  }
}

@media (prefers-reduced-motion: reduce) {
  .settings-trigger,
  .trigger-gear,
  .menu-item-btn,
  .danger-btn,
  .account-details > summary::after {
    transition: none;
  }

  .settings-trigger:hover .trigger-gear,
  .settings-trigger.open .trigger-gear {
    transform: none;
  }

  .account-details[open] > summary::after {
    transform: none;
  }
}
</style>
