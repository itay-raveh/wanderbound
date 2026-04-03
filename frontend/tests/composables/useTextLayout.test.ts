import { distributePages, type JustifiedLine } from "@/composables/useTextLayout";

function line(text: string): JustifiedLine {
  return { text };
}

function lines(count: number): JustifiedLine[] {
  return Array.from({ length: count }, (_, i) => line(`Line ${i}`));
}

describe("distributePages", () => {
  it("puts all lines in sidebar when they fit", () => {
    const result = distributePages(lines(5), 10, 20);
    expect(result).toHaveLength(1);
    expect(result[0]).toHaveLength(5);
  });

  it("puts all lines in sidebar at exact capacity", () => {
    const result = distributePages(lines(10), 10, 20);
    expect(result).toHaveLength(1);
    expect(result[0]).toHaveLength(10);
  });

  it("overflows to one continuation page", () => {
    const result = distributePages(lines(15), 10, 20);
    expect(result).toHaveLength(2);
    expect(result[0]).toHaveLength(10);
    expect(result[1]).toHaveLength(5);
  });

  it("overflows to multiple continuation pages", () => {
    const result = distributePages(lines(30), 5, 8);
    // 5 sidebar + 8 + 8 + 8 + 1 = 30
    expect(result).toHaveLength(5);
    expect(result[0]).toHaveLength(5);
    expect(result[1]).toHaveLength(8);
    expect(result[2]).toHaveLength(8);
    expect(result[3]).toHaveLength(8);
    expect(result[4]).toHaveLength(1);
  });

  it("pages contain non-overlapping sequential slices", () => {
    const all = lines(25);
    const result = distributePages(all, 7, 10);

    const flat = result.flat();
    expect(flat).toHaveLength(25);
    flat.forEach((l, i) => {
      expect(l.text).toBe(`Line ${i}`);
    });
  });

  it("returns single empty page for empty input", () => {
    const result = distributePages([], 10, 20);
    expect(result).toEqual([[]]);
  });

  it("handles single line", () => {
    const result = distributePages([line("Only")], 10, 20);
    expect(result).toEqual([[line("Only")]]);
  });

  it("preserves paragraph break lines in distribution", () => {
    const input = [
      line("First paragraph line 1"),
      line("First paragraph line 2"),
      line(""), // paragraph break
      line("Second paragraph line 1"),
      line("Second paragraph line 2"),
    ];
    const result = distributePages(input, 3, 10);
    expect(result).toHaveLength(2);
    // Sidebar: first 3 lines (2 text + 1 break)
    expect(result[0]).toEqual([
      line("First paragraph line 1"),
      line("First paragraph line 2"),
      line(""),
    ]);
    // Continuation: remaining 2 lines
    expect(result[1]).toEqual([
      line("Second paragraph line 1"),
      line("Second paragraph line 2"),
    ]);
  });

  it("guards against NaN sidebarMax (treats as unlimited)", () => {
    const result = distributePages(lines(5), NaN, 10);
    expect(result).toHaveLength(1);
    expect(result[0]).toHaveLength(5);
  });

  it("guards against NaN continuationMax (treats as unlimited)", () => {
    const result = distributePages(lines(15), 5, NaN);
    expect(result).toHaveLength(2);
    expect(result[0]).toHaveLength(5);
    expect(result[1]).toHaveLength(10);
  });

  it("guards against zero sidebarMax", () => {
    const result = distributePages(lines(5), 0, 10);
    expect(result).toHaveLength(1);
    expect(result[0]).toHaveLength(5);
  });

  it("guards against negative continuationMax", () => {
    const result = distributePages(lines(15), 5, -1);
    expect(result).toHaveLength(2);
    expect(result[0]).toHaveLength(5);
    expect(result[1]).toHaveLength(10);
  });
});
