import { http, HttpResponse } from "msw";

export const BASE = "http://localhost:8000/api/v1";

export const defaultUser = {
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

export const defaultAlbum = {
  id: "aid-1",
  uid: 1,
  title: "Test Album",
  subtitle: "A test trip",
  excluded_steps: [],
  maps_ranges: [],
  front_cover_photo: "cover.jpg",
  back_cover_photo: "back.jpg",
  colors: { nl: "#e77c31" },
};

export const defaultMedia = [
  { name: "cover.jpg", width: 1920, height: 1080 },
  { name: "photo1.jpg", width: 1920, height: 1080 },
  { name: "photo2.jpg", width: 1080, height: 1920 },
];

const defaultStep = {
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

export const defaultSteps = [defaultStep];

export const defaultSegmentOutlines = [
  {
    start_time: 1704060000,
    end_time: 1704067200,
    kind: "driving",
    timezone_id: "Europe/Amsterdam",
    start_coord: [52.0, 4.0],
    end_coord: [52.37, 4.89],
  },
];

export const handlers = [
  http.get(`${BASE}/users`, () => HttpResponse.json(defaultUser)),
  http.patch(`${BASE}/users`, () => HttpResponse.json(defaultUser)),
  http.get(`${BASE}/albums/:aid`, () => HttpResponse.json(defaultAlbum)),
  http.patch(`${BASE}/albums/:aid`, () => HttpResponse.json(defaultAlbum)),
  http.get(`${BASE}/albums/:aid/media`, () => HttpResponse.json(defaultMedia)),
  http.get(`${BASE}/albums/:aid/steps`, () => HttpResponse.json(defaultSteps)),
  http.get(`${BASE}/albums/:aid/segments`, () => HttpResponse.json(defaultSegmentOutlines)),
  http.patch(`${BASE}/albums/:aid/steps/:sid`, () =>
    HttpResponse.json(defaultStep),
  ),
];
