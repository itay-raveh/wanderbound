export interface IndexedPage {
  originalIdx: number;
  page: string[];
}

/** Filter out the cover photo from pages when it's already shown on the main page (short description). */
export function filterCoverFromPages(
  pages: string[][],
  cover: string | null | undefined,
  isShort: boolean,
): IndexedPage[] {
  if (!isShort || !cover) {
    return pages.map((page, i) => ({ originalIdx: i, page }));
  }
  return pages
    .map((page, i) => ({ originalIdx: i, page: page.filter((p) => p !== cover) }))
    .filter(({ page }) => page.length > 0);
}
