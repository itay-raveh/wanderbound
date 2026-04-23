<script lang="ts" setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useQueryCache } from "@pinia/colada";
import { supported, notSupportedReason } from "@mapbox/mapbox-gl-supported";
import type { UploadResult } from "@/client";
import { useTripProcessingStream } from "@/composables/useTripProcessingStream";
import { useUserQuery } from "@/queries/useUserQuery";
import { useAuthStateQuery } from "@/queries/useAuthStateQuery";
import { queryKeys } from "@/queries/keys";
import { useI18n } from "vue-i18n";
import { useMeta } from "quasar";
import RegisterHero from "@/components/register/RegisterHero.vue";
import DataInstructions from "@/components/register/DataInstructions.vue";
import ZipUploader from "@/components/register/ZipUploader.vue";
import UnsupportedBanner from "@/components/register/UnsupportedBanner.vue";
import ProcessingProgress from "@/components/register/ProcessingProgress.vue";

useMeta({ title: "Upload" });

const { t } = useI18n();

const mapboxSupported = supported();
const mapboxReason = mapboxSupported ? null : notSupportedReason();

const router = useRouter();
const cache = useQueryCache();

const { data: authStateData } = useAuthStateQuery();
const { user } = useUserQuery();
const stream = useTripProcessingStream();
const handoff = (history.state ?? {}) as { uploadResult?: UploadResult };
const justUploaded = ref<UploadResult | null>(handoff.uploadResult ?? null);

type UploadState = "new" | "evicted" | "reupload" | "processing";
const pageState = computed<UploadState>(() => {
  if (justUploaded.value || stream.state.value === "running")
    return "processing";
  if (authStateData.value?.state === "pending_signup") return "new";
  const u = user.value;
  if (!u) return "new";
  if (!u.has_data) return u.album_ids?.length ? "evicted" : "new";
  if (!u.is_processed) return "processing";
  return "reupload";
});

const trips = computed(() => justUploaded.value?.trips ?? []);

const heroName = computed(
  () =>
    justUploaded.value?.user?.first_name ??
    user.value?.first_name ??
    authStateData.value?.first_name ??
    undefined,
);

const isReturning = computed(() => !!user.value);

function startProcessing() {
  if (stream.state.value === "running") return;
  stream.start();
}

onMounted(() => {
  if (pageState.value === "processing") startProcessing();
});

watch(pageState, (s) => {
  if (s === "processing") startProcessing();
});

function onUploaded(data: UploadResult) {
  justUploaded.value = data;
  void cache.invalidateQueries({ key: queryKeys.authState() });
  void cache.invalidateQueries({ key: queryKeys.user() });
  startProcessing();
}

function onRetry() {
  stream.start();
}

function onReupload() {
  stream.abort();
  justUploaded.value = null;
}

function onDone() {
  void router.push({ name: "editor" });
}
</script>

<template>
  <q-page class="upload-page flex flex-center no-wrap">
    <div class="upload-content">
      <RegisterHero :user-name="heroName" :is-returning="isReturning" />

      <q-card v-if="pageState !== 'processing'" class="upload-card fade-up">
        <template v-if="pageState === 'evicted'">
          <h2 class="state-title text-h6 text-weight-bold">
            {{ t("register.evictedTitle") }}
          </h2>
          <p class="state-body text-body2 text-muted">
            {{ t("register.evictedBody") }}
          </p>
          <q-separator class="q-my-md" />
        </template>

        <template v-else-if="pageState === 'reupload'">
          <h2 class="state-title text-h6 text-weight-bold">
            {{ t("register.reuploadTitle") }}
          </h2>
          <p class="state-body text-body2 text-muted">
            {{ t("register.reuploadBody") }}
          </p>
          <q-separator class="q-my-md" />
        </template>

        <template v-else-if="pageState === 'new'">
          <h2 class="state-title text-h6 text-weight-bold">
            {{ t("register.getDataTitle") }}
          </h2>
          <DataInstructions />
          <q-separator class="q-my-md" />
        </template>

        <ZipUploader
          v-if="mapboxSupported"
          @uploaded="onUploaded"
        />
        <UnsupportedBanner v-else :reason="mapboxReason" />
      </q-card>

      <ProcessingProgress
        v-else
        class="upload-card"
        :trips="trips"
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
