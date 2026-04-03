import { http, HttpResponse } from "msw";
import {
  mockUser,
  mockAlbum,
  mockMedia,
  mockStep,
  mockSteps,
  mockSegmentOutlines,
} from "../fixtures/mocks";

export const BASE = "http://localhost:8000/api/v1";

// Re-export for tests that reference mock data directly
export {
  mockUser as defaultUser,
  mockAlbum as defaultAlbum,
  mockMedia as defaultMedia,
  mockSteps as defaultSteps,
  mockSegmentOutlines as defaultSegmentOutlines,
} from "../fixtures/mocks";

export const handlers = [
  http.get(`${BASE}/users`, () => HttpResponse.json(mockUser)),
  http.patch(`${BASE}/users`, () => HttpResponse.json(mockUser)),
  http.get(`${BASE}/albums/:aid`, () => HttpResponse.json(mockAlbum)),
  http.patch(`${BASE}/albums/:aid`, () => HttpResponse.json(mockAlbum)),
  http.get(`${BASE}/albums/:aid/media`, () => HttpResponse.json(mockMedia)),
  http.get(`${BASE}/albums/:aid/steps`, () => HttpResponse.json(mockSteps)),
  http.get(`${BASE}/albums/:aid/segments`, () =>
    HttpResponse.json(mockSegmentOutlines),
  ),
  http.patch(`${BASE}/albums/:aid/steps/:sid`, () =>
    HttpResponse.json(mockStep),
  ),
];
