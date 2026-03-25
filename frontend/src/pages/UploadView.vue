<script lang="ts" setup>
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { supported, notSupportedReason } from "@mapbox/mapbox-gl-supported";
import type { UploadResult } from "@/client";
import { useProcessingStream } from "@/composables/useProcessingStream";
import { useUserQuery } from "@/queries/useUserQuery";
import { getAuthState, clearAuthState as clearAuth } from "@/router";
import { useI18n } from "vue-i18n";
import { useMeta } from "quasar";
import RegisterHero from "@/components/register/RegisterHero.vue";
import DataInstructions from "@/components/register/DataInstructions.vue";
import ZipUploader from "@/components/register/ZipUploader.vue";
import UnsupportedBanner from "@/components/register/UnsupportedBanner.vue";
import ProcessingProgress from "@/components/register/ProcessingProgress.vue";

useMeta({ title: "Upload" });

const { t } = useI18n();
const STORAGE_KEY = "processing_upload_result";

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

const uploadResult = ref<UploadResult | null>(null);
const stream = useProcessingStream();

const heroName = computed(() =>
  uploadResult.value?.user.first_name ?? user.value?.first_name,
);

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
  clearAuth();
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
      <RegisterHero :user-name="heroName" />

      <!-- Upload view -->
      <q-card v-if="!uploadResult" class="upload-card fade-up">
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

        <!-- New user: collapsible instructions -->
        <template v-else>
          <q-expansion-item
            :label="t('register.getDataTitle')"
            default-opened
            dense
            :duration="200"
            header-class="data-instructions-header text-weight-semibold text-bright"
            class="data-instructions"
          >
            <DataInstructions />
          </q-expansion-item>
          <q-separator class="q-my-md" />
        </template>

        <ZipUploader v-if="mapboxSupported" :credential="credential" :provider="provider" @uploaded="onUploaded" />
        <UnsupportedBanner v-else :reason="mapboxReason" />
      </q-card>

      <!-- Processing view -->
      <ProcessingProgress
        v-else
        class="upload-card"
        :trips="uploadResult!.trips"
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
  padding: var(--gap-lg);
  background: var(--page-gradient);
  position: relative;
  overflow: hidden;
}

.upload-page::before {
  content: "";
  position: absolute;
  inset: -20%;
  opacity: 0.35;
  background:
    radial-gradient(ellipse 60% 50% at var(--aurora-x1) 20%, var(--q-primary), transparent 70%),
    radial-gradient(ellipse 50% 45% at var(--aurora-x2) 80%, var(--aurora-accent), transparent 70%);
  animation: aurora 20s ease-in-out infinite alternate;
  pointer-events: none;
  filter: blur(60px);
}

@keyframes aurora {
  to {
    --aurora-x1: 60%;
    --aurora-x2: 40%;
  }
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

.data-instructions {
  margin: -0.5rem -1rem;
  border-radius: var(--radius-md);
}

.data-instructions :deep(.q-expansion-item__content) {
  padding: 0 1rem var(--gap-md);
}

.data-instructions :deep(.data-instructions-header) {
  padding: var(--gap-md) 1rem;
  min-height: unset;
  font-size: var(--type-md);
}

@media (prefers-reduced-motion: reduce) {
  .upload-page::before {
    animation: none;
  }
}
</style>

<style>
@property --aurora-accent {
  syntax: "<color>";
  inherits: false;
  initial-value: #818cf8;
}

@property --aurora-x1 {
  syntax: "<percentage>";
  inherits: false;
  initial-value: 20%;
}

@property --aurora-x2 {
  syntax: "<percentage>";
  inherits: false;
  initial-value: 80%;
}
</style>
