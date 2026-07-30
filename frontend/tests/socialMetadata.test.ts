import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const html = readFileSync(resolve("index.html"), "utf8");
const document = new DOMParser().parseFromString(html, "text/html");

function content(selector: string): string | null {
  return document.querySelector<HTMLMetaElement>(selector)?.content ?? null;
}

it("provides complete metadata for social link previews", () => {
  expect({
    canonical: document.querySelector<HTMLLinkElement>('link[rel="canonical"]')
      ?.href,
    openGraphUrl: content('meta[property="og:url"]'),
    openGraphSiteName: content('meta[property="og:site_name"]'),
    openGraphImage: content('meta[property="og:image"]'),
    openGraphImageType: content('meta[property="og:image:type"]'),
    openGraphImageWidth: content('meta[property="og:image:width"]'),
    openGraphImageHeight: content('meta[property="og:image:height"]'),
    openGraphImageAlt: content('meta[property="og:image:alt"]'),
    twitterImage: content('meta[name="twitter:image"]'),
    twitterImageAlt: content('meta[name="twitter:image:alt"]'),
  }).toEqual({
    canonical: "https://wanderbound.raveh.dev/",
    openGraphUrl: "https://wanderbound.raveh.dev/",
    openGraphSiteName: "Wanderbound",
    openGraphImage: "https://wanderbound.raveh.dev/og-image.png",
    openGraphImageType: "image/png",
    openGraphImageWidth: "1200",
    openGraphImageHeight: "630",
    openGraphImageAlt:
      "Wanderbound: Turn your Polarsteps trips into photo albums",
    twitterImage: "https://wanderbound.raveh.dev/og-image.png",
    twitterImageAlt:
      "Wanderbound: Turn your Polarsteps trips into photo albums",
  });
});
