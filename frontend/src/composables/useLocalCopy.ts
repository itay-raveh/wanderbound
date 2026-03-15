import { ref, watch, type Ref } from "vue";

/** Reactive local copy of an array prop, kept in sync via shallow comparison.
 *  Needed for VueDraggable v-model, which requires a writable ref. */
export function useLocalCopy<T>(source: () => T[]): Ref<T[]> {
  const local = ref([...source()]) as Ref<T[]>;
  watch(source, (val) => {
    if (
      val.length === local.value.length &&
      val.every((v, i) => v === local.value[i])
    )
      return;
    local.value = [...val];
  });
  return local;
}
