import { createApp, defineComponent, h, ref, type Ref } from "vue";
import type { StepRead as Step, StepUpdate } from "@/client";
import { provideStepMutate, useStepLayout } from "@/composables/useStepLayout";
import { makeStep } from "../helpers";

vi.mock("vue-draggable-plus", () => ({
  useDraggable: vi.fn(),
}));

interface LayoutResult {
  saveField: (patch: Partial<StepUpdate>) => void;
  onPageUpdate: (idx: number, page: string[]) => void;
  onCoverUpdate: (cover: string) => void;
  printMode: boolean;
}

function mountStepLayout(step: Step) {
  const stepRef = ref(step);
  const mutateSpy =
    vi.fn<(payload: { sid: number; update: StepUpdate }) => void>();
  let result!: LayoutResult;

  const Child = defineComponent({
    setup() {
      const dropZoneRef = ref(null);
      const coverDropRef = ref(null);
      result = useStepLayout(stepRef as Ref<Step>, {
        dropZoneRef,
        coverDropRef,
      });
      return () => null;
    },
  });

  const Parent = defineComponent({
    setup() {
      provideStepMutate(mutateSpy);
      return () => h(Child);
    },
  });

  const app = createApp(Parent);
  app.mount(document.createElement("div"));

  onTestFinished(() => {
    app.unmount();
  });

  return { result, mutateSpy, stepRef };
}

function lastUpdate(mutateSpy: ReturnType<typeof mountStepLayout>["mutateSpy"]) {
  expect(mutateSpy).toHaveBeenCalledOnce();
  return mutateSpy.mock.calls[0][0].update;
}

describe("onCoverUpdate", () => {
  it.each([
    [
      { cover: null, pages: [["p1", "p2"], ["p3"]], unused: [] },
      "p2",
      { cover: "p2", pages: [["p1"], ["p3"]], unused: [] },
    ],
    [
      { cover: "old_cover", pages: [["p1", "new_cover"]], unused: ["u1"] },
      "new_cover",
      { cover: "new_cover", pages: [["p1"]], unused: ["u1", "old_cover"] },
    ],
    [
      { cover: null, pages: [], unused: ["u1", "new_cover", "u2"] },
      "new_cover",
      { cover: "new_cover", unused: ["u1", "u2"] },
    ],
  ])("updates cover placement", (stepPatch, cover, expected) => {
    const { result, mutateSpy } = mountStepLayout(makeStep({ id: 1, ...stepPatch }));

    result.onCoverUpdate(cover);

    expect(lastUpdate(mutateSpy)).toMatchObject(expected);
  });
});

describe("onPageUpdate", () => {
  it.each([
    [
      { pages: [["a", "b"], ["c", "d"]], unused: [] },
      ["a", "b", "c"],
      { pages: [["a", "b", "c"], ["d"]], unused: [] },
    ],
    [
      { pages: [["a"]], unused: ["u1", "u2"] },
      ["a", "u1"],
      { pages: [["a", "u1"]], unused: ["u2"] },
    ],
    [
      { pages: [["a"], ["b"]], unused: [] },
      ["a", "b"],
      { pages: [["a", "b"]] },
    ],
  ])("updates page placement", (stepPatch, page, expected) => {
    const { result, mutateSpy } = mountStepLayout(makeStep({ id: 1, ...stepPatch }));

    result.onPageUpdate(0, page);

    expect(lastUpdate(mutateSpy)).toMatchObject(expected);
  });
});
