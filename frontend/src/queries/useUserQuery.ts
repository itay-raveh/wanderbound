import { useQuery } from "@pinia/colada";
import { readUser } from "@/client";
import { computed } from "vue";
import { queryKeys } from "./keys";
import { KM_TO_MI, M_TO_FT } from "@/utils/units";

export function useUserQuery() {
  const query = useQuery({
    key: queryKeys.user(),
    query: async () => {
      const { data } = await readUser();
      return data;
    },
    staleTime: Infinity,
  });

  const user = computed(() => query.data.value);
  const locale = computed(() => user.value?.locale.replace("_", "-") ?? "en");
  const isKm = computed(() => user.value?.unit_is_km ?? true);
  const isCelsius = computed(() => user.value?.temperature_is_celsius ?? true);

  function formatDistance(km: number): string {
    const value = isKm.value ? km : km * KM_TO_MI;
    return Math.round(value).toLocaleString(locale.value);
  }

  function distanceUnit(): string {
    return isKm.value ? "km" : "mi";
  }

  function formatTemp(celsius: number): string {
    const value = isCelsius.value ? celsius : (celsius * 9) / 5 + 32;
    const unit = isCelsius.value ? "C" : "F";
    return `${Math.round(value).toLocaleString(locale.value)}°${unit}`;
  }

  function formatElevationValue(meters: number): string {
    const value = isKm.value ? meters : meters * M_TO_FT;
    return Math.round(value).toLocaleString(locale.value);
  }

  function formatElevation(meters: number): string {
    return `${formatElevationValue(meters)}${isKm.value ? "m" : "ft"}`;
  }

  function formatDate(date: Date, options: Intl.DateTimeFormatOptions): string {
    return date.toLocaleDateString(locale.value, options);
  }

  function formatDateRange(
    start: Date,
    end: Date,
    options: Intl.DateTimeFormatOptions,
  ): string {
    return new Intl.DateTimeFormat(locale.value, options).formatRange(start, end);
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
    formatElevationValue,
    formatElevation,
    formatDate,
    formatDateRange,
  };
}
