import {
  googleUpgradeRequestLimitError,
  hasReachedGoogleUpgradeSessionLimit,
  mediaUpgradeInvalidationKeys,
} from "@/composables/useMediaUpgrade";
import { queryKeys } from "@/queries/keys";
import { UPGRADE_ERRORS } from "@/utils/upgradeErrors";

describe("mediaUpgradeInvalidationKeys", () => {
  it("invalidates album and normalized media metadata after upgrades", () => {
    expect(mediaUpgradeInvalidationKeys("album-1")).toEqual([
      queryKeys.album("album-1"),
      queryKeys.media("album-1"),
      queryKeys.printBundles("album-1"),
    ]);
  });
});

describe("Google upgrade frontend limits", () => {
  it("detects when selecting another picker session would exceed the backend cap", () => {
    expect(
      hasReachedGoogleUpgradeSessionLimit(Array.from({ length: 99 })),
    ).toBe(false);
    expect(
      hasReachedGoogleUpgradeSessionLimit(Array.from({ length: 100 })),
    ).toBe(true);
  });

  it("reports the backend request cap that would reject an upgrade", () => {
    expect(
      googleUpgradeRequestLimitError(
        Array.from({ length: 101 }),
        Array.from({ length: 1 }),
      ),
    ).toBe(UPGRADE_ERRORS.tooManySelectionRounds);
    expect(
      googleUpgradeRequestLimitError(
        Array.from({ length: 1 }),
        Array.from({ length: 10_001 }),
      ),
    ).toBe(UPGRADE_ERRORS.tooManyMatches);
    expect(
      googleUpgradeRequestLimitError(
        Array.from({ length: 100 }),
        Array.from({ length: 10_000 }),
      ),
    ).toBeNull();
  });
});
