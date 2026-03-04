<script lang="ts" setup>
defineProps<{
  countries: [string, string][];
}>();
</script>

<template>
  <div class="bg-accent column justify-around q-pa-xl">
    <div v-for="[code, name] in countries" :key="code">
      <div class="row items-center">
        <q-img
          :alt="name"
          :src="`https://flagcdn.com/${code.toLowerCase()}.svg`"
          class="rounded-borders on-left"
          width="3rem"
        />
        <div class="text-h4 text-weight-bold">{{ name }}</div>
      </div>
    </div>
  </div>
</template>
