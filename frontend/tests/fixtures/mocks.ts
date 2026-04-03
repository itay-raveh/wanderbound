// Single source of truth for test mock data.
// Used by both Vitest MSW handlers and Playwright E2E fixtures.

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
  excluded_steps: [],
  maps_ranges: [],
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

/** 1x1 transparent JPEG as base64 for media route stubs. */
export const TINY_JPEG_BASE64 =
  "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAFBABAAAAAAAAAAAAAAAAAAAACf/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AKgA/9k=";
