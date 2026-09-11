<script lang="ts" setup>
import { loginLocalUser } from "@/client";
import { queryKeys } from "@/queries/keys";
import { useLocalUsersQuery } from "@/queries/useLocalUsersQuery";
import { useQueryCache } from "@pinia/colada";
import { useQuasar } from "quasar";
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";

const { t } = useI18n();
const router = useRouter();
const cache = useQueryCache();
const $q = useQuasar();
const open = ref(false);
const loggingIn = ref(false);
const { data: users, error, asyncStatus, refetch } = useLocalUsersQuery(open);

async function login(uid: number) {
  if (loggingIn.value) return;
  loggingIn.value = true;
  try {
    const { data: user } = await loginLocalUser({ path: { uid } });
    await cache.invalidateQueries(undefined, false);
    cache.setQueryData(queryKeys.user(), user);
    await cache.invalidateQueries({ key: queryKeys.authState() });
    await router.push({ name: user.is_processed ? "editor" : "upload" });
  } catch {
    $q.notify({ type: "negative", message: t("login.signInFailed") });
  } finally {
    loggingIn.value = false;
  }
}
</script>

<template>
  <q-btn-dropdown
    v-model="open"
    :label="t('login.localContinue')"
    :loading="loggingIn"
    dropdown-icon="expand_more"
    menu-anchor="bottom middle"
    menu-self="top middle"
    :menu-offset="[0, 8]"
    :content-style="{ minWidth: '16.25rem', maxWidth: 'calc(100vw - 2rem)' }"
    flat
    no-caps
  >
    <q-list role="presentation">
      <q-item v-if="asyncStatus === 'loading'">
        <q-item-section><q-spinner color="primary" /></q-item-section>
      </q-item>
      <q-item v-else-if="error">
        <q-item-section>
          <q-item-label role="alert">{{
            t("login.localLoadFailed")
          }}</q-item-label>
          <q-btn flat no-caps :label="t('login.localRetry')" @click="refetch()" />
        </q-item-section>
      </q-item>
      <q-item v-else-if="!users?.length">
        <q-item-section>{{ t("login.localEmpty") }}</q-item-section>
      </q-item>
      <q-item
        v-for="user in users"
        v-else
        :key="user.id"
        clickable
        role="menuitem"
        :disable="loggingIn"
        @click="login(user.id)"
      >
        <q-item-section>
          <q-item-label dir="auto">{{ user.first_name }}</q-item-label>
          <q-item-label caption>{{
            t("login.localAccountId", { id: user.id })
          }}</q-item-label>
        </q-item-section>
      </q-item>
    </q-list>
  </q-btn-dropdown>
</template>
