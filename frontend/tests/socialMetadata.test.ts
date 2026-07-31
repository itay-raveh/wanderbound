import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const html = readFileSync(resolve("index.html"), "utf8");
const document = new DOMParser().parseFromString(html, "text/html");

it("includes social sharing metadata", () => {
  const selectors = [
    'link[rel="canonical"]',
    'meta[property="og:type"]',
    'meta[property="og:url"]',
    'meta[property="og:site_name"]',
    'meta[property="og:title"]',
    'meta[property="og:description"]',
    'meta[property="og:image"]',
    'meta[property="og:image:type"]',
    'meta[property="og:image:width"]',
    'meta[property="og:image:height"]',
    'meta[property="og:image:alt"]',
    'meta[name="twitter:card"]',
    'meta[name="twitter:title"]',
    'meta[name="twitter:description"]',
    'meta[name="twitter:image"]',
    'meta[name="twitter:image:alt"]',
  ];

  for (const selector of selectors) {
    expect(document.querySelector(selector), selector).not.toBeNull();
  }
});
