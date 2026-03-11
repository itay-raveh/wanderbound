<script lang="ts" setup>
import { ref, watch } from "vue";
import { VueDraggable } from "vue-draggable-plus";
import MediaItem from "../MediaItem.vue";

const props = defineProps<{
  assets: Array<string>;
  stepId: number;
  albumName: string;
}>();

const emit = defineEmits<{
  "update:unused-photos": [unused: string[]];
}>();

const localUnused = ref([...props.assets]);

watch(
  () => props.assets,
  (val) => {
    localUnused.value = [...val];
  },
);

function onDragChange() {
  emit("update:unused-photos", [...localUnused.value]);
}
</script>

<template>
  <div class="wrapper">
    <div class="header">Unused Photos</div>
    <VueDraggable
      v-model="localUnused"
      class="container"
      group="photos"
      :animation="200"
      @change="onDragChange"
    >
      <MediaItem
        v-for="photo in localUnused"
        :key="photo"
        :album-id="albumName"
        :media="photo"
        :step-id="stepId"
        class="photo-item"
      />
    </VueDraggable>
  </div>
</template>

<style lang="scss" scoped>
.wrapper {
  width: 20%;
  height: 100%;

  position: sticky;
  right: 0;
  top: 5rem;
  margin-top: 5rem;
  margin-bottom: 10rem;

  border-radius: 10px;
  background: var(--bg-secondary);
  box-shadow: 0 -5px 15px rgba(0, 0, 0, 0.2);

  display: flex;
  flex-direction: column;
}

.header {
  padding: 1rem;
  text-align: center;
  font-weight: bold;
  font-size: 1.25rem;
  color: var(--text-muted);
}

.container {
  padding: 1rem 0;
  overflow-y: auto;
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  min-height: 100px;

  .photo-item {
    width: 90%;
    height: auto;
  }
}

@media print {
  .wrapper {
    display: none !important;
  }
}
</style>
