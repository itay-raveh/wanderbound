import { useQuery } from "@pinia/colada";
import * as Sentry from "@sentry/vue";
import { readUser } from "@/client";
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { queryKeys } from "./keys";

export const KM_TO_MI = 0.621371;
export const M_TO_FT = 3.28084;

export function useUserQuery() {
  const { t } = useI18n();
  const query = useQuery({
    key: queryKeys.user(),
    query: async () => {
      const { data } = await readUser();
      if (data) Sentry.setUser({ id: String(data.id) });
      return data;
    },
    staleTime: Infinity,
  });

  const user = computed(() => query.data.value);
  const locale = computed(() => user.value?.locale ?? "en");
  const isKm = computed(() => user.value?.unit_is_km ?? true);
  const isCelsius = computed(() => user.value?.temperature_is_celsius ?? true);

  const distanceUnit = computed(() => t(isKm.value ? "overview.km" : "overview.mi"));
  const elevationUnit = computed(() => t(isKm.value ? "overview.m" : "overview.ft"));

  function formatDistance(km: number): string {
    const value = isKm.value ? km : km * KM_TO_MI;
    return Math.round(value).toLocaleString(locale.value);
  }

  function formatTemp(celsius: number): string {
    const value = isCelsius.value ? celsius : (celsius * 9) / 5 + 32;
    return `${Math.round(value).toLocaleString(locale.value)}°`;
  }

  function formatElevationValue(meters: number): string {
    const value = isKm.value ? meters : meters * M_TO_FT;
    return Math.round(value).toLocaleString(locale.value);
  }

  function formatElevation(meters: number): string {
    return `${formatElevationValue(meters)} ${elevationUnit.value}`;
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

  const regionNames = computed(
    () => new Intl.DisplayNames([locale.value], { type: "region" }),
  );

  /** Localized country name from ISO 3166-1 alpha-2 code, with fallback to detail string. */
  function countryName(code: string, detail: string): string {
    if (!code || code === "00") return detail;
    try {
      return regionNames.value.of(code.toUpperCase()) ?? detail;
    } catch {
      return detail;
    }
  }

  return {
    ...query,
    user,
    locale,
    isKm,
    isCelsius,
    distanceUnit,
    elevationUnit,
    formatDistance,
    formatTemp,
    formatElevationValue,
    formatElevation,
    formatDate,
    formatDateRange,
    countryName,
  };
}
