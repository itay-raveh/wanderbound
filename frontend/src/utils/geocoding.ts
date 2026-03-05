import { ref } from "vue";
import { client } from "@/api/client.gen.ts";
import { defineStore } from "pinia";
import { type Location } from "@/api";

let _locationCache: Location | null = null;

export const useUserLocation = defineStore("home", () => {
  const location = ref<Location | null>(null);

  function clear() {
    location.value = null;
  }

  function set() {
    if (_locationCache) {
      location.value = _locationCache;
      return;
    }
    navigator.geolocation.getCurrentPosition(
      ({ coords: { longitude: lon, latitude: lat } }) => {
        client
          .get<
            {
              data: {
                address: {
                  country_code: string;
                  country: string;
                  city?: string;
                  town?: string;
                  village?: string;
                };
              };
            },
            unknown,
            true
          >({
            url: `/nominatim/reverse?lat=${lat}&lon=${lon}&format=json&zoom=12`,
          })
          .then(({ data: { address } }) => {
            _locationCache = {
              lat,
              lon,
              name:
                address.city || address.town || address.village || "(Unknown)",
              detail: address.country,
              country_code: address.country_code,
            };
            location.value = _locationCache;
          })
          .catch(console.error);
      },
      () => {
        location.value = null;
      },
      { timeout: 10000 },
    );
  }

  return { location, set, clear };
});

interface Point {
  lat: number;
  lon: number;
}

// Haversine approximation
export function distance(p2: Point, p1: Point) {
  const R = 6371.2;
  const dLat = ((p2.lat - p1.lat) * Math.PI) / 180;
  const dLon = ((p2.lon - p1.lon) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((p1.lat * Math.PI) / 180) *
      Math.cos((p2.lat * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}
