import type { Step, SegmentOutline } from "@/client";
import { haversineKm } from "@/utils/geo";

const CIRCUITY: Record<string, number> = {
  driving: 1.3,
  walking: 1.2,
  hike: 1.4,
  flight: 1.0,
};

interface StepExtreme {
  value: number;
  step: Step;
}

interface ColdExtreme extends StepExtreme {
  isNight: boolean;
}

interface Overview {
  totalPhotos: number;
  estimatedDistanceKm: number;
  distanceKm: number;
  countries: { code: string; detail: string }[];
  coldest: ColdExtreme | null;
  hottest: StepExtreme | null;
  highestElevation: StepExtreme | null;
  furthestFromHome: StepExtreme | null;
}

export function computeOverview(
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

  // Extremes - single pass over all steps
  let coldest: ColdExtreme | null = null;
  let hottest: StepExtreme | null = null;
  let highestElevation: StepExtreme | null = null;
  let furthestFromHome: StepExtreme | null = null;

  for (const s of steps) {
    const dayFeels = s.weather.day.feels_like;

    // Hot: day feels-like only
    if (!hottest || dayFeels > hottest.value) {
      hottest = { value: dayFeels, step: s };
    }

    // Cold: check both day and night feels-like
    if (!coldest || dayFeels < coldest.value) {
      coldest = { value: dayFeels, step: s, isNight: false };
    }
    if (
      s.weather.night &&
      s.weather.night.feels_like < (coldest?.value ?? Infinity)
    ) {
      coldest = { value: s.weather.night.feels_like, step: s, isNight: true };
    }

    if (!highestElevation || s.elevation > highestElevation.value) {
      highestElevation = { value: s.elevation, step: s };
    }

    if (homeLocation) {
      const dist = haversineKm(
        homeLocation.lat,
        homeLocation.lon,
        s.location.lat,
        s.location.lon,
      );
      if (!furthestFromHome || dist > furthestFromHome.value) {
        furthestFromHome = { value: dist, step: s };
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
