import { ref, watch, type Ref } from "vue";

function shallowEqual<T>(a: T[], b: T[]): boolean {
  return a.length === b.length && a.every((v, i) => v === b[i]);
}

/** Writable ref that mirrors a reactive array source (for VueDraggable v-model). */
export function useLocalCopy<T>(source: () => T[]): Ref<T[]> {
  const local = ref([...source()]) as Ref<T[]>;
  watch(source, (val) => {
    if (!shallowEqual(local.value, val)) local.value = [...val];
  });
  return local;
}
