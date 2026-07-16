import {
  googleUpgradeRequestLimitError,
  hasReachedGoogleUpgradeSessionLimit,
  mediaUpgradeInvalidationKeys,
} from "@/composables/useMediaUpgrade";
import { queryKeys } from "@/queries/keys";
import {
  GOOGLE_UPGRADE_MAX_MATCHES,
  GOOGLE_UPGRADE_MAX_SESSION_IDS,
} from "@/utils/externalMediaLimits";
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
      hasReachedGoogleUpgradeSessionLimit(
        Array.from({ length: GOOGLE_UPGRADE_MAX_SESSION_IDS - 1 }),
      ),
    ).toBe(false);
    expect(
      hasReachedGoogleUpgradeSessionLimit(
        Array.from({ length: GOOGLE_UPGRADE_MAX_SESSION_IDS }),
      ),
    ).toBe(true);
  });

  it("reports the backend request cap that would reject an upgrade", () => {
    expect(
      googleUpgradeRequestLimitError(
        Array.from({ length: GOOGLE_UPGRADE_MAX_SESSION_IDS + 1 }),
        Array.from({ length: 1 }),
      ),
    ).toBe(UPGRADE_ERRORS.tooManySelectionRounds);
    expect(
      googleUpgradeRequestLimitError(
        Array.from({ length: 1 }),
        Array.from({ length: GOOGLE_UPGRADE_MAX_MATCHES + 1 }),
      ),
    ).toBe(UPGRADE_ERRORS.tooManyMatches);
    expect(
      googleUpgradeRequestLimitError(
        Array.from({ length: GOOGLE_UPGRADE_MAX_SESSION_IDS }),
        Array.from({ length: GOOGLE_UPGRADE_MAX_MATCHES }),
      ),
    ).toBeNull();
  });
});
