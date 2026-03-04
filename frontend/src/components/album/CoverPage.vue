<script lang="ts" setup>
import { chooseTextDir } from "@/utils/text";
import type { Album, Step } from "@/api";
import { date } from "quasar";
import { computed } from "vue";

const { isSameDate } = date;

const props = defineProps<{
  album: Album;
  steps: Step[];
  isBack?: boolean;
}>();

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
    <q-img
      :class="{ dimmed: !isBack }"
      :src="isBack ? album.back_cover_photo : album.front_cover_photo"
      class="fit"
      fit="cover"
    />
    <div
      v-if="!isBack"
      class="absolute-top-left fit column justify-center items-center text-center q-gutter-sm"
    >
      <div class="bg-dark text-h6 q-pa-sm rounded-borders text-weight-bold">
        {{ dates }}
      </div>
      <div
        v-if="album.title"
        :dir="chooseTextDir(album.title)"
        class="text-h1 text-weight-bold"
        style="text-shadow: 0 0 5px black"
      >
        {{ album.title }}
      </div>
      <div
        v-if="album.subtitle"
        :dir="chooseTextDir(album.subtitle)"
        class="text-h5"
      >
        {{ album.subtitle }}
      </div>
    </div>
  </div>
</template>
