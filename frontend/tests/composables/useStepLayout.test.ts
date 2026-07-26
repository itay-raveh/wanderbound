import { ref, type Ref } from "vue";
import type { StepRead as Step, StepUpdate } from "@/client";
import { provideStepMutate, useStepLayout } from "@/composables/useStepLayout";
import { makeStep, withParentSetup } from "../helpers";

vi.mock("vue-draggable-plus", () => ({
  useDraggable: vi.fn(),
}));

function mountStepLayout(step: Step) {
  const stepRef = ref(step);
  const mutateSpy =
    vi.fn<(payload: { sid: number; update: StepUpdate }) => void>();
  const { result } = withParentSetup(
    () => {
      provideStepMutate(mutateSpy);
    },
    () => {
      const dropZoneRef = ref(null);
      const coverDropRef = ref(null);
      return useStepLayout(stepRef as Ref<Step>, {
        dropZoneRef,
        coverDropRef,
      });
    },
    { plugins: false },
  );

  return { result, mutateSpy, stepRef };
}

function lastUpdate(
  mutateSpy: ReturnType<typeof mountStepLayout>["mutateSpy"],
) {
  expect(mutateSpy).toHaveBeenCalledOnce();
  return mutateSpy.mock.calls[0][0].update;
}

describe("onCoverUpdate", () => {
  it.each([
    [
      {
        cover: null,
        pages: [
          { kind: "grid" as const, media: ["p1", "p2"] },
          { kind: "grid" as const, media: ["p3"] },
        ],
        unused: [],
      },
      "p2",
      {
        cover: "p2",
        pages: [
          { kind: "grid", media: ["p1"] },
          { kind: "grid", media: ["p3"] },
        ],
        unused: [],
      },
    ],
    [
      {
        cover: "old_cover",
        pages: [
          { kind: "grid" as const, media: ["p1", "new_cover"] },
        ],
        unused: ["u1"],
      },
      "new_cover",
      {
        cover: "new_cover",
        pages: [{ kind: "grid", media: ["p1"] }],
        unused: ["u1", "old_cover"],
      },
    ],
    [
      { cover: null, pages: [], unused: ["u1", "new_cover", "u2"] },
      "new_cover",
      { cover: "new_cover", unused: ["u1", "u2"] },
    ],
  ])("updates cover placement", (stepPatch, cover, expected) => {
    const { result, mutateSpy } = mountStepLayout(
      makeStep({ id: 1, ...stepPatch }),
    );

    result.onCoverUpdate(cover);

    expect(lastUpdate(mutateSpy)).toMatchObject(expected);
  });
});

describe("onPageUpdate", () => {
  it.each([
    [
      {
        pages: [
          { kind: "grid" as const, media: ["a", "b"] },
          { kind: "grid" as const, media: ["c", "d"] },
        ],
        unused: [],
      },
      ["a", "b", "c"],
      {
        pages: [
          { kind: "grid", media: ["a", "b", "c"] },
          { kind: "grid", media: ["d"] },
        ],
        unused: [],
      },
    ],
    [
      {
        pages: [{ kind: "grid" as const, media: ["a"] }],
        unused: ["u1", "u2"],
      },
      ["a", "u1"],
      {
        pages: [{ kind: "grid", media: ["a", "u1"] }],
        unused: ["u2"],
      },
    ],
    [
      {
        pages: [
          { kind: "grid" as const, media: ["a"] },
          { kind: "grid" as const, media: ["b"] },
        ],
        unused: [],
      },
      ["a", "b"],
      { pages: [{ kind: "grid", media: ["a", "b"] }] },
    ],
  ])("updates page placement", (stepPatch, page, expected) => {
    const { result, mutateSpy } = mountStepLayout(
      makeStep({ id: 1, ...stepPatch }),
    );

    result.onPageUpdate(0, page);

    expect(lastUpdate(mutateSpy)).toMatchObject(expected);
  });

  it("moves a panorama into a grid without leaving half a spread", () => {
    const { result, mutateSpy } = mountStepLayout(
      makeStep({
        pages: [
          { kind: "grid", media: ["grid.jpg"] },
          { kind: "panorama_spread", media: ["panorama.jpg"] },
        ],
      }),
    );

    result.onPageUpdate(0, ["grid.jpg", "panorama.jpg"]);

    expect(lastUpdate(mutateSpy)).toMatchObject({
      pages: [{ kind: "grid", media: ["grid.jpg", "panorama.jpg"] }],
    });
  });

  it("rejects a multi-media panorama before mutating", () => {
    const { result, mutateSpy } = mountStepLayout(
      makeStep({
        pages: [{ kind: "panorama_spread", media: ["panorama.jpg"] }],
      }),
    );

    result.onPageUpdate(0, ["panorama.jpg", "other.jpg"]);

    expect(mutateSpy).not.toHaveBeenCalled();
  });
});

describe("onUnusedUpdate", () => {
  it("removes a panorama spread as one logical page", () => {
    const { result, mutateSpy } = mountStepLayout(
      makeStep({
        pages: [{ kind: "panorama_spread", media: ["panorama.jpg"] }],
      }),
    );

    result.onUnusedUpdate(["panorama.jpg"]);

    expect(lastUpdate(mutateSpy)).toMatchObject({
      pages: [],
      unused: ["panorama.jpg"],
    });
  });
});
