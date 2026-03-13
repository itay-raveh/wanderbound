<script lang="ts" setup>
import { chooseTextDir } from "@/utils/text";
import type { Album, Step } from "@/client";
import { useUserQuery } from "@/queries/useUserQuery";
import MediaItem from "./MediaItem.vue";
import { computed } from "vue";

const { formatDate } = useUserQuery();

const props = defineProps<{
  album: Album;
  steps: Step[];
  isBack?: boolean;
}>();

const coverMedia = computed(() =>
  props.isBack ? props.album.back_cover_photo : props.album.front_cover_photo,
);

const dates = computed(() => {
  const start = new Date(props.steps[0]!.datetime);
  const end = new Date(props.steps[props.steps.length - 1]!.datetime);

  const sameYear = start.getFullYear() === end.getFullYear();
  const sameMonth = sameYear && start.getMonth() === end.getMonth();

  if (sameMonth) {
    const dayStart = formatDate(start, { day: "numeric" });
    const dayEnd = formatDate(end, { day: "numeric" });
    const month = formatDate(start, { month: "long" });
    const year = formatDate(start, { year: "numeric" });
    return `${dayStart}\u2013${dayEnd} ${month} ${year}`;
  } else if (sameYear) {
    const s = formatDate(start, { month: "long", day: "numeric" });
    const e = formatDate(end, { month: "long", day: "numeric" });
    const year = formatDate(start, { year: "numeric" });
    return `${s} \u2013 ${e}, ${year}`;
  } else {
    const s = formatDate(start, { month: "long", year: "numeric" });
    const e = formatDate(end, { month: "long", year: "numeric" });
    return `${s} \u2013 ${e}`;
  }
});
</script>

<template>
  <div class="page-container cover-page relative-position">
    <MediaItem
      v-if="coverMedia"
      :media="coverMedia"
      :step-id="0"
      cover
      :class="{ 'cover-dimmed': !isBack }"
      class="fit"
    />
    <div
      v-if="!isBack"
      class="cover-overlay fit absolute-top-left"
    >
      <div class="cover-content column justify-center items-center text-center fit">
        <div class="cover-date">{{ dates }}</div>
        <div
          v-if="album.title"
          :dir="chooseTextDir(album.title)"
          class="cover-title"
        >
          {{ album.title }}
        </div>
        <div
          v-if="album.subtitle"
          :dir="chooseTextDir(album.subtitle)"
          class="cover-subtitle"
        >
          {{ album.subtitle }}
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
// Only the front cover gets dimmed (not the back)
.cover-dimmed {
  filter: brightness(0.6);
}

.cover-overlay {
  z-index: 1;
}

.cover-content {
  gap: 0.75rem;
  padding: 2rem;
}

.cover-date {
  font-size: 0.9rem;
  font-weight: 700;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.92);
  text-shadow:
    0 1px 8px rgba(0, 0, 0, 0.8),
    0 0 24px rgba(0, 0, 0, 0.4);
}

.cover-title {
  font-size: 3.5rem;
  font-weight: 700;
  line-height: 1.1;
  letter-spacing: -0.02em;
  color: white;
  text-shadow:
    0 2px 20px rgba(0, 0, 0, 0.8),
    0 1px 6px rgba(0, 0, 0, 0.5),
    0 0 60px rgba(0, 0, 0, 0.3);
  max-width: 80%;
}

.cover-subtitle {
  font-size: 1.25rem;
  font-weight: 400;
  letter-spacing: 0.02em;
  color: rgba(255, 255, 255, 0.88);
  text-shadow:
    0 1px 10px rgba(0, 0, 0, 0.8),
    0 0 30px rgba(0, 0, 0, 0.4);
  max-width: 70%;
}
</style>
