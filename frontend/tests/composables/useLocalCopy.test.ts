import { useLocalCopy } from "@/composables/useLocalCopy";
import { ref, nextTick } from "vue";

describe("useLocalCopy", () => {
  it("initializes with a copy of the source array", () => {
    const source = ref([1, 2, 3]);
    const local = useLocalCopy(() => source.value);
    expect(local.value).toEqual([1, 2, 3]);
  });

  it("creates a new array (not the same reference)", () => {
    const arr = [1, 2, 3];
    const source = ref(arr);
    const local = useLocalCopy(() => source.value);
    expect(local.value).not.toBe(arr);
  });

  it("syncs when source changes", async () => {
    const source = ref([1, 2, 3]);
    const local = useLocalCopy(() => source.value);

    source.value = [4, 5, 6];
    await nextTick();

    expect(local.value).toEqual([4, 5, 6]);
  });

  it("does not sync when source values are shallowly equal", async () => {
    const source = ref([1, 2, 3]);
    const local = useLocalCopy(() => source.value);

    // Mutate local independently
    local.value = [1, 2, 3]; // same values
    const afterManualSet = local.value;

    // Trigger source to a new array with same values
    source.value = [1, 2, 3];
    await nextTick();

    // shallowEqual should prevent reassignment
    expect(local.value).toBe(afterManualSet);
  });

  it("allows independent writes to local", () => {
    const source = ref(["a", "b"]);
    const local = useLocalCopy(() => source.value);

    local.value = ["x", "y", "z"];
    expect(local.value).toEqual(["x", "y", "z"]);
    // Source should not be affected
    expect(source.value).toEqual(["a", "b"]);
  });

  it("syncs when source changes to different values after local write", async () => {
    const source = ref([1, 2]);
    const local = useLocalCopy(() => source.value);

    local.value = [10, 20]; // independent write
    source.value = [3, 4]; // source changes to different values
    await nextTick();

    expect(local.value).toEqual([3, 4]);
  });

  it("handles empty arrays", async () => {
    const source = ref<number[]>([]);
    const local = useLocalCopy(() => source.value);
    expect(local.value).toEqual([]);

    source.value = [1];
    await nextTick();
    expect(local.value).toEqual([1]);

    source.value = [];
    await nextTick();
    expect(local.value).toEqual([]);
  });

  it("handles objects in arrays (shallow comparison)", async () => {
    const obj1 = { id: 1 };
    const obj2 = { id: 2 };
    const source = ref([obj1, obj2]);
    const local = useLocalCopy(() => source.value);

    expect(local.value).toEqual([obj1, obj2]);

    // Same references => shallowEqual => no sync
    const ref1 = local.value;
    source.value = [obj1, obj2];
    await nextTick();
    expect(local.value).toBe(ref1);

    // Different object (same shape but new reference) => not shallowEqual => sync
    const obj3 = { id: 1 };
    source.value = [obj3, obj2];
    await nextTick();
    expect(local.value).toEqual([obj3, obj2]);
    expect(local.value).not.toBe(ref1);
  });
});
