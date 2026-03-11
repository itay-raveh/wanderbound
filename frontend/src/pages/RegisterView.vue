<script lang="ts" setup>
import { supported, notSupportedReason } from "@mapbox/mapbox-gl-supported";
import RegisterHero from "@/components/register/RegisterHero.vue";
import DataInstructions from "@/components/register/DataInstructions.vue";
import ZipUploader from "@/components/register/ZipUploader.vue";
import UnsupportedBanner from "@/components/register/UnsupportedBanner.vue";

const mapboxSupported = supported();
const mapboxReason = mapboxSupported ? null : notSupportedReason();
</script>

<template>
  <q-page class="register-page">
    <div class="register-content">
      <RegisterHero />
      <div class="steps-card">
        <DataInstructions />
        <div class="steps-divider" />
        <ZipUploader v-if="mapboxSupported" />
        <UnsupportedBanner v-else :reason="mapboxReason" />
      </div>
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
  border-radius: 1rem;
  padding: 1.75rem 2rem;
  animation: fadeUp 0.5s ease both;
  animation-delay: 0.15s;
}

.steps-divider {
  height: 1px;
  background: var(--border-color);
  margin: 1.5rem 0;
}

@keyframes fadeUp {
  from {
    opacity: 0;
    transform: translateY(0.75rem);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
