import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const html = readFileSync(resolve("index.html"), "utf8");
const document = new DOMParser().parseFromString(html, "text/html");

function content(selector: string): string | null {
  return document.querySelector<HTMLMetaElement>(selector)?.content ?? null;
}

it("provides complete static metadata for social link previews", () => {
  expect({
    openGraphSiteName: content('meta[property="og:site_name"]'),
    openGraphImageType: content('meta[property="og:image:type"]'),
    openGraphImageWidth: content('meta[property="og:image:width"]'),
    openGraphImageHeight: content('meta[property="og:image:height"]'),
    openGraphImageAlt: content('meta[property="og:image:alt"]'),
    twitterImageAlt: content('meta[name="twitter:image:alt"]'),
  }).toEqual({
    openGraphSiteName: "Wanderbound",
    openGraphImageType: "image/png",
    openGraphImageWidth: "1200",
    openGraphImageHeight: "630",
    openGraphImageAlt:
      "Wanderbound: Turn your Polarsteps trips into photo albums",
    twitterImageAlt:
      "Wanderbound: Turn your Polarsteps trips into photo albums",
  });
});
