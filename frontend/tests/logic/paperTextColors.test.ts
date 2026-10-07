import { colors } from "quasar";
import { paperTextColors } from "@/components/album/colors";

function contrast(foreground: string, background: string): number {
  const luminances = [
    colors.luminosity(foreground),
    colors.luminosity(background),
  ].sort((a, b) => b - a);
  return (luminances[0] + 0.05) / (luminances[1] + 0.05);
}

it("preserves small-text contrast and hierarchy across saturated, pale and borderline paper", () => {
  const samples = [
    "#ffeeaa",
    "#202040",
    "#ff0000",
    "#00ff00",
    "#0000ff",
    "#ff00ff",
    "#00ffff",
    "#b00090",
    "#8b8050",
  ];
  for (let channel = 0; channel <= 255; channel++) {
    samples.push(`#${channel.toString(16).padStart(2, "0").repeat(3)}`);
  }
  for (const r of [0, 51, 102, 153, 204, 255]) {
    for (const g of [0, 51, 102, 153, 204, 255]) {
      for (const b of [0, 51, 102, 153, 204, 255]) {
        samples.push(
          `#${[r, g, b].map((channel) => channel.toString(16).padStart(2, "0")).join("")}`,
        );
      }
    }
  }
  for (const paper of samples) {
    const { text, muted, faint } = paperTextColors(paper);
    const ratios = [text, muted, faint].map((color) => contrast(color, paper));
    expect(Math.min(...ratios), paper).toBeGreaterThanOrEqual(4.5);
    expect(ratios[0], paper).toBeGreaterThanOrEqual(ratios[1]);
    expect(ratios[1], paper).toBeGreaterThanOrEqual(ratios[2]);
  }
  const cream = paperTextColors("#ffeeaa");
  expect(new Set(Object.values(cream)).size).toBe(3);
  const tint = colors.textToRgb(cream.muted);
  expect(tint.r).toBeGreaterThan(tint.g);
  expect(tint.g).toBeGreaterThan(tint.b);
  const borderline = paperTextColors("#777777");
  expect(borderline.muted).toBe(borderline.faint);
});
