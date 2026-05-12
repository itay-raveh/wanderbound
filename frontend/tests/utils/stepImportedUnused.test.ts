import { mergeImportedUnused } from "@/utils/stepImportedUnused";
import { makeStep } from "../helpers";

describe("mergeImportedUnused", () => {
  it("does not re-add imported media that was placed on a page", () => {
    const step = makeStep({
      pages: [["imported.jpg"]],
      unused: [],
    });

    expect(mergeImportedUnused(step, ["imported.jpg"]).unused).toEqual([]);
  });

  it("does not re-add imported media that was placed as step cover", () => {
    const step = makeStep({
      cover: "imported.jpg",
      unused: [],
    });

    expect(mergeImportedUnused(step, ["imported.jpg"]).unused).toEqual([]);
  });

  it("prepends imports that are not in base step state yet", () => {
    const step = makeStep({ unused: ["old.jpg"] });

    expect(mergeImportedUnused(step, ["new.jpg"]).unused).toEqual([
      "new.jpg",
      "old.jpg",
    ]);
  });
});
