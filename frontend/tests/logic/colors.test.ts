import { getCountryColor, DEFAULT_COUNTRY_COLOR } from "@/components/album/colors";

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
