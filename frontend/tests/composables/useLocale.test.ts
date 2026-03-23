import { resolveLocale, getLocaleOptions, applyLocale } from "@/composables/useLocale";

// ---------------------------------------------------------------------------
// resolveLocale
// ---------------------------------------------------------------------------

describe("resolveLocale", () => {
  it("returns exact match when available", () => {
    // "en-US" is a standard Quasar lang pack
    expect(resolveLocale("en-US")).toBe("en-US");
  });

  it("falls back to base language when region variant is unavailable", () => {
    // "he-IL" has no exact pack, but "he" does
    expect(resolveLocale("he")).toBe("he");
  });

  it("returns the original string when neither exact nor base matches", () => {
    // A made-up locale with no pack at all
    expect(resolveLocale("xx-YY")).toBe("xx-YY");
  });

  it("handles base-only codes that have packs", () => {
    // "fr" is a standard Quasar lang pack
    expect(resolveLocale("fr")).toBe("fr");
  });

  it("prefers exact match over base when both exist", () => {
    // "pt-BR" has its own pack; should not fall back to "pt"
    expect(resolveLocale("pt-BR")).toBe("pt-BR");
  });
});

// ---------------------------------------------------------------------------
// getLocaleOptions
// ---------------------------------------------------------------------------

describe("getLocaleOptions", () => {
  it("returns an array of { label, value } objects", () => {
    const options = getLocaleOptions();
    expect(Array.isArray(options)).toBe(true);
    expect(options.length).toBeGreaterThan(0);
    for (const opt of options) {
      expect(opt).toHaveProperty("label");
      expect(opt).toHaveProperty("value");
      expect(typeof opt.label).toBe("string");
      expect(typeof opt.value).toBe("string");
    }
  });

  it("caches the result on subsequent calls", () => {
    const first = getLocaleOptions();
    const second = getLocaleOptions();
    expect(first).toBe(second); // same reference
  });

  it("includes well-known locale codes", () => {
    const options = getLocaleOptions();
    const codes = options.map((o) => o.value);
    expect(codes).toContain("en-US");
    expect(codes).toContain("fr");
    expect(codes).toContain("de");
  });

  it("values are sorted alphabetically", () => {
    const options = getLocaleOptions();
    const values = options.map((o) => o.value);
    const sorted = [...values].sort();
    expect(values).toEqual(sorted);
  });
});

// ---------------------------------------------------------------------------
// applyLocale
// ---------------------------------------------------------------------------

describe("applyLocale", () => {
  it("sets document.documentElement.lang to the base language", async () => {
    await applyLocale("en-US");
    expect(document.documentElement.lang).toBe("en");
  });

  it("deduplicates consecutive calls with the same locale", async () => {
    await applyLocale("fr");
    document.documentElement.lang = "overwritten";

    // Second call with same locale should be a no-op
    await applyLocale("fr");
    expect(document.documentElement.lang).toBe("overwritten");
  });

  it("applies a different locale after a previous one", async () => {
    await applyLocale("en-US");
    expect(document.documentElement.lang).toBe("en");

    await applyLocale("de");
    expect(document.documentElement.lang).toBe("de");
  });
});
