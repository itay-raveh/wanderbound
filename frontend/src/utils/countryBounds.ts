import rawBounds from "@/countries/bounds.json";

/** Country bounds indexed by lowercase ISO code: [x, y, width, height] in Web Mercator. */
export const countryBounds = rawBounds as unknown as Record<string, [number, number, number, number]>;
