import { test as base, type Page } from "@playwright/test";

const API = "**/api/v1";

const mockUser = {
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

const mockAlbum = {
  id: "aid-1",
  uid: 1,
  title: "South America",
  subtitle: "A great adventure",
  steps_ranges: [["2024-01-01", "2024-01-15"]],
  maps_ranges: [],
  front_cover_photo: "cover.jpg",
  back_cover_photo: "back.jpg",
  colors: { nl: "#e77c31" },
  media: {},
};

const mockStep = {
  uid: 1,
  aid: "aid-1",
  id: 1,
  name: "Amsterdam",
  description: "Visited the canals and museums.",
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

const mockAlbumData = {
  steps: [mockStep],
  segments: [],
};

async function mockAllApi(page: Page) {
  await page.route(`${API}/users`, (route) => {
    return route.fulfill({ json: mockUser });
  });
  await page.route(`${API}/albums/**`, (route) => {
    const url = route.request().url();
    if (url.endsWith("/data")) {
      return route.fulfill({ json: mockAlbumData });
    }
    return route.fulfill({ json: mockAlbum });
  });
  await page.route(`${API}/auth/google`, (route) =>
    route.fulfill({ json: mockUser }),
  );
  // Serve a tiny 1x1 pixel for all media requests
  await page.route("**/media/**", (route) =>
    route.fulfill({
      contentType: "image/jpeg",
      body: Buffer.from(
        "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAFBABAAAAAAAAAAAAAAAAAAAACf/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AKgA/9k=",
        "base64",
      ),
    }),
  );
}

export const test = base.extend<{ authedPage: Page }>({
  authedPage: async ({ page }, use) => {
    await mockAllApi(page);
    await page.addInitScript(() =>
      localStorage.setItem("last-album-id", "aid-1"),
    );
    await use(page);
  },
});

export { expect } from "@playwright/test";
