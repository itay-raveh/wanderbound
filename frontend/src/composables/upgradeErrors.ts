export const UPGRADE_ERRORS = {
  popupBlocked: "popupBlocked",
  noResults: "noResults",
  selectionTimeout: "selectionTimeout",
  selectionCancelled: "selectionCancelled",
  connectionLost: "connectionLost",
  authCancelled: "authCancelled",
  authTimeout: "authTimeout",
  chromeOnly: "chromeOnly",
} as const;

export type UpgradeErrorKey = (typeof UPGRADE_ERRORS)[keyof typeof UPGRADE_ERRORS];
