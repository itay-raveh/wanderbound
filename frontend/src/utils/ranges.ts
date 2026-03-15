export interface Range {
  start: number;
  end: number;
}

export function toRangeList(str: string): Range[] {
  if (!str || !str.trim()) return [];
  return str.split(",").map((part) => {
    const trimmed = part.trim();
    if (trimmed.includes("-")) {
      const parts = trimmed.split("-");
      return {
        start: parseInt(parts[0] ?? "0", 10),
        end: parseInt(parts[1] ?? "0", 10),
      };
    }
    const idx = parseInt(trimmed, 10);
    return { start: idx, end: idx };
  });
}
