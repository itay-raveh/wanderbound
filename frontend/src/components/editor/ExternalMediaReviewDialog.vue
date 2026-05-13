<script lang="ts" setup>
import type { ReplacementReviewState } from "@/composables/useReplaceExternalMedia";
import { computed } from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();

const props = defineProps<{
  modelValue: boolean;
  review: ReplacementReviewState | null;
  replacing?: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  confirm: [];
}>();

const hasWarnings = computed(() => (props.review?.warnings.length ?? 0) > 0);
</script>

<template>
  <q-dialog
    :model-value="modelValue"
    persistent
    @update:model-value="(value) => emit('update:modelValue', value)"
  >
    <q-card v-if="review" class="review-dialog">
      <q-card-section class="review-header">
        <div class="text-h6">{{ t("externalMedia.review.title") }}</div>
        <div class="review-subtitle">
          {{ t("externalMedia.review.body") }}
        </div>
      </q-card-section>

      <q-card-section class="review-grid">
        <div class="preview-panel">
          <div class="preview-label">
            {{ t("externalMedia.review.current") }}
          </div>
          <img :src="review.current.previewUrl" alt="" class="preview-media" />
          <div class="preview-meta">
            {{ review.current.width }} × {{ review.current.height }}
          </div>
        </div>

        <div class="preview-panel">
          <div class="preview-label">
            {{ t("externalMedia.review.replacement") }}
          </div>
          <img
            v-if="review.replacement.kind === 'photo'"
            :src="review.replacement.previewUrl"
            alt=""
            class="preview-media"
          />
          <video
            v-else
            :src="review.replacement.previewUrl"
            class="preview-media"
            muted
            playsinline
            preload="metadata"
          />
          <div class="preview-meta">
            {{ review.replacement.width }} × {{ review.replacement.height }}
          </div>
        </div>
      </q-card-section>

      <q-card-section
        v-if="hasWarnings || review.blockedReason"
        class="review-alerts"
      >
        <div v-if="review.blockedReason" class="alert alert-error">
          {{ review.blockedReason }}
        </div>
        <div
          v-for="warning in review.warnings"
          :key="warning"
          class="alert alert-warning"
        >
          {{ warning }}
        </div>
      </q-card-section>

      <q-card-actions align="right">
        <q-btn
          flat
          no-caps
          :label="t('common.cancel')"
          @click="emit('update:modelValue', false)"
        />
        <q-btn
          color="primary"
          no-caps
          :disable="Boolean(review.blockedReason) || replacing"
          :loading="replacing"
          :label="t('externalMedia.review.confirm')"
          @click="emit('confirm')"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<style lang="scss" scoped>
.review-dialog {
  width: min(44rem, 92vw);
  border-radius: var(--radius-md);
}

.review-header {
  display: grid;
  gap: var(--gap-sm);
}

.review-subtitle {
  color: var(--text-muted);
  line-height: 1.5;
}

.review-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--gap-md-lg);
}

.preview-panel {
  display: grid;
  gap: var(--gap-sm);
}

.preview-label {
  font-size: var(--type-xs);
  font-weight: 700;
  letter-spacing: var(--tracking-wide);
  text-transform: uppercase;
  color: var(--text-muted);
}

.preview-media {
  width: 100%;
  aspect-ratio: 4 / 3;
  object-fit: cover;
  border-radius: var(--radius-sm);
  background: var(--bg-secondary);
}

.preview-meta {
  color: var(--text-muted);
  font-size: var(--type-sm);
}

.review-alerts {
  display: grid;
  gap: var(--gap-sm);
}

.alert {
  padding: var(--gap-sm) var(--gap-md);
  border-radius: var(--radius-sm);
  font-size: var(--type-sm);
  line-height: 1.5;
}

.alert-warning {
  background: color-mix(in srgb, var(--q-warning) 12%, transparent);
  color: color-mix(in srgb, var(--q-warning) 70%, var(--text));
}

.alert-error {
  background: color-mix(in srgb, var(--q-negative) 12%, transparent);
  color: color-mix(in srgb, var(--q-negative) 70%, var(--text));
}

@media (max-width: 720px) {
  .review-grid {
    grid-template-columns: 1fr;
  }
}
</style>
