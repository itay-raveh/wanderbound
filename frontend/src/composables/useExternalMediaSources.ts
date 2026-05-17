import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { useGooglePhotos } from "./useGooglePhotos";

export function useExternalMediaSources() {
  const googlePhotos = useGooglePhotos();
  const { t } = useI18n();

  const googleStatusLabel = computed(() => {
    switch (googlePhotos.state.value) {
      case "connected":
        return t("externalMedia.google.connected");
      case "disconnected":
        return t("externalMedia.google.disconnected");
      default:
        return t("externalMedia.google.unavailable");
    }
  });

  return {
    googlePhotos,
    googleStatusLabel,
    googleAvailable: computed(
      () => googlePhotos.state.value !== "unavailable",
    ),
    googleConnected: computed(() => googlePhotos.state.value === "connected"),
  };
}
