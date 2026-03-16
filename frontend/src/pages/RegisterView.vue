<script lang="ts" setup>
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { supported, notSupportedReason } from "@mapbox/mapbox-gl-supported";
import type { UserCreated } from "@/client/types.gen";
import { useProcessingStream } from "@/composables/useProcessingStream";

import RegisterHero from "@/components/register/RegisterHero.vue";
import DataInstructions from "@/components/register/DataInstructions.vue";
import ZipUploader from "@/components/register/ZipUploader.vue";
import UnsupportedBanner from "@/components/register/UnsupportedBanner.vue";
import ProcessingProgress from "@/components/register/ProcessingProgress.vue";

const STORAGE_KEY = "processing_upload_result";

const mapboxSupported = supported();
const mapboxReason = mapboxSupported ? null : notSupportedReason();

const router = useRouter();

const uploadResult = ref<UserCreated | null>(null);

const stream = useProcessingStream();

onMounted(() => {
  try {
    const stored = sessionStorage.getItem(STORAGE_KEY);
    if (stored) {
      uploadResult.value = JSON.parse(stored) as UserCreated;
      stream.start();
    }
  } catch {
    sessionStorage.removeItem(STORAGE_KEY);
  }
});

function onUploaded(data: UserCreated) {
  uploadResult.value = data;
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  stream.start();
}

function onRetry() {
  stream.abort();
  uploadResult.value = null;
  sessionStorage.removeItem(STORAGE_KEY);
}

function onDone() {
  sessionStorage.removeItem(STORAGE_KEY);
  void router.push("/");
}
</script>

<template>
  <div class="register-page flex flex-center">
    <div class="register-content">
      <RegisterHero />

      <!-- Upload view -->
      <q-card v-if="!uploadResult" class="steps-card fade-up">
        <DataInstructions />
        <q-separator class="q-my-md" />
        <ZipUploader v-if="mapboxSupported" @uploaded="onUploaded" />
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
  </div>
</template>

<style scoped>
.register-page {
  min-height: 100vh;
  background: linear-gradient(
    to bottom,
    color-mix(in srgb, var(--q-primary) 8%, var(--bg-deep)),
    var(--bg)
  );
}

.register-content {
  width: 100%;
  max-width: 32rem;
}

.steps-card {
  padding: 1.75rem 2rem;
  animation-delay: var(--duration-fast);
}

</style>
