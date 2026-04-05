export const mockUser = {
  id: 1,
  google_sub: "g-1",
  first_name: "Test",
  last_name: "User",
  profile_image_url: null,
  locale: "en-US",
  unit_is_km: true,
  temperature_is_celsius: true,
  album_ids: ["aid-1"],
  has_data: true,
  living_location: null,
};

export const mockAlbum = {
  id: "aid-1",
  uid: 1,
  title: "South America",
  subtitle: "A great adventure",
  hidden_steps: [],
  hidden_headers: [],
  maps_ranges: [],
  safe_margin_mm: 0,
  front_cover_photo: "cover.jpg",
  back_cover_photo: "back.jpg",
  colors: { nl: "#e77c31" },
};

export const mockMedia = [
  { name: "cover.jpg", width: 1920, height: 1080 },
  { name: "photo1.jpg", width: 1920, height: 1080 },
  { name: "photo2.jpg", width: 1080, height: 1920 },
];

export const mockStep = {
  id: 1,
  name: "Amsterdam",
  description: "Visited the canals.",
  timestamp: 1704067200,
  timezone_id: "Europe/Amsterdam",
  location: {
    name: "Amsterdam",
    detail: "North Holland",
    country_code: "nl",
    lat: 52.37,
    lon: 4.89,
  },
  elevation: 0,
  weather: {
    day: { temp: 5, feels_like: 2, icon: "cloudy" },
    night: null,
  },
  cover: "photo1.jpg",
  pages: [["photo1.jpg", "photo2.jpg"]],
  unused: [],
  datetime: "2024-01-01T12:00:00+01:00",
};

export const mockSteps = [mockStep];

export const mockSegmentOutlines = [
  {
    start_time: 1704060000,
    end_time: 1704067200,
    kind: "driving",
    timezone_id: "Europe/Amsterdam",
    start_coord: [52.0, 4.0],
    end_coord: [52.37, 4.89],
  },
];

// ---------------------------------------------------------------------------
// Rich mock data for photo-focus E2E tests (3 steps, 2 countries)
// ---------------------------------------------------------------------------

function makePhoto(idx: number): string {
  return `focus-photo-${idx}.jpg`;
}

const focusPhotos = Array.from({ length: 12 }, (_, i) => makePhoto(i + 1));

export const mockFocusMedia = focusPhotos.map((name) => ({
  name,
  width: 1920,
  height: 1080,
}));

export const mockFocusSteps = [
  {
    id: 101,
    name: "Buenos Aires",
    description: "Tango and steak.",
    timestamp: 1704067200,
    timezone_id: "America/Argentina/Buenos_Aires",
    location: { name: "Buenos Aires", detail: "CABA", country_code: "ar", lat: -34.6, lon: -58.4 },
    elevation: 25,
    weather: { day: { temp: 28, feels_like: 30, icon: "clear-day" }, night: null },
    cover: focusPhotos[0],
    pages: [[focusPhotos[0], focusPhotos[1], focusPhotos[2], focusPhotos[3]]],
    unused: [],
    datetime: "2024-01-01T12:00:00-03:00",
  },
  {
    id: 102,
    name: "Ushuaia",
    description: "End of the world.",
    timestamp: 1704240000,
    timezone_id: "America/Argentina/Ushuaia",
    location: { name: "Ushuaia", detail: "Tierra del Fuego", country_code: "ar", lat: -54.8, lon: -68.3 },
    elevation: 15,
    weather: { day: { temp: 10, feels_like: 7, icon: "cloudy" }, night: null },
    cover: focusPhotos[4],
    pages: [[focusPhotos[4], focusPhotos[5], focusPhotos[6]], [focusPhotos[7]]],
    unused: [],
    datetime: "2024-01-03T10:00:00-03:00",
  },
  {
    id: 103,
    name: "Santiago",
    description: "Wine country.",
    timestamp: 1704500000,
    timezone_id: "America/Santiago",
    location: { name: "Santiago", detail: "RM", country_code: "cl", lat: -33.4, lon: -70.6 },
    elevation: 520,
    weather: { day: { temp: 32, feels_like: 34, icon: "clear-day" }, night: null },
    cover: focusPhotos[8],
    pages: [[focusPhotos[8], focusPhotos[9], focusPhotos[10], focusPhotos[11]]],
    unused: [],
    datetime: "2024-01-06T14:00:00-03:00",
  },
];

/** 1x1 transparent JPEG as base64 for media route stubs. */
export const TINY_JPEG_BASE64 =
  "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAFBABAAAAAAAAAAAAAAAAAAAACf/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AKgA/9k=";
