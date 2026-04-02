import { getCountryColor, DEFAULT_COUNTRY_COLOR, ensureSatelliteContrast } from "@/components/album/colors";

describe("getCountryColor", () => {
  const colors: Record<string, string> = {
    US: "#FF0000",
    NL: "#FF6600",
    IL: "#0038B8",
  };

  it("returns the color for a known country code", () => {
    expect(getCountryColor(colors, "US")).toBe("#FF0000");
    expect(getCountryColor(colors, "NL")).toBe("#FF6600");
    expect(getCountryColor(colors, "IL")).toBe("#0038B8");
  });

  it("returns DEFAULT_COUNTRY_COLOR for unknown country code", () => {
    expect(getCountryColor(colors, "XX")).toBe(DEFAULT_COUNTRY_COLOR);
    expect(getCountryColor(colors, "")).toBe(DEFAULT_COUNTRY_COLOR);
  });

  it("returns DEFAULT_COUNTRY_COLOR for empty colors map", () => {
    expect(getCountryColor({}, "US")).toBe(DEFAULT_COUNTRY_COLOR);
  });

  it("is case-sensitive (country codes must match exactly)", () => {
    expect(getCountryColor(colors, "us")).toBe(DEFAULT_COUNTRY_COLOR);
    expect(getCountryColor(colors, "Us")).toBe(DEFAULT_COUNTRY_COLOR);
  });
});

describe("ensureSatelliteContrast", () => {
  it("returns bright saturated colors unchanged", () => {
    // Bright red — already vivid
    expect(ensureSatelliteContrast("#FF0000")).toBe("#FF0000");
    // Bright cyan
    expect(ensureSatelliteContrast("#00CCFF")).toBe("#00CCFF");
  });

  it("lightens dark colors", () => {
    const result = ensureSatelliteContrast("#1a0a2e"); // very dark purple
    // Should be noticeably lighter than the input
    const brightness = parseInt(result.slice(1, 3), 16) + parseInt(result.slice(3, 5), 16) + parseInt(result.slice(5, 7), 16);
    expect(brightness).toBeGreaterThan(0x1a + 0x0a + 0x2e);
  });

  it("saturates desaturated colors", () => {
    // Gray-ish blue — low saturation
    const result = ensureSatelliteContrast("#7788aa");
    // Result should differ from input (boosted saturation)
    expect(result).not.toBe("#7788aa");
  });

  it("boosts near-black to a visible color", () => {
    const result = ensureSatelliteContrast("#111111");
    const r = parseInt(result.slice(1, 3), 16);
    const g = parseInt(result.slice(3, 5), 16);
    const b = parseInt(result.slice(5, 7), 16);
    // Should have meaningful brightness now
    expect(Math.max(r, g, b)).toBeGreaterThan(80);
  });

  it("handles shorthand hex (#RGB)", () => {
    // #F00 = bright red, should pass through
    expect(ensureSatelliteContrast("#F00")).toBe("#F00");
  });

  it("is a pure function (no side effects)", () => {
    const input = "#2b1d0e";
    const result1 = ensureSatelliteContrast(input);
    const result2 = ensureSatelliteContrast(input);
    expect(result1).toBe(result2);
  });
});
