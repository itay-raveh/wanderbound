import { mediaUpgradeInvalidationKeys } from "@/composables/useMediaUpgrade";
import { queryKeys } from "@/queries/keys";

describe("mediaUpgradeInvalidationKeys", () => {
  it("invalidates album and normalized media metadata after upgrades", () => {
    expect(mediaUpgradeInvalidationKeys("album-1")).toEqual([
      queryKeys.album("album-1"),
      queryKeys.media("album-1"),
    ]);
  });
});
