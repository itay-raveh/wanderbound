import type { PhysicalRenderItem } from "./albumRenderPlan";

type PreviewPage = { item: PhysicalRenderItem; number: number };
export type PrintSpread = {
  covers: boolean;
  pages: [PreviewPage | null, PreviewPage | null];
};

export function buildPrintSpreads(items: PhysicalRenderItem[]): PrintSpread[] {
  const covers: PrintSpread = { covers: true, pages: [null, null] };
  const interiors = new Map<number, PrintSpread>();
  items.forEach((item, index) => {
    const page = { item, number: index + 1 };
    if (
      item.type === "header" &&
      (item.headerKey === "cover-front" || item.headerKey === "cover-back")
    ) {
      covers.pages[item.headerKey === "cover-back" ? 0 : 1] = page;
      return;
    }
    // Keep PDF parity even when one cover is hidden or the last page is unpaired.
    const pair = Math.floor(index / 2);
    let spread = interiors.get(pair);
    if (!spread) {
      spread = { covers: false, pages: [null, null] };
      interiors.set(pair, spread);
    }
    spread.pages[index % 2] = page;
  });
  return [
    ...(covers.pages.some(Boolean) ? [covers] : []),
    ...interiors.values(),
  ];
}
