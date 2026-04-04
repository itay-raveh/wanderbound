<script lang="ts" setup>
defineProps<{
  name: string;
  mode: "light" | "dark";
  sizes?: string;
  alt?: string;
  loading?: "lazy" | "eager";
  fetchpriority?: "high" | "low" | "auto";
}>();

// Must match WEBP_WIDTHS in scripts/landing-screenshots.ts
const WIDTHS = [640, 1536];

function srcset(stem: string, mode: string) {
  const set = WIDTHS.map((w) => `/landing/${stem}-${mode}-${w}w.webp ${w}w`);
  set.push(`/landing/${stem}-${mode}.webp 2400w`);
  return set.join(", ");
}
</script>

<template>
  <picture>
    <source :srcset="srcset(name, mode)" :sizes="sizes ?? '320px'" type="image/webp" />
    <img
      :src="`/landing/${name}-${mode}.jpg`"
      :alt="alt ?? ''"
      :loading="loading"
      :fetchpriority="fetchpriority"
      class="landing-img"
    />
  </picture>
</template>

<style scoped>
.landing-img {
  display: block;
  width: 100%;
  aspect-ratio: var(--page-aspect);
  object-fit: cover;
}
</style>
