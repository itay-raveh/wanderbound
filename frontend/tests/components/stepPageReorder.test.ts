import {
  planStepPages,
  reorderStepPhotoPages,
} from "@/components/album/stepPages";
import type { TextPage } from "@/composables/useTextLayout";
import { makeStep, photoGridPage } from "../helpers";

it("preserves finished pages and description portraits through repeated reordering", () => {
  const media = new Map(
    ["portrait-a", "portrait-b"].map((name) => [
      name,
      { name, width: 100, height: 200 },
    ]),
  );
  const text: TextPage[] = [
    { text: "Introduction", offset: 0, lineIndex: 0, direction: "ltr" },
    { text: "Continuation", offset: 12, lineIndex: 1, direction: "ltr" },
  ];
  const step = makeStep({
    cover: "cover",
    pages: [
      photoGridPage("cover", "portrait-a", "landscape"),
      { kind: "panorama_spread", media: ["wide"] },
      photoGridPage("portrait-b", "other"),
    ],
    unused: ["unused"],
  });
  const original = planStepPages(step, media, text);
  const reordered = reorderStepPhotoPages(original, 2, 0)!;
  const after = planStepPages({ ...step, pages: reordered }, media, text);

  expect(after.continuationPhotos).toEqual(original.continuationPhotos);
  expect(after.photoPages.map(({ page }) => page)).toEqual([
    photoGridPage("portrait-b", "other"),
    photoGridPage("landscape"),
    { kind: "panorama_spread", media: ["wide"] },
  ]);
  const restored = planStepPages(
    { ...step, pages: reorderStepPhotoPages(after, 0, 2)! },
    media,
    text,
  );
  expect(restored.photoPages.map(({ page }) => page)).toEqual(
    original.photoPages.map(({ page }) => page),
  );
  expect(restored.continuationPhotos).toEqual(["portrait-a"]);
  expect(new Set(reordered.flatMap((page) => page.media))).toEqual(
    new Set(
      step.pages
        .flatMap((page) => page.media)
        .filter((name) => name !== step.cover),
    ),
  );
});
