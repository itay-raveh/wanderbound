import type { Step, SegmentOutline } from "@/client";

const CIRCUITY: Record<string, number> = {
  driving: 1.3,
  walking: 1.2,
  hike: 1.4,
  flight: 1.0,
};

function haversineKm(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

interface Overview {
  totalPhotos: number;
  estimatedDistanceKm: number;
  distanceKm: number;
  countries: { code: string; detail: string }[];
  coldest: { value: number; stepName: string } | null;
  hottest: { value: number; stepName: string } | null;
  highestElevation: { value: number; stepName: string } | null;
  furthestFromHome: { distanceKm: number; stepName: string } | null;
}

export function useOverview(
  steps: Step[],
  segmentOutlines: SegmentOutline[],
  exactDistanceKm: number | null,
  homeLocation: { lat: number; lon: number } | null,
): Overview {
  const totalPhotos = steps.reduce(
    (sum, s) => sum + s.pages.reduce((ps, page) => ps + page.length, 0),
    0,
  );

  let estimatedDistanceKm = 0;
  for (const seg of segmentOutlines) {
    const [lat1, lon1] = seg.start_coord;
    const [lat2, lon2] = seg.end_coord;
    const straight = haversineKm(lat1, lon1, lat2, lon2);
    estimatedDistanceKm += straight * (CIRCUITY[seg.kind] ?? 1.0);
  }

  const distanceKm = exactDistanceKm ?? estimatedDistanceKm;

  // Countries (preserve first-seen detail text)
  const seen = new Map<string, string>();
  for (const { location } of steps) {
    if (location.country_code !== "00" && !seen.has(location.country_code)) {
      seen.set(location.country_code, location.detail);
    }
  }
  const countries = [...seen].map(([code, detail]) => ({ code, detail }));

  // Extremes
  let coldest: Overview["coldest"] = null;
  let hottest: Overview["hottest"] = null;
  let highestElevation: Overview["highestElevation"] = null;
  let furthestFromHome: Overview["furthestFromHome"] = null;

  for (const s of steps) {
    const dayFeelsLike = s.weather.day.feels_like;
    const nightFeelsLike = s.weather.night?.feels_like;

    const candidates = [dayFeelsLike, nightFeelsLike].filter(
      (v): v is number => v != null,
    );
    const minFeel = candidates.length ? Math.min(...candidates) : undefined;
    const maxFeel = dayFeelsLike;

    if (minFeel != null && (!coldest || minFeel < coldest.value)) {
      coldest = { value: minFeel, stepName: s.name };
    }
    if (maxFeel != null && (!hottest || maxFeel > hottest.value)) {
      hottest = { value: maxFeel, stepName: s.name };
    }
    if (!highestElevation || s.elevation > highestElevation.value) {
      highestElevation = { value: s.elevation, stepName: s.name };
    }
    if (homeLocation) {
      const dist = haversineKm(
        homeLocation.lat,
        homeLocation.lon,
        s.location.lat,
        s.location.lon,
      );
      if (!furthestFromHome || dist > furthestFromHome.distanceKm) {
        furthestFromHome = { distanceKm: dist, stepName: s.name };
      }
    }
  }

  return {
    totalPhotos,
    estimatedDistanceKm,
    distanceKm,
    countries,
    coldest,
    hottest,
    highestElevation,
    furthestFromHome,
  };
}
