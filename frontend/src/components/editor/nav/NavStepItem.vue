<script lang="ts" setup>
import { computed, ref, watchEffect } from "vue";
import { useI18n } from "vue-i18n";
import {
  symOutlinedVisibility,
  symOutlinedVisibilityOff,
} from "@quasar/extras/material-symbols-outlined";
import { useActiveSection } from "@/composables/useActiveSection";
import { useElementVisibility } from "@vueuse/core";

const { t } = useI18n();

const props = defineProps<{
  name: string;
  date: string;
  thumb: string | null;
  color: string;
  active: boolean;
  hidden: boolean;
  lazyRoot?: HTMLElement | null;
}>();

defineEmits<{
  click: [];
  toggle: [];
}>();

const thumbRef = ref<HTMLElement | null>(null);
const thumbVisible = useElementVisibility(thumbRef, {
  scrollTarget: computed(() => props.lazyRoot ?? null),
  rootMargin: "0px",
  once: true,
  initialValue:
    typeof window !== "undefined" && !("IntersectionObserver" in window),
});
const { programmaticScrolling } = useActiveSection();
const loadThumb = ref(false);
watchEffect(() => {
  if (thumbVisible.value && !programmaticScrolling.value) {
    loadThumb.value = true;
  }
});
</script>

<template>
  <div
    role="button"
    tabindex="0"
    :class="['nav-item', { visible: active, 'nav-hidden': hidden }]"
    :aria-current="active ? 'step' : undefined"
    @click="$emit('click')"
    @keydown.enter="$emit('click')"
  >
    <div ref="thumbRef" class="item-thumb">
      <img
        v-if="thumb"
        :src="loadThumb ? thumb : undefined"
        alt=""
        width="36"
        height="28"
        class="thumb-img"
        loading="lazy"
      />
      <div v-else class="thumb-empty" :style="{ background: color }" />
    </div>
    <div class="item-info">
      <span class="item-name" dir="auto">{{ name }}</span>
      <span class="item-date text-muted">{{ date }}</span>
    </div>
    <button
      type="button"
      class="step-toggle"
      :aria-label="hidden ? t('nav.showStep') : t('nav.hideStep')"
      @click.stop="$emit('toggle')"
    >
      <q-icon
        :name="hidden ? symOutlinedVisibilityOff : symOutlinedVisibility"
        size="var(--type-xs)"
      />
    </button>
  </div>
</template>

<style lang="scss" scoped>
@use "nav-item";
@use "nav-toggle" as *;

.thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb-empty {
  width: 100%;
  height: 100%;
  opacity: var(--opacity-thumb-empty);
}

.item-date {
  font-size: var(--type-xs);
}

.step-toggle {
  @include nav-toggle;

  .nav-item:hover & {
    opacity: 1;
  }

  .nav-item.nav-hidden & {
    opacity: 1;
  }
}
</style>
