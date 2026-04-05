import { ensureSatelliteContrast } from "@/components/album/colors";

describe("ensureSatelliteContrast", () => {
  it("lightens dark colors", () => {
    const result = ensureSatelliteContrast("#1a0a2e"); // very dark purple
    // Should be noticeably lighter than the input
    const brightness = parseInt(result.slice(1, 3), 16) + parseInt(result.slice(3, 5), 16) + parseInt(result.slice(5, 7), 16);
    expect(brightness).toBeGreaterThan(0x1a + 0x0a + 0x2e);
  });

  it("boosts near-black to a visible color", () => {
    const result = ensureSatelliteContrast("#111111");
    const r = parseInt(result.slice(1, 3), 16);
    const g = parseInt(result.slice(3, 5), 16);
    const b = parseInt(result.slice(5, 7), 16);
    // Should have meaningful brightness now
    expect(Math.max(r, g, b)).toBeGreaterThan(80);
  });
});
