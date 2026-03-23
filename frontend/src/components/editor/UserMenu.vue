<script lang="ts" setup>
import { deleteUser, logout } from "@/client";
import * as Sentry from "@sentry/vue";
import { clearMsalCache } from "@/composables/useMicrosoftAuth";
import { googleLogout } from "vue3-google-login";
import { useQueryCache } from "@pinia/colada";
import { useUserQuery } from "@/queries/useUserQuery";
import { useUserMutation } from "@/queries/useUserMutation";
import { getLocaleOptions, resolveLocale } from "@/composables/useLocale";
import { useQuasar } from "quasar";
import { useI18n } from "vue-i18n";
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import DeleteDialog from "./DeleteDialog.vue";
import {
  matPerson,
  matLightMode,
  matDarkMode,
  matDeleteOutline,
  matDownload,
  matSettings,
  matLogout,
  matUploadFile,
} from "@quasar/extras/material-icons";
import { useDataExport } from "@/composables/useDataExport";

const router = useRouter();
const cache = useQueryCache();
const { user, isKm, isCelsius } = useUserQuery();
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
    (o) => o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q),
  );
});

function onLocaleFilter(val: string, update: (fn: () => void) => void) {
  update(() => {
    localeFilter.value = val;
  });
}

async function clearAllAuthState() {
  Sentry.setUser(null);
  googleLogout();
  await Promise.all([cache.invalidateQueries(undefined, false), clearMsalCache()]);
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
    <button class="settings-trigger" :class="{ open: menuOpen }" :aria-label="t('settings.menu')" :aria-expanded="menuOpen">
      <q-avatar v-if="user.profile_image_url" size="2rem" class="trigger-avatar">
        <img :src="user.profile_image_url" :alt="user.first_name" referrerpolicy="no-referrer" />
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
            <h4 class="section-title text-overline text-faint">{{ t("settings.appearance") }}</h4>
            <div class="seg-track">
              <button
                :class="{ active: !$q.dark.isActive }"
                class="seg-btn"
                @click="$q.dark.isActive && $q.dark.set(false)"
              >
                <q-icon :name="matLightMode" size="0.875rem" />
                {{ t("settings.light") }}
              </button>
              <button
                :class="{ active: $q.dark.isActive }"
                class="seg-btn"
                @click="$q.dark.isActive || $q.dark.set(true)"
              >
                <q-icon :name="matDarkMode" size="0.875rem" />
                {{ t("settings.dark") }}
              </button>
            </div>
          </section>

          <!-- Locale -->
          <section class="card-section">
            <h4 class="section-title text-overline text-faint">{{ t("settings.locale") }}</h4>
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
                @update:model-value="$event !== user.locale && patch({ locale: $event })"
              />
            </div>
            <div class="unit-row row no-wrap items-center justify-between">
              <span class="unit-label text-body2">{{ t("settings.distance") }}</span>
              <div class="seg-track compact">
                <button
                  :class="{ active: isKm }"
                  class="seg-btn"
                  @click="isKm || patch({ unit_is_km: true })"
                >{{ t("overview.km") }}</button>
                <button
                  :class="{ active: !isKm }"
                  class="seg-btn"
                  @click="isKm && patch({ unit_is_km: false })"
                >{{ t("overview.mi") }}</button>
              </div>
            </div>
            <div class="unit-row row no-wrap items-center justify-between">
              <span class="unit-label text-body2">{{ t("settings.temperature") }}</span>
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

          <!-- Data -->
          <section class="card-section">
            <h4 class="section-title text-overline text-faint">{{ t("settings.data") }}</h4>

            <button class="action-btn" @click="menuOpen = false; router.push({ name: 'upload' })">
              <q-icon :name="matUploadFile" size="1rem" />
              {{ t("settings.reuploadData") }}
            </button>

            <button class="action-btn" @click="menuOpen = false; exportStream.start()">
              <q-icon :name="matDownload" size="1rem" />
              {{ t("settings.exportData") }}
            </button>
          </section>

          <q-separator class="q-my-sm" />

          <button class="action-btn" @click="handleSignOut">
            <q-icon :name="matLogout" size="1rem" />
            {{ t("settings.signOut") }}
          </button>

          <button class="danger-btn" @click="showDeleteConfirm = true">
            <q-icon :name="matDeleteOutline" size="1rem" />
            {{ t("settings.deleteAll") }}
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
  padding: var(--gap-sm-md) 0.6rem var(--gap-sm-md) var(--gap-sm-md);
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

  &:focus-visible {
    outline: 2px solid var(--q-primary);
    outline-offset: 2px;
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
  padding: 0 var(--gap-xs);
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

  &:focus-visible {
    outline: 2px solid var(--q-primary);
    outline-offset: 1px;
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
  margin-bottom: var(--gap-md-lg);
}

.action-btn,
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
    outline: 2px solid var(--q-primary);
    outline-offset: -1px;
  }
}

.action-btn {
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
</style>
