<script lang="ts" setup>
import { chooseTextDir } from "@/utils/text";
import type { Album, Step } from "@/client";
import MediaItem from "./MediaItem.vue";
import { date } from "quasar";
import { computed } from "vue";

const { isSameDate } = date;

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

  if (isSameDate(start, end, "year")) {
    if (isSameDate(start, end, "month")) {
      return `${start.getDate()}-${end.getDate()} ${start.toLocaleDateString("default", { month: "long" })}`;
    } else {
      return `${start.toLocaleDateString("default", {
        month: "long",
        day: "numeric",
      })} - ${end.toLocaleDateString("default", {
        month: "long",
        day: "numeric",
      })} ${start.toLocaleDateString("default", { year: "numeric" })}`;
    }
  } else {
    return `${start.toLocaleDateString("default", {
      month: "long",
      year: "numeric",
    })} - ${end.toLocaleDateString("default", {
      month: "long",
      year: "numeric",
    })}`;
  }
});
</script>

<template>
  <div class="page-container relative-position">
    <MediaItem
      v-if="coverMedia"
      :media="coverMedia"
      :album-id="album.id"
      :step-id="0"
      :class="{ dimmed: !isBack }"
      class="fit"
    />
    <div
      v-if="!isBack"
      class="absolute-top-left fit column justify-center items-center text-center q-gutter-sm"
    >
      <div class="cover-date-badge text-h6 q-pa-sm rounded-borders text-weight-bold">
        {{ dates }}
      </div>
      <div
        v-if="album.title"
        :dir="chooseTextDir(album.title)"
        class="text-h1 text-weight-bold cover-title-shadow"
      >
        {{ album.title }}
      </div>
      <div
        v-if="album.subtitle"
        :dir="chooseTextDir(album.subtitle)"
        class="text-h5 cover-title-shadow"
      >
        {{ album.subtitle }}
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.cover-date-badge {
  background: var(--bg-deep);
  color: var(--text-bright);
}

.cover-title-shadow {
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.6);
  color: white;
}
</style>
