<script lang="ts" setup>
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { supported, notSupportedReason } from "@mapbox/mapbox-gl-supported";
import type { UploadResult } from "@/client";
import { useProcessingStream } from "@/composables/useProcessingStream";
import { useUserQuery } from "@/queries/useUserQuery";
import { CREDENTIAL_KEY } from "@/router";
import { useI18n } from "vue-i18n";
import { useMeta } from "quasar";

import RegisterHero from "@/components/register/RegisterHero.vue";

useMeta({ title: "Upload" });
import DataInstructions from "@/components/register/DataInstructions.vue";
import ZipUploader from "@/components/register/ZipUploader.vue";
import UnsupportedBanner from "@/components/register/UnsupportedBanner.vue";
import ProcessingProgress from "@/components/register/ProcessingProgress.vue";

const { t } = useI18n();
const STORAGE_KEY = "processing_upload_result";

const mapboxSupported = supported();
const mapboxReason = mapboxSupported ? null : notSupportedReason();

const router = useRouter();
const credential = sessionStorage.getItem(CREDENTIAL_KEY) ?? undefined;

// Derive upload page state from user query.
// For new users (credential present), the query will 401 - user stays undefined.
const isNewUser = !!credential;
const { user } = useUserQuery();

type UploadState = "new" | "evicted" | "reupload";
const pageState = computed<UploadState>(() => {
  if (isNewUser) return "new";
  const u = user.value;
  if (u?.album_ids?.length && !u.has_data) return "evicted";
  return "reupload";
});

const uploadResult = ref<UploadResult | null>(null);
const stream = useProcessingStream();

onMounted(() => {
  try {
    const stored = sessionStorage.getItem(STORAGE_KEY);
    if (stored) {
      uploadResult.value = JSON.parse(stored) as UploadResult;
      stream.start();
    }
  } catch {
    sessionStorage.removeItem(STORAGE_KEY);
  }
});

function onUploaded(data: UploadResult) {
  uploadResult.value = data;
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  sessionStorage.removeItem(CREDENTIAL_KEY);
  stream.start();
}

function onRetry() {
  stream.abort();
  uploadResult.value = null;
  sessionStorage.removeItem(STORAGE_KEY);
}

function onDone() {
  sessionStorage.removeItem(STORAGE_KEY);
  void router.push({ name: "editor" });
}
</script>

<template>
  <q-page class="upload-page flex flex-center no-wrap">
    <div class="upload-content">
      <RegisterHero />

      <!-- Upload view -->
      <q-card v-if="!uploadResult" class="steps-card fade-up">
        <!-- Evicted user message -->
        <template v-if="pageState === 'evicted'">
          <h3 class="state-title text-h6 text-weight-bold">{{ t("register.evictedTitle") }}</h3>
          <p class="state-body text-body2 text-muted">{{ t("register.evictedBody") }}</p>
          <q-separator class="q-my-md" />
        </template>

        <!-- Manual re-upload message -->
        <template v-else-if="pageState === 'reupload'">
          <h3 class="state-title text-h6 text-weight-bold">{{ t("register.reuploadTitle") }}</h3>
          <p class="state-body text-body2 text-muted">{{ t("register.reuploadBody") }}</p>
          <q-separator class="q-my-md" />
        </template>

        <!-- New user: full instructions -->
        <template v-else>
          <DataInstructions />
          <q-separator class="q-my-md" />
        </template>

        <ZipUploader v-if="mapboxSupported" :credential="credential" @uploaded="onUploaded" />
        <UnsupportedBanner v-else :reason="mapboxReason" />
      </q-card>

      <!-- Processing view -->
      <ProcessingProgress
        v-else
        :trips="uploadResult!.trips"
        :user="uploadResult!.user"
        :state="stream.state.value"
        :trip-index="stream.tripIndex.value"
        :phase-done="stream.phaseDone.value"
        :error-detail="stream.errorDetail.value"
        @retry="onRetry"
        @done="onDone"
      />
    </div>
  </q-page>
</template>

<style scoped>
.upload-page {
  min-height: 100%;
  background: var(--page-gradient);
}

.upload-content {
  width: 100%;
  max-width: 32rem;
}

.steps-card {
  padding: 1.75rem 2rem;
  animation-delay: 0.15s;
}

.state-title {
  margin: 0 0 var(--gap-md);
}

.state-body {
  margin: 0;
  line-height: 1.5;
}
</style>
