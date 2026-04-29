<script lang="ts" setup>
import { computed, ref } from "vue";
import { useElementVisibility } from "@vueuse/core";

const props = defineProps<{
  src: string;
  selected: boolean;
  label: string;
  lazyRoot?: HTMLElement | null;
}>();

defineEmits<{ select: [] }>();

const root = ref<HTMLElement | null>(null);
const visible = useElementVisibility(root, {
  scrollTarget: computed(() => props.lazyRoot ?? null),
  rootMargin: "300px",
  once: true,
  initialValue:
    typeof window !== "undefined" && !("IntersectionObserver" in window),
});
</script>

<template>
  <img
    ref="root"
    :src="visible ? src : undefined"
    class="cover-cell"
    :class="{ selected }"
    :aria-label="label"
    role="button"
    tabindex="0"
    alt=""
    @click="$emit('select')"
    @keydown.enter="$emit('select')"
    @keydown.space.prevent="$emit('select')"
  />
</template>
