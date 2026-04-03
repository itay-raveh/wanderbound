import {
  mediaSrcset,
  THUMB_WIDTHS,
} from "@/utils/media";

describe("mediaSrcset", () => {
  it("builds srcset string with all thumb widths", () => {
    const result = mediaSrcset("photo.jpg", "abc");
    const parts = result.split(", ");
    expect(parts).toHaveLength(THUMB_WIDTHS.length);
    for (const w of THUMB_WIDTHS) {
      expect(result).toContain(`?w=${w} ${w}w`);
    }
  });
});
