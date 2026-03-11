import { useQuery } from "@pinia/colada";
import { readUser } from "@/client";
import { computed } from "vue";
import { queryKeys } from "./keys";

export function useUserQuery() {
  const query = useQuery({
    key: queryKeys.user(),
    query: async () => {
      const { data } = await readUser();
      return data;
    },
    staleTime: Infinity,
  });

  const user = computed(() => query.data.value?.user);
  const locale = computed(() => user.value?.locale.replace("_", "-") ?? "en");
  const isKm = computed(() => user.value?.unit_is_km ?? true);
  const isCelsius = computed(() => user.value?.temperature_is_celsius ?? true);

  function formatDistance(km: number): string {
    const value = isKm.value ? km : km * 0.621371;
    return Math.round(value).toLocaleString(locale.value);
  }

  function distanceUnit(): string {
    return isKm.value ? "km" : "mi";
  }

  function formatTemp(celsius: number): string {
    const value = isCelsius.value ? celsius : (celsius * 9) / 5 + 32;
    return `${Math.round(value)}°`;
  }

  function formatElevation(meters: number): string {
    const value = isKm.value ? meters : meters * 3.28084;
    return `${Math.round(value).toLocaleString(locale.value)}${isKm.value ? "m" : "ft"}`;
  }

  function formatDate(date: Date, options: Intl.DateTimeFormatOptions): string {
    return date.toLocaleDateString(locale.value, options);
  }

  return {
    ...query,
    user,
    locale,
    isKm,
    isCelsius,
    formatDistance,
    distanceUnit,
    formatTemp,
    formatElevation,
    formatDate,
  };
}
