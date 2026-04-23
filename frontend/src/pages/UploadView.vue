<script lang="ts" setup>
import { computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useSessionStorage } from "@vueuse/core";
import { supported, notSupportedReason } from "@mapbox/mapbox-gl-supported";
import type { UploadResult } from "@/client";
import { useTripProcessingStream } from "@/composables/useTripProcessingStream";
import { useUserQuery } from "@/queries/useUserQuery";
import { getAuthState, clearAuthState as clearAuth } from "@/router";
import { useI18n } from "vue-i18n";
import { useMeta } from "quasar";
import RegisterHero from "@/components/register/RegisterHero.vue";
import DataInstructions from "@/components/register/DataInstructions.vue";
import ZipUploader from "@/components/register/ZipUploader.vue";
import UnsupportedBanner from "@/components/register/UnsupportedBanner.vue";
import ProcessingProgress from "@/components/register/ProcessingProgress.vue";
import { UPLOAD_RESULT_KEY } from "@/utils/storage-keys";

useMeta({ title: "Upload" });

const { t } = useI18n();

const mapboxSupported = supported();
const mapboxReason = mapboxSupported ? null : notSupportedReason();

const router = useRouter();
const authState = getAuthState();
const credential = authState?.credential;
const provider = authState?.provider;

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

const uploadResult = useSessionStorage<UploadResult | null>(
  UPLOAD_RESULT_KEY,
  null,
);
const stream = useTripProcessingStream();

const heroName = computed(
  () => uploadResult.value?.user?.first_name ?? user.value?.first_name,
);

onMounted(() => {
  if (uploadResult.value?.trips) stream.start();
  else if (uploadResult.value) uploadResult.value = null;
});

function onUploaded(data: UploadResult) {
  uploadResult.value = data;
  clearAuth();
  stream.start();
}

function onRetry() {
  stream.start();
}

function onReupload() {
  stream.abort();
  uploadResult.value = null;
}

function onDone() {
  uploadResult.value = null;
  void router.push({ name: "editor" });
}
</script>

<template>
  <q-page class="upload-page flex flex-center no-wrap">
    <div class="upload-content">
      <RegisterHero :user-name="heroName" />

      <!-- Upload view -->
      <q-card v-if="!uploadResult" class="upload-card fade-up">
        <!-- Evicted user message -->
        <template v-if="pageState === 'evicted'">
          <h2 class="state-title text-h6 text-weight-bold">
            {{ t("register.evictedTitle") }}
          </h2>
          <p class="state-body text-body2 text-muted">
            {{ t("register.evictedBody") }}
          </p>
          <q-separator class="q-my-md" />
        </template>

        <!-- Manual re-upload message -->
        <template v-else-if="pageState === 'reupload'">
          <h2 class="state-title text-h6 text-weight-bold">
            {{ t("register.reuploadTitle") }}
          </h2>
          <p class="state-body text-body2 text-muted">
            {{ t("register.reuploadBody") }}
          </p>
          <q-separator class="q-my-md" />
        </template>

        <!-- New user: instructions -->
        <template v-else>
          <h2 class="state-title text-h6 text-weight-bold">
            {{ t("register.getDataTitle") }}
          </h2>
          <DataInstructions />
          <q-separator class="q-my-md" />
        </template>

        <ZipUploader
          v-if="mapboxSupported"
          :credential="credential"
          :provider="provider"
          @uploaded="onUploaded"
        />
        <UnsupportedBanner v-else :reason="mapboxReason" />
      </q-card>

      <!-- Processing view -->
      <ProcessingProgress
        v-else-if="uploadResult.trips"
        class="upload-card"
        :trips="uploadResult.trips"
        :state="stream.state.value"
        :trip-index="stream.tripIndex.value"
        :phase-done="stream.phaseDone.value"
        :error-detail="stream.errorDetail.value"
        @retry="onRetry"
        @reupload="onReupload"
        @done="onDone"
      />
    </div>
  </q-page>
</template>

<style scoped>
.upload-page {
  min-height: 100%;
  padding: var(--gap-lg);
  background: var(--page-gradient);
  position: relative;
  overflow: hidden;
}

.upload-page::before {
  content: "";
  position: absolute;
  inset: -10%;
  pointer-events: none;
  opacity: 0.09;
  background: url("/topo-contours.svg") center / cover no-repeat;
}

.upload-content {
  width: 100%;
  max-width: 32rem;
  position: relative;
}

.upload-card {
  padding: 1.75rem 2rem;
}

@media (max-width: 479px) {
  .upload-card {
    padding: 1.25rem;
  }
}

.state-title {
  margin: 0 0 var(--gap-md);
}

.state-body {
  margin: 0;
  line-height: 1.5;
}
</style>
