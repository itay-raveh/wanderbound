<script lang="ts" setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { supported, notSupportedReason } from "@mapbox/mapbox-gl-supported";
import type { UserCreated } from "@/client/types.gen";
import { useProcessingStream } from "@/composables/useProcessingStream";

import RegisterHero from "@/components/register/RegisterHero.vue";
import DataInstructions from "@/components/register/DataInstructions.vue";
import ZipUploader from "@/components/register/ZipUploader.vue";
import UnsupportedBanner from "@/components/register/UnsupportedBanner.vue";
import ProcessingProgress from "@/components/register/ProcessingProgress.vue";

const mapboxSupported = supported();
const mapboxReason = mapboxSupported ? null : notSupportedReason();

const router = useRouter();

const uploadResult = ref<UserCreated | null>(null);

const stream = useProcessingStream();

function onUploaded(data: UserCreated) {
  uploadResult.value = data;
  stream.start();
}

function onRetry() {
  stream.abort();
  uploadResult.value = null;
}

function onDone() {
  void router.push("/");
}
</script>

<template>
  <q-page class="register-page">
    <div class="register-content">
      <RegisterHero />

      <!-- Upload view -->
      <div v-if="!uploadResult" class="steps-card">
        <DataInstructions />
        <div class="steps-divider" />
        <ZipUploader v-if="mapboxSupported" @uploaded="onUploaded" />
        <UnsupportedBanner v-else :reason="mapboxReason" />
      </div>

      <!-- Processing view -->
      <ProcessingProgress
        v-else
        :trips="uploadResult!.trips"
        :user="uploadResult!.user"
        :state="stream.state.value"
        :trip-index="stream.tripIndex.value"
        :phase="stream.phase.value"
        :phase-done="stream.phaseDone.value"
        :error-detail="stream.errorDetail.value"
        @retry="onRetry"
        @done="onDone"
      />
    </div>
  </q-page>
</template>

<style scoped>
.register-page {
  background: linear-gradient(
    to bottom,
    color-mix(in srgb, var(--q-primary) 8%, var(--bg-deep)),
    var(--bg)
  );
  display: flex;
  align-items: center;
  justify-content: center;
}

.register-content {
  width: 100%;
  max-width: 32rem;
}

.steps-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: 1.75rem 2rem;
  animation: fadeUp 0.5s ease both;
  animation-delay: 0.15s;
}

.steps-divider {
  height: 1px;
  background: var(--border-color);
  margin: 1.5rem 0;
}
</style>
